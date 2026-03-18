from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse

from app.auth import validate_api_key, _is_valid_key
from app.services import song_cache

router = APIRouter(tags=["cache"])


@router.get("/cache/{file_key}")
def serve_cached_song(
    file_key: str,
    request: Request,
    key: str = Query(None, description="API key (alternative to header for audio elements)"),
):
    """Serve a locally cached MP3 file. Much faster than Supabase signed URLs."""
    # Accept key from query param or header
    api_key = key or request.headers.get("X-API-Key", "")
    if not _is_valid_key(api_key):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid API key")
    local = song_cache.get_path(file_key)
    if not local or not Path(local).exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not in local cache")
    return FileResponse(local, media_type="audio/mpeg")


@router.get("/cache-stats")
def cache_stats(_key: str = Depends(validate_api_key)):
    """Return local song cache statistics."""
    return {
        "cached_songs": song_cache.cache_count(),
        "used_mb": round(song_cache.cache_size_mb(), 2),
        "max_mb": song_cache.SONG_CACHE_MAX_MB,
    }
