import asyncio
import logging
import yt_dlp
import urllib.request
import json
from typing import List, Optional, Dict, Any
from app.config import settings
from app.schemas.video import Video, TranscriptLine

logger = logging.getLogger(__name__)


def _fetch_subtitle_json3(url: str) -> Optional[Dict[str, Any]]:
    """Fetch and parse JSON3 subtitle data from a URL."""
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        logger.warning("Error fetching subtitle JSON3: %s", e)
        return None


def _parse_json3_subtitles(subtitle_data: Dict[str, Any]) -> List[TranscriptLine]:
    """Parse JSON3 subtitle format into TranscriptLine objects."""
    lines = []
    for event in subtitle_data.get('events', []):
        segs = event.get('segs', [])
        if not segs:
            continue
        text = ' '.join(seg.get('utf8', '').strip() for seg in segs if seg.get('utf8', '').strip())
        if not text:
            continue
        t_start_ms = event.get('tStartMs', 0)
        dur_ms = event.get('dDurationMs', 0)
        lines.append(TranscriptLine(
            start=t_start_ms / 1000.0,
            end=(t_start_ms + dur_ms) / 1000.0,
            text=text
        ))
    return lines


def _check_transcript_for_video(video_id: str) -> bool:
    """
    Check if a video has English subtitles (manual or automatic).
    Makes a lightweight yt-dlp call with listsubtitles.
    """
    video_url = f"https://www.youtube.com/watch?v={video_id}"
    opts = {
        'quiet': True,
        'skip_download': True,
        'extract_flat': False,
        'listsubtitles': True,
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            auto_subs = info.get('automatic_captions', {})
            manual_subs = info.get('subtitles', {})
            has_en = 'en' in auto_subs or 'en' in manual_subs
            logger.debug("Video %s transcript check: %s", video_id, has_en)
            return has_en
    except Exception as e:
        logger.warning("Transcript check failed for %s: %s", video_id, e)
        return False


async def _check_transcript_thread(video_id: str) -> bool:
    """Thread-pool wrapper for _check_transcript_for_video."""
    return await asyncio.to_thread(_check_transcript_for_video, video_id)


def get_channel_videos(channel_name: str, channel_url: str, max_results: int = None) -> List[Video]:
    """Fetch list of videos from a YouTube channel, tagged with channel name."""
    opts = {
        'quiet': True,
        'extract_flat': False,
        'playlistend': max_results or settings.max_videos_per_channel,
        'skip_download': True,
    }

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(channel_url, download=False)
        entries = info.get('entries', []) or []

        videos = []
        for entry in entries:
            thumbnail = None
            thumbnails = entry.get('thumbnails') or []
            if thumbnails:
                # Pick ~medium range thumbnail (180-360 height) with largest area
                valid = [t for t in thumbnails if 180 <= t.get('height', 0) <= 400]
                if valid:
                    valid.sort(key=lambda t: t.get('height', 0) * t.get('width', 0), reverse=True)
                    thumbnail = valid[0].get('url')
                if not thumbnail:
                    thumbnails.sort(key=lambda t: t.get('height', 0) * t.get('width', 0), reverse=True)
                    thumbnail = thumbnails[0].get('url')

            videos.append(Video(
                id=entry.get('id', ''),
                title=entry.get('title', 'Unknown'),
                thumbnail=thumbnail,
                upload_date=entry.get('upload_date'),
                duration=entry.get('duration'),
                has_transcript=False,  # Will be updated after transcript check
                youtuber=channel_name,
            ))

        return videos


async def get_channel_videos_with_transcript_check(
    channel_name: str, channel_url: str, max_results: int = None
) -> List[Video]:
    """
    Fetch channel videos AND concurrently check transcript availability for each.
    Returns videos with has_transcript=True/False accurately set.
    """
    videos = await asyncio.to_thread(
        get_channel_videos, channel_name, channel_url, max_results
    )

    if not videos:
        return videos

    # Check transcripts concurrently — each call is independent
    results = await asyncio.gather(
        *(_check_transcript_thread(v.id) for v in videos),
        return_exceptions=True,
    )

    for video, result in zip(videos, results):
        if isinstance(result, Exception):
            logger.warning("Transcript check exception for %s: %s", video.id, result)
            video.has_transcript = False
        else:
            video.has_transcript = result

    return videos


def get_video_transcript(video_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch transcript for a specific video.
    Returns dict with title and list of transcript lines.
    """
    video_url = f"https://www.youtube.com/watch?v={video_id}"

    opts = {
        'quiet': True,
        'skip_download': True,
        'extract_flat': False,
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(video_url, download=False)

            title = info.get('title', 'Unknown')
            subtitles = info.get('automatic_captions', {})
            manual_subs = info.get('subtitles', {})

            # Find English subtitles (prefer manual, fall back to auto)
            en_subs = None
            for subs_dict in [manual_subs, subtitles]:
                if 'en' in subs_dict:
                    en_subs = subs_dict['en']
                    break

            if not en_subs:
                logger.debug("No English subtitles found for %s", video_id)
                return None

            # Find JSON3 format URL
            json3_url = None
            for fmt in en_subs:
                if fmt.get('ext') == 'json3':
                    json3_url = fmt.get('url')
                    break

            if not json3_url:
                return None

            # Fetch and parse the actual subtitle content
            subtitle_data = _fetch_subtitle_json3(json3_url)
            if not subtitle_data:
                return None

            lines = _parse_json3_subtitles(subtitle_data)

            return {
                'video_id': video_id,
                'title': title,
                'lines': lines
            }

    except Exception as e:
        logger.error("Error fetching transcript for %s: %s", video_id, e)
        return None


def check_video_has_transcript(video_id: str) -> bool:
    """Check if a video has available transcripts (manual or auto, English)."""
    return _check_transcript_for_video(video_id)
