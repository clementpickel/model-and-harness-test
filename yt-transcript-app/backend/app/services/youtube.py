import yt_dlp
import urllib.request
import json
from typing import List, Optional, Dict, Any
from app.config import settings
from app.schemas.video import Video, TranscriptLine


def _fetch_subtitle_json3(url: str) -> Optional[Dict[str, Any]]:
    """Fetch and parse JSON3 subtitle data from a URL."""
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        print(f"Error fetching subtitle JSON3: {e}")
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


def get_channel_videos(max_results: int = None) -> List[Video]:
    """Fetch list of videos from the YouTube channel."""
    opts = {
        'quiet': True,
        'extract_flat': True,
        'playlistend': max_results or settings.max_videos,
        'skip_download': True,
    }

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(settings.channel_url, download=False)
        entries = info.get('entries', []) or []

        videos = []
        for entry in entries:
            videos.append(Video(
                id=entry.get('id', ''),
                title=entry.get('title', 'Unknown'),
                thumbnail=entry.get('thumbnail'),
                upload_date=entry.get('upload_date'),
                duration=entry.get('duration'),
                has_transcript=False  # Will be updated when fetching transcript
            ))

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
        print(f"Error fetching transcript for {video_id}: {e}")
        return None


def check_video_has_transcript(video_id: str) -> bool:
    """Check if a video has available transcripts."""
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
            return 'en' in auto_subs or 'en' in manual_subs
    except Exception:
        return False