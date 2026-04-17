from fastapi import APIRouter, BackgroundTasks, HTTPException
from datetime import datetime
from app.schemas.video import VideoListResponse, TranscriptResponse
from app.services.youtube import get_channel_videos, get_video_transcript
from app.services.cache import get_cache
from app.config import settings


router = APIRouter(prefix="/api", tags=["videos"])


def _fetch_and_cache_videos_for_channel(channel_name: str, channel_url: str):
    """Background task to fetch videos for one channel and update its cache."""
    cache = get_cache()
    videos = get_channel_videos(channel_name, channel_url)
    for video in videos:
        video.has_transcript = True  # Will be verified on request
    cache.set(f"videos_{channel_name}", videos)
    cache.set(f"last_updated_{channel_name}", datetime.utcnow().isoformat())


def _fetch_and_cache_all_videos():
    """Background task to fetch videos from all channels."""
    for channel in settings.channels:
        _fetch_and_cache_videos_for_channel(channel.name, channel.url)


@router.get("/videos", response_model=VideoListResponse)
async def get_videos():
    """Get list of videos from all channels."""
    cache = get_cache()
    all_videos = []
    latest_update = None

    for channel in settings.channels:
        videos = cache.get(f"videos_{channel.name}")
        updated_str = cache.get(f"last_updated_{channel.name}")

        if videos is None:
            # First-time fetch for this channel
            _fetch_and_cache_videos_for_channel(channel.name, channel.url)
            videos = cache.get(f"videos_{channel.name}")
            updated_str = cache.get(f"last_updated_{channel.name}")

        all_videos.extend(videos or [])

        if updated_str:
            updated = datetime.fromisoformat(updated_str)
            if latest_update is None or updated > latest_update:
                latest_update = updated

    return VideoListResponse(
        videos=all_videos,
        last_updated=latest_update
    )


@router.get("/videos/{video_id}/transcript", response_model=TranscriptResponse)
async def get_transcript(video_id: str):
    """Get transcript for a specific video."""
    cache = get_cache()
    cache_key = f"transcript_{video_id}"

    # Check cache first
    cached = cache.get(cache_key)
    if cached:
        return TranscriptResponse(**cached)

    # Fetch fresh
    transcript = get_video_transcript(video_id)
    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found")

    # Cache it
    cache.set(cache_key, transcript)

    return TranscriptResponse(**transcript)


@router.post("/refresh")
async def refresh_videos(background_tasks: BackgroundTasks):
    """Trigger a background refresh of all video lists."""
    cache = get_cache()
    for channel in settings.channels:
        cache.delete(f"videos_{channel.name}")
        cache.delete(f"last_updated_{channel.name}")

    background_tasks.add_task(_fetch_and_cache_all_videos)

    return {"status": "refresh_started"}


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    cache = get_cache()
    return {
        "status": "healthy",
        "channels": [c.name for c in settings.channels],
    }
