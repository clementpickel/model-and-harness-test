from pydantic_settings import BaseSettings
from typing import List
from app.schemas.video import ChannelConfig


class Settings(BaseSettings):
    cache_ttl_seconds: int = 300
    db_path: str = "/tmp/yt_transcripts.db"
    cors_origins: List[str] = [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "https://transcript.clementpickel.fr",
    ]
    channels: list[ChannelConfig] = [
        ChannelConfig(name="bycloudAI", url="https://www.youtube.com/@bycloudAI/videos"),
        ChannelConfig(name="Fireship", url="https://www.youtube.com/@Fireship/videos"),
        ChannelConfig(name="T3", url="https://www.youtube.com/@t3dotgg/videos"),
    ]
    max_videos_per_channel: int = 10

    class Config:
        env_prefix = "YT_"


settings = Settings()
