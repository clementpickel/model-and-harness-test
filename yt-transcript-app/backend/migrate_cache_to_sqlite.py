"""
One-shot migration: reads the old /tmp/video_cache/*.json files and imports
them into the new SQLite database.

Run once, then delete. Safe to re-run (uses INSERT OR REPLACE).
"""
import json
import sys
import pathlib

OLD_CACHE = pathlib.Path("/tmp/video_cache")


def migrate():
    import asyncio
    from app.services.database import get_database

    async def _migrate():
        db = await get_database()

        for fpath in sorted(OLD_CACHE.glob("*.json")):
            key = fpath.stem          # e.g. "videos_Fireship"
            with open(fpath) as f:
                value = json.load(f)

            # Derive the cache key used by CacheService
            if key.startswith("transcript_"):
                cache_key = key
            elif key.startswith("last_updated_"):
                cache_key = key
            elif key.startswith("videos_"):
                cache_key = key
            else:
                print(f"SKIP unknown pattern: {fpath.name}")
                continue

            await db.set(cache_key, value)
            print(f"  imported {fpath.name} -> {cache_key}")

        print("\nMigration complete. Old cache files kept in place — delete them manually.")

    asyncio.run(_migrate())


if __name__ == "__main__":
    migrate()
