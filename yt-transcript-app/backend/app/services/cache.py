import json
import time
from pathlib import Path
from typing import Optional, Any, get_origin, get_args
from app.config import settings


def _serialize_value(value: Any) -> Any:
    """Recursively serialize Pydantic models and other non-JSON types."""
    if hasattr(value, 'model_dump'):
        # Pydantic v2
        return _serialize_value(value.model_dump())
    elif hasattr(value, 'dict'):
        # Pydantic v1
        return _serialize_value(value.dict())
    elif isinstance(value, list):
        return [_serialize_value(item) for item in value]
    elif isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    return value


class CacheService:
    def __init__(self, cache_dir: str = None):
        self.cache_dir = Path(cache_dir or settings.cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def get(self, key: str) -> Optional[Any]:
        """Get cached value if it exists and is not expired."""
        path = self._get_path(key)
        if not path.exists():
            return None

        try:
            # Check TTL by reading mtime
            mtime = path.stat().st_mtime
            age = time.time() - mtime

            if age > settings.cache_ttl_seconds:
                path.unlink()  # Remove expired cache
                return None

            with open(path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def set(self, key: str, value: Any) -> None:
        """Set cached value."""
        path = self._get_path(key)
        serialized = _serialize_value(value)
        with open(path, 'w') as f:
            json.dump(serialized, f)

    def delete(self, key: str) -> None:
        """Delete a cached value."""
        path = self._get_path(key)
        if path.exists():
            path.unlink()

    def clear(self) -> None:
        """Clear all cached values."""
        for path in self.cache_dir.glob("*.json"):
            path.unlink()

    def get_mtime(self, key: str) -> Optional[float]:
        """Get modification time of cached value."""
        path = self._get_path(key)
        if path.exists():
            return path.stat().st_mtime
        return None


# Singleton instance
_cache: Optional[CacheService] = None


def get_cache() -> CacheService:
    global _cache
    if _cache is None:
        _cache = CacheService()
    return _cache