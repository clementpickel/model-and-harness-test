from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    cache_ttl_seconds: int = 300  # 5 minutes default for active refresh
    cache_dir: str = "/tmp/video_cache"
    channel_url: str = "https://www.youtube.com/@bycloudAI/videos"
    max_videos: int = 50


settings = Settings()