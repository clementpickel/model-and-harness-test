import asyncio
import logging
from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, HTTPException
from app.schemas.video import VideoListResponse, TranscriptResponse, Video
from app.services.youtube import (
    get_channel_videos,
    get_channel_videos_with_transcript_check,
    get_video_transcript,
)
from app.services.database import get_database
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["videos"])


# ── background helpers ────────────────────────────────────────────────────────

async def _refresh_channel(channel_name: str, channel_url: str) -> int:
    """
    Incrementally refresh one channel: fetch all videos, diff by upload_date,
    and only INSERT OR IGNORE genuinely new ones (newer than our current max
    upload_date for this channel). Returns the count of new videos added.
    """
    # yt-dlp is sync — run in thread pool
    videos = await get_channel_videos_with_transcript_check(channel_name, channel_url)

    cache = get_database()

    # First refresh for this channel — insert everything
    max_date = await cache.get_max_upload_date(channel_name)

    if max_date is None:
        # No existing data — store all videos
        new_count = await cache.upsert_videos_batch(videos, channel_name)
        await cache.set_refreshed_at(channel_name)
        logger.info("Channel %s: initial import %d videos", channel_name, new_count)
        return new_count

    # Incremental refresh — only videos with upload_date > max_date are new
    new_videos = [v for v in videos if v.upload_date and v.upload_date > max_date]

    if not new_videos:
        logger.info("Channel %s: no new videos (max date %s)", channel_name, max_date)
        await cache.set_refreshed_at(channel_name)
        return 0

    new_count = await cache.upsert_videos_batch(new_videos, channel_name)
    await cache.set_refreshed_at(channel_name)
    logger.info("Channel %s: added %d new videos (max date was %s)", channel_name, new_count, max_date)
    return new_count


async def _refresh_all_channels() -> dict:
    """Refresh all channels concurrently. Returns {channel_name: new_count}."""
    results = await asyncio.gather(
        *(_refresh_channel(c.name, c.url) for c in settings.channels),
        return_exceptions=True,
    )
    report = {}
    for channel, result in zip(settings.channels, results):
        if isinstance(result, Exception):
            logger.error("Channel %s refresh failed: %s", channel.name, result)
            report[channel.name] = -1
        else:
            report[channel.name] = result
    return report


# ── routes ────────────────────────────────────────────────────────────────────

@router.get("/videos", response_model=VideoListResponse)
async def get_videos():
    """
    Return all cached videos across all channels.
    Serves immediately from SQLite — no blocking yt-dlp calls.
    If no videos are cached at all, triggers a background refresh.
    """
    cache = get_database()
    all_rows = await cache.get_all_videos()

    # First-ever load: cache is empty — fire background refresh, return empty list
    # (frontend can call /refresh manually or wait for background task)
    if not all_rows:
        # Trigger background refresh but don't wait
        asyncio.create_task(_refresh_all_channels())
        return VideoListResponse(videos=[], last_updated=None)

    # Reconstruct Video Pydantic models from DB rows
    videos = [
        Video(
            id=r["video_id"],
            title=r["title"],
            thumbnail=r["thumbnail"],
            upload_date=r["upload_date"],
            duration=r["duration"],
            has_transcript=bool(r["has_transcript"]),
            youtuber=r["channel_name"],
        )
        for r in all_rows
    ]

    # Compute last_updated from the most recent video fetched_at
    last_updated = None
    for r in all_rows:
        fetched = r.get("fetched_at")
        if fetched:
            dt = datetime.fromisoformat(fetched)
            if last_updated is None or dt > last_updated:
                last_updated = dt

    return VideoListResponse(videos=videos, last_updated=last_updated)


@router.get("/videos/{video_id}/transcript", response_model=TranscriptResponse)
async def get_transcript(video_id: str):
    """
    Get transcript for a specific video.
    Checks the DB cache first; on miss, fetches from YouTube via yt-dlp.
    """
    cache = get_database()
    cached = await cache.get(f"transcript_{video_id}")
    if cached:
        return TranscriptResponse(**cached)

    # yt-dlp is sync — run in thread pool
    transcript = await asyncio.to_thread(get_video_transcript, video_id)
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found")

    # Cache permanently
    await cache.set(f"transcript_{video_id}", transcript)

    # Also update has_transcript flag on the video so the list stays accurate
    await cache.upsert_video(
        video_id=video_id,
        channel_name="",  # unknown from this endpoint
        title=transcript.get("title", "Unknown"),
        thumbnail=None,
        upload_date=None,
        duration=None,
        has_transcript=True,
    )

    return TranscriptResponse(**transcript)


@router.post("/refresh")
async def refresh_videos(background_tasks: BackgroundTasks):
    """
    Trigger an incremental background refresh of all channels.
    Only fetches videos newer than the most recent video already cached.
    Old videos and transcripts are preserved.
    """
    # Run in background — client gets 202 immediately
    background_tasks.add_task(_refresh_all_channels)
    return {"status": "refresh_started"}


@router.post("/refresh/{channel_name}")
async def refresh_channel(channel_name: str, background_tasks: BackgroundTasks):
    """Trigger an incremental refresh for a single channel."""
    matched = [c for c in settings.channels if c.name == channel_name]
    if not matched:
        raise HTTPException(status_code=404, detail=f"Unknown channel: {channel_name}")

    async def _run():
        count = await _refresh_channel(matched[0].name, matched[0].url)
        logger.info("Channel %s refresh complete: %d new videos", channel_name, count)

    background_tasks.add_task(_run)
    return {"status": "refresh_started", "channel": channel_name}


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    cache = get_database()
    all_videos = await cache.get_all_videos()
    return {
        "status": "healthy",
        "channels": [c.name for c in settings.channels],
        "cached_videos": len(all_videos),
    }
