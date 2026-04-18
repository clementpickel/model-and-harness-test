"""
SQLite-backed persistent cache for the YouTube transcript app.

Schema
------
  videos         — video metadata keyed by video_id (persistent, incremental refresh)
  transcripts    — parsed transcript lines per video_id (permanent once cached)
  metadata       — refresh bookkeeping (refreshed_at per channel)

No TTL on videos — refresh is incremental (only new videos) so old data is preserved.
Transcripts are permanently cached; a 404 means no transcript (cached as such).
"""

import json
import datetime
import asyncio
import aiosqlite
import logging
from pathlib import Path
from typing import Optional, Any
from app.config import settings

logger = logging.getLogger(__name__)


# ── helpers ───────────────────────────────────────────────────────────────────

def _serialize(value: Any) -> Any:
    """Recursively walk a Pydantic model or nested structure into JSON-safe dicts."""
    if hasattr(value, "model_dump"):
        return _serialize(value.model_dump())   # Pydantic v2
    if hasattr(value, "dict"):
        return _serialize(value.dict())        # Pydantic v1
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    return value


# ── service ──────────────────────────────────────────────────────────────────

class CacheService:
    """
    SQLite-backed cache with incremental video refresh.

    Key schema:
      transcript_{video_id}  → transcripts table  (permanent once set)
      last_updated_{channel} → metadata table     (ISO timestamp)
      refreshed_at_{channel} → metadata table     (ISO timestamp of last refresh)
    """

    def __init__(self, db_path: str = None):
        self._db_path = Path(db_path or settings.db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[aiosqlite.Connection] = None

    # ── lifecycle ────────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Call once at startup. Creates tables and handles WAL mode.

        Migration: if old per-channel videos_cache table exists (JSON blobs),
        rename it so the new per-video videos table can be created cleanly.
        """
        conn = await aiosqlite.connect(str(self._db_path))
        conn.row_factory = aiosqlite.Row
        self._conn = conn

        # Migrate legacy schema if needed — SQLite doesn't support ALTER TABLE IF EXISTS,
        # so we must check the table list first.
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='videos_cache'"
        )
        legacy_exists = await cursor.fetchone()
        if legacy_exists:
            await conn.execute("ALTER TABLE videos_cache RENAME TO _legacy_videos_cache")
            await conn.execute("ALTER TABLE metadata RENAME TO _legacy_metadata")
            await conn.commit()

        await conn.executescript("""
            PRAGMA journal_mode = WAL;

            CREATE TABLE IF NOT EXISTS videos (
                video_id      TEXT PRIMARY KEY,
                channel_name  TEXT NOT NULL,
                title         TEXT NOT NULL,
                thumbnail     TEXT,
                upload_date   TEXT,
                duration      INTEGER,
                has_transcript INTEGER NOT NULL DEFAULT 0,
                fetched_at    TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS transcripts (
                video_id     TEXT PRIMARY KEY,
                video_title  TEXT NOT NULL,
                lines_json   TEXT NOT NULL,
                fetched_at   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS metadata (
                key          TEXT PRIMARY KEY,
                value        TEXT NOT NULL,
                updated_at   TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_videos_channel ON videos(channel_name);
            CREATE INDEX IF NOT EXISTS idx_videos_upload_date ON videos(upload_date);
        """)
        await conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    # ── internal ──────────────────────────────────────────────────────────────

    async def _execute(self, sql: str, params=()):
        if self._conn is None:
            raise RuntimeError("CacheService not initialized — call initialize() first.")
        return await self._conn.execute(sql, params)

    async def _commit(self):
        await self._conn.commit()

    # ── public API ────────────────────────────────────────────────────────────

    async def get(self, key: str) -> Optional[Any]:
        """Return the deserialised value or None if missing."""
        if key.startswith("videos_"):
            return await self._get_videos_by_channel(key[len("videos_") :])
        if key.startswith("transcript_"):
            return await self._get_transcript(key[len("transcript_") :])
        if key.startswith("last_updated_") or key.startswith("refreshed_at_"):
            return await self._get_meta(key)
        return None

    async def set(self, key: str, value: Any) -> None:
        """Store a value."""
        serialized = _serialize(value)
        if key.startswith("videos_"):
            # videos are stored individually via upsert_video; this is a no-op
            # to keep the interface compatible with the old file-based cache
            pass
        elif key.startswith("transcript_"):
            await self._set_transcript(key[len("transcript_") :], serialized)
        elif key.startswith("last_updated_"):
            await self._set_meta(key, serialized)
        elif key.startswith("refreshed_at_"):
            await self._set_meta(key, serialized)

    async def delete(self, key: str) -> None:
        if key.startswith("transcript_"):
            await self._delete_transcript(key[len("transcript_") :])
        elif key.startswith("last_updated_") or key.startswith("refreshed_at_"):
            await self._delete_meta(key)

    async def clear(self) -> None:
        """Clear all data — videos, transcripts, and metadata."""
        await self._execute("DELETE FROM videos")
        await self._execute("DELETE FROM transcripts")
        await self._execute("DELETE FROM metadata")
        await self._commit()

    # ── videos ────────────────────────────────────────────────────────────────

    async def upsert_video(self, video_id: str, channel_name: str, title: str,
                           thumbnail: Optional[str], upload_date: Optional[str],
                           duration: Optional[int], has_transcript: bool) -> None:
        """Insert or replace a video. Idempotent — safe to call repeatedly."""
        now = datetime.datetime.utcnow().isoformat()
        await self._execute("""
            INSERT OR REPLACE INTO videos
              (video_id, channel_name, title, thumbnail, upload_date, duration, has_transcript, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (video_id, channel_name, title, thumbnail, upload_date, duration,
              1 if has_transcript else 0, now))
        await self._commit()

    async def upsert_videos_batch(
        self, videos: list, channel_name: str
    ) -> int:
        """
        Batch upsert a list of videos. Returns the number of newly inserted videos.
        Uses INSERT OR IGNORE so existing rows are preserved.
        """
        now = datetime.datetime.utcnow().isoformat()
        rows = [
            (v.id, channel_name, v.title, v.thumbnail, v.upload_date, v.duration,
             1 if v.has_transcript else 0, now)
            for v in videos
        ]
        await self._executemany("""
            INSERT OR IGNORE INTO videos
              (video_id, channel_name, title, thumbnail, upload_date, duration, has_transcript, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)
        await self._commit()
        # Count how many were actually inserted
        cursor = await self._execute(
            "SELECT COUNT(*) FROM videos WHERE channel_name = ? AND fetched_at = ?",
            (channel_name, now)
        )
        row = await cursor.fetchone()
        return row["COUNT(*)"] if row else 0

    async def _get_videos_by_channel(self, channel: str) -> Optional[list]:
        cursor = await self._execute(
            """SELECT video_id, channel_name, title, thumbnail, upload_date,
                      duration, has_transcript, fetched_at
               FROM videos WHERE channel_name = ?
               ORDER BY upload_date DESC, fetched_at DESC""",
            (channel,),
        )
        rows = await cursor.fetchall()
        if not rows:
            return None
        return [dict(r) for r in rows]

    async def get_all_videos(self) -> list:
        """Return all videos across all channels, sorted by upload_date descending."""
        cursor = await self._execute(
            """SELECT video_id, channel_name, title, thumbnail, upload_date,
                      duration, has_transcript, fetched_at
               FROM videos
               ORDER BY upload_date DESC, fetched_at DESC"""
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def get_max_upload_date(self, channel_name: str) -> Optional[str]:
        """Return the most recent upload_date we have for a channel."""
        cursor = await self._execute(
            "SELECT MAX(upload_date) as max_date FROM videos WHERE channel_name = ?",
            (channel_name,),
        )
        row = await cursor.fetchone()
        return row["max_date"] if row else None

    async def get_channel_last_updated(self, channel_name: str) -> Optional[str]:
        """Return the fetched_at timestamp of the most recently added video for a channel."""
        cursor = await self._execute(
            "SELECT MAX(fetched_at) as last_updated FROM videos WHERE channel_name = ?",
            (channel_name,),
        )
        row = await cursor.fetchone()
        return row["last_updated"] if row else None

    async def get_refreshed_at(self, channel_name: str) -> Optional[str]:
        return await self._get_meta(f"refreshed_at_{channel_name}")

    async def set_refreshed_at(self, channel_name: str) -> None:
        now = datetime.datetime.utcnow().isoformat()
        await self._set_meta(f"refreshed_at_{channel_name}", now)

    # ── transcripts ────────────────────────────────────────────────────────────

    async def _get_transcript(self, video_id: str) -> Optional[dict]:
        row = await self._execute(
            "SELECT video_title, lines_json FROM transcripts WHERE video_id = ?",
            (video_id,),
        )
        result = await row.fetchone()
        if result is None:
            return None
        return {
            "video_id": video_id,
            "title":    result["video_title"],
            "lines":    json.loads(result["lines_json"]),
        }

    async def _set_transcript(self, video_id: str, transcript: dict) -> None:
        now = datetime.datetime.utcnow().isoformat()
        await self._execute("""
            INSERT OR REPLACE INTO transcripts (video_id, video_title, lines_json, fetched_at)
            VALUES (?, ?, ?, ?)
        """, (video_id, transcript.get("title", "Unknown"),
              json.dumps(transcript.get("lines", [])), now))
        await self._commit()

    async def _delete_transcript(self, video_id: str) -> None:
        await self._execute("DELETE FROM transcripts WHERE video_id = ?", (video_id,))
        await self._commit()

    async def _executemany(self, sql: str, rows: list) -> None:
        if self._conn is None:
            raise RuntimeError("CacheService not initialized.")
        await self._conn.executemany(sql, rows)

    # ── metadata ──────────────────────────────────────────────────────────────

    async def _get_meta(self, key: str) -> Optional[str]:
        row = await self._execute("SELECT value FROM metadata WHERE `key` = ?", (key,))
        result = await row.fetchone()
        return result["value"] if result else None

    async def _set_meta(self, key: str, value: str) -> None:
        now = datetime.datetime.utcnow().isoformat()
        await self._execute(
            "INSERT OR REPLACE INTO metadata (`key`, value, updated_at) VALUES (?, ?, ?)",
            (key, value, now),
        )
        await self._commit()

    async def _delete_meta(self, key: str) -> None:
        await self._execute("DELETE FROM metadata WHERE `key` = ?", (key,))
        await self._commit()


# ── singleton ─────────────────────────────────────────────────────────────────

_cache: Optional[CacheService] = None


async def get_database() -> CacheService:
    global _cache
    if _cache is None:
        _cache = CacheService()
        await _cache.initialize()
    return _cache


def get_cache() -> CacheService:
    """Sync-friendly accessor — instance must already be initialized via lifespan."""
    if _cache is None:
        raise RuntimeError("Database not initialized.")
    return _cache
