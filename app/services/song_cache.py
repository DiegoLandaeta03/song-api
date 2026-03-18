"""
Local disk cache for downloaded MP3 files.
Keeps songs on disk to avoid re-fetching from Supabase on repeated plays.
LRU eviction when the cache exceeds SONG_CACHE_MAX_MB.
"""

import os
import shutil
import threading
from pathlib import Path

from app.config import SONG_CACHE_DIR, SONG_CACHE_MAX_MB

_lock = threading.Lock()
_cache_dir = Path(SONG_CACHE_DIR)
_cache_dir.mkdir(parents=True, exist_ok=True)


def _cache_path(file_key: str) -> Path:
    return _cache_dir / f"{file_key}.mp3"


def has(file_key: str) -> bool:
    return _cache_path(file_key).exists()


def get_path(file_key: str) -> str | None:
    """Return the local file path if cached, updating its access time (LRU touch)."""
    p = _cache_path(file_key)
    if p.exists():
        # Touch access time for LRU
        p.touch()
        return str(p)
    return None


def put(file_key: str, source_path: str) -> str:
    """Copy (or move) a file into the cache. Returns the cached file path."""
    dest = _cache_path(file_key)
    if not dest.exists():
        shutil.copy2(source_path, dest)
    _evict_if_needed()
    return str(dest)


def put_from_bytes(file_key: str, data: bytes) -> str:
    """Write raw bytes into the cache."""
    dest = _cache_path(file_key)
    dest.write_bytes(data)
    _evict_if_needed()
    return str(dest)


def cache_size_mb() -> float:
    """Total size of cached files in MB."""
    total = sum(f.stat().st_size for f in _cache_dir.iterdir() if f.is_file())
    return total / (1024 * 1024)


def cache_count() -> int:
    return sum(1 for f in _cache_dir.iterdir() if f.is_file())


def _evict_if_needed():
    """Remove oldest-accessed files until under the max size."""
    with _lock:
        files = [f for f in _cache_dir.iterdir() if f.is_file()]
        total = sum(f.stat().st_size for f in files)
        max_bytes = SONG_CACHE_MAX_MB * 1024 * 1024

        if total <= max_bytes:
            return

        # Sort by access time ascending (oldest first)
        files.sort(key=lambda f: f.stat().st_atime)
        for f in files:
            if total <= max_bytes:
                break
            size = f.stat().st_size
            f.unlink(missing_ok=True)
            total -= size
