"""
SQLite-backed persistent cache for the YouTube transcript app.

Schema
------
  videos_cache   — serialized video list per channel (mirrors old JSON files)
  transcripts    — parsed transcript lines per video_id (no TTL, persistent)
  metadata       — last_updated timestamps and TTL flags

The CacheService interface (get / set / delete / clear) is preserved so the
router needs zero changes beyond swapping the import.
"""

import json
import time
import datetime
import aiosqlite
from pathlib import Path
from typing import Optional, Any
from app.config import settings


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


def _is_expired(fetched_at: str, ttl_seconds: int) -> bool:
    """Return True when the stored ISO timestamp is older than ttl_seconds."""
    try:
        fetched_dt = datetime.datetime.fromisoformat(fetched_at)
        age = (datetime.datetime.utcnow() - fetched_dt).total_seconds()
        return age > ttl_seconds
    except Exception:
        return True   # Treat malformed dates as expired.


# ── service ──────────────────────────────────────────────────────────────────

class CacheService:
    """
    Drop-in replacement for the file-based CacheService.

    Routes key → table:
      videos_{channel}       → videos_cache  (TTL: cache_ttl_seconds)
      transcript_{video_id} → transcripts  (no TTL — permanent)
      last_updated_{channel} → metadata    (driven by videos_cache writes)
    """

    def __init__(self, db_path: str = None):
        self._db_path = Path(db_path or settings.db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: Optional[aiosqlite.Connection] = None

    # ── lifecycle ────────────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Call once at startup. Creates tables and handles WAL mode."""
        conn = await aiosqlite.connect(str(self._db_path))
        conn.row_factory = aiosqlite.Row
        self._conn = conn
        await conn.executescript("""
            PRAGMA journal_mode = WAL;

            CREATE TABLE IF NOT EXISTS videos_cache (
                channel_name TEXT PRIMARY KEY,
                videos_json  TEXT NOT NULL,
                fetched_at   TEXT NOT NULL          -- ISO 8601
            );

            CREATE TABLE IF NOT EXISTS transcripts (
                video_id     TEXT PRIMARY KEY,
                video_title  TEXT NOT NULL,
                lines_json   TEXT NOT NULL,         -- JSON array of TranscriptLine
                fetched_at   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS metadata (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)
        await conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    # ── internal cursor ──────────────────────────────────────────────────────

    async def _execute(self, sql: str, params=()):
        if self._conn is None:
            raise RuntimeError("CacheService not initialized — call initialize() first.")
        return await self._conn.execute(sql, params)

    async def _commit(self):
        await self._conn.commit()

    # ── public API ────────────────────────────────────────────────────────────

    async def get(self, key: str) -> Optional[Any]:
        """Return the deserialised value or None if missing / expired."""
        if key.startswith("videos_"):
            return await self._get_videos_cache(key[len("videos_") :])
        if key.startswith("transcript_"):
            return await self._get_transcript(key[len("transcript_") :])
        if key.startswith("last_updated_"):
            return await self._get_meta(f"last_updated_{key[len('last_updated_'):]}")
        return None

    async def set(self, key: str, value: Any) -> None:
        """Store a value.  TTL is enforced on reads, not writes."""
        serialized = _serialize(value)
        if key.startswith("videos_"):
            await self._set_videos_cache(key[len("videos_") :], serialized)
        elif key.startswith("transcript_"):
            await self._set_transcript(key[len("transcript_") :], serialized)
        elif key.startswith("last_updated_"):
            await self._set_meta(f"last_updated_{key[len('last_updated_'):]}", serialized)

    async def delete(self, key: str) -> None:
        if key.startswith("videos_"):
            await self._delete_videos_cache(key[len("videos_") :])
        elif key.startswith("transcript_"):
            await self._delete_transcript(key[len("transcript_") :])
        elif key.startswith("last_updated_"):
            await self._delete_meta(f"last_updated_{key[len('last_updated_'):]}")

    async def clear(self) -> None:
        await self._execute("DELETE FROM videos_cache")
        await self._execute("DELETE FROM transcripts")
        await self._execute("DELETE FROM metadata")
        await self._commit()

    # ── videos_cache ─────────────────────────────────────────────────────────

    async def _get_videos_cache(self, channel: str) -> Optional[list]:
        row = await self._execute(
            "SELECT videos_json, fetched_at FROM videos_cache WHERE channel_name = ?",
            (channel,),
        )
        result = await row.fetchone()
        if result is None:
            return None
        videos_json, fetched_at = result["videos_json"], result["fetched_at"]
        if _is_expired(fetched_at, settings.cache_ttl_seconds):
            await self._delete_videos_cache(channel)
            return None
        return json.loads(videos_json)

    async def _set_videos_cache(self, channel: str, videos: list) -> None:
        now = datetime.datetime.utcnow().isoformat()
        await self._execute(
            """
            INSERT OR REPLACE INTO videos_cache (channel_name, videos_json, fetched_at)
            VALUES (?, ?, ?)
            """,
            (channel, json.dumps(videos), now),
        )
        # Keep last_updated in sync
        await self._set_meta(f"last_updated_{channel}", now)
        await self._commit()

    async def _delete_videos_cache(self, channel: str) -> None:
        await self._execute("DELETE FROM videos_cache WHERE channel_name = ?", (channel,))
        await self._delete_meta(f"last_updated_{channel}")
        await self._commit()

    # ── transcripts ───────────────────────────────────────────────────────────

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
        await self._execute(
            """
            INSERT OR REPLACE INTO transcripts (video_id, video_title, lines_json, fetched_at)
            VALUES (?, ?, ?, ?)
            """,
            (video_id, transcript.get("title", "Unknown"),
             json.dumps(transcript.get("lines", [])), now),
        )
        await self._commit()

    async def _delete_transcript(self, video_id: str) -> None:
        await self._execute("DELETE FROM transcripts WHERE video_id = ?", (video_id,))
        await self._commit()

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
