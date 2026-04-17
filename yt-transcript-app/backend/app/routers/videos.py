from fastapi import APIRouter, BackgroundTasks, HTTPException
from datetime import datetime
from app.schemas.video import VideoListResponse, TranscriptResponse
from app.services.youtube import get_channel_videos, get_video_transcript
from app.services.cache import get_cache


router = APIRouter(prefix="/api", tags=["videos"])


def _fetch_and_cache_videos():
    """Background task to fetch videos and update cache."""
    cache = get_cache()
    videos = get_channel_videos()

    # Update has_transcript for each video
    for video in videos:
        video.has_transcript = True  # Assume true, will be verified on request

    cache.set("videos", videos)
    cache.set("last_updated", datetime.utcnow().isoformat())


@router.get("/videos", response_model=VideoListResponse)
async def get_videos():
    """Get list of videos from the channel."""
    cache = get_cache()

    videos = cache.get("videos")
    last_updated_str = cache.get("last_updated")

    if videos is None:
        # First-time fetch
        _fetch_and_cache_videos()
        videos = cache.get("videos")
        last_updated_str = cache.get("last_updated")

    last_updated = None
    if last_updated_str:
        last_updated = datetime.fromisoformat(last_updated_str)

    return VideoListResponse(
        videos=videos or [],
        last_updated=last_updated
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
    """Trigger a background refresh of video list."""
    cache = get_cache()
    cache.delete("videos")
    cache.delete("last_updated")

    background_tasks.add_task(_fetch_and_cache_videos)

    return {"status": "refresh_started"}


@router.get("/health")
async def health_check():
    """Health check endpoint."""
    cache = get_cache()
    last_updated = cache.get("last_updated")
    return {
        "status": "healthy",
        "cache_ttl": cache.get_mtime("videos"),
        "last_updated": last_updated
    }