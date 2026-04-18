import asyncio
from fastapi import APIRouter, BackgroundTasks, HTTPException
from datetime import datetime
from app.schemas.video import VideoListResponse, TranscriptResponse
from app.services.youtube import get_channel_videos, get_video_transcript
from app.services.database import get_cache
from app.config import settings


router = APIRouter(prefix="/api", tags=["videos"])


async def _fetch_and_cache_videos_for_channel(channel_name: str, channel_url: str):
    """Background task: fetch videos for one channel via yt-dlp and persist to SQLite."""
    # yt-dlp is sync — run in thread pool to avoid blocking the event loop
    videos = await asyncio.to_thread(get_channel_videos, channel_name, channel_url)
    for video in videos:
        video.has_transcript = True  # Verified on request; saves a call here

    cache = get_cache()
    await cache.set(f"videos_{channel_name}", videos)
    await cache.set(f"last_updated_{channel_name}", datetime.utcnow().isoformat())


async def _fetch_and_cache_all_videos():
    """Background task: refresh all channels concurrently."""
    await asyncio.gather(
        *(_fetch_and_cache_videos_for_channel(c.name, c.url) for c in settings.channels)
    )


@router.get("/videos", response_model=VideoListResponse)
async def get_videos():
    """Get list of videos from all channels."""
    cache = get_cache()
    all_videos = []
    latest_update = None

    for channel in settings.channels:
        videos = await cache.get(f"videos_{channel.name}")
        updated_str = await cache.get(f"last_updated_{channel.name}")

        if videos is None:
            # First-time fetch for this channel (blocking — only happens once)
            videos = await asyncio.to_thread(get_channel_videos, channel.name, channel.url)
            for video in videos:
                video.has_transcript = True
            await cache.set(f"videos_{channel.name}", videos)
            await cache.set(f"last_updated_{channel.name}", datetime.utcnow().isoformat())
            updated_str = await cache.get(f"last_updated_{channel.name}")

        all_videos.extend(videos or [])

        if updated_str:
            updated = datetime.fromisoformat(updated_str)
            if latest_update is None or updated > latest_update:
                latest_update = updated

    def sort_key(v):
        date = v.upload_date if hasattr(v, "upload_date") else v.get("upload_date")
        return date or "00000000"

    all_videos.sort(key=sort_key, reverse=True)

    return VideoListResponse(videos=all_videos, last_updated=latest_update)


@router.get("/videos/{video_id}/transcript", response_model=TranscriptResponse)
async def get_transcript(video_id: str):
    """Get transcript for a specific video."""
    cache = get_cache()
    cached = await cache.get(f"transcript_{video_id}")
    if cached:
        return TranscriptResponse(**cached)

    # yt-dlp is sync
    transcript = await asyncio.to_thread(get_video_transcript, video_id)
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found")

    await cache.set(f"transcript_{video_id}", transcript)
    return TranscriptResponse(**transcript)


@router.post("/refresh")
async def refresh_videos(background_tasks: BackgroundTasks):
    """Trigger a background refresh of all video lists."""
    cache = get_cache()
    for channel in settings.channels:
        await cache.delete(f"videos_{channel.name}")
        await cache.delete(f"last_updated_{channel.name}")

    background_tasks.add_task(_fetch_and_cache_all_videos)
    return {"status": "refresh_started"}


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "channels": [c.name for c in settings.channels],
    }
