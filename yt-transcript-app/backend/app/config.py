from pydantic_settings import BaseSettings
from pathlib import Path


class ChannelConfig(BaseSettings):
    name: str
    url: str


class Settings(BaseSettings):
    cache_ttl_seconds: int = 300
    cache_dir: str = "/tmp/video_cache"
    channels: list[ChannelConfig] = [
        ChannelConfig(name="bycloudAI", url="https://www.youtube.com/@bycloudAI/videos"),
        ChannelConfig(name="Fireship", url="https://www.youtube.com/@Fireship/videos"),
        ChannelConfig(name="T3", url="https://www.youtube.com/@t3dotgg/videos"),
    ]
    max_videos_per_channel: int = 10


settings = Settings()
