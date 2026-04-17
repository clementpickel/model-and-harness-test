from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class TranscriptLine(BaseModel):
    start: float
    end: float
    text: str


class Video(BaseModel):
    id: str
    title: str
    thumbnail: Optional[str] = None
    upload_date: Optional[str] = None
    duration: Optional[int] = None
    has_transcript: bool = False


class VideoListResponse(BaseModel):
    videos: List[Video]
    last_updated: Optional[datetime] = None


class TranscriptResponse(BaseModel):
    video_id: str
    title: str
    lines: List[TranscriptLine]