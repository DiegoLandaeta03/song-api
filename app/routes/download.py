from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import validate_api_key
from app.models.schemas import DownloadRequest, SongRecord
from app.services import downloader, storage, song_cache
from app.services.musicbrainz import lookup_recording

router = APIRouter(tags=["download"])


@router.post("/download", response_model=SongRecord, status_code=status.HTTP_200_OK)
def download(
    body: DownloadRequest,
    _key: str = Depends(validate_api_key),
):
    # 1. Dedup: already in Supabase?
    existing = storage.get_song_by_mbid(body.musicbrainz_id)
    if existing:
        # Ensure the local cache has it for fast playback
        _ensure_cached(existing)
        return existing

    # 2. Hydrate all metadata from MusicBrainz
    try:
        meta = lookup_recording(body.musicbrainz_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"MusicBrainz lookup failed: {exc}",
        )

    title = meta["title"]
    artist = meta["artist"]

    if not title or not artist:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not determine title/artist from MusicBrainz ID",
        )

    # 3. Concurrent duplicate guard
    if downloader.is_in_progress(body.musicbrainz_id, title, artist):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Download already in progress for this song. Try again shortly.",
        )

    # 4. Download to temp file
    try:
        dl = downloader.download_song(
            musicbrainz_id=body.musicbrainz_id,
            title=title,
            artist=artist,
        )
    except TimeoutError as exc:
        raise HTTPException(status_code=status.HTTP_408_REQUEST_TIMEOUT, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Download failed: {exc}",
        )

    # 5. Cache locally before upload (upload deletes the temp file)
    song_cache.put(dl["file_key"], dl["file_path"])

    # 6. Upload to Supabase Storage + write DB row
    return storage.save_song(
        musicbrainz_id=body.musicbrainz_id,
        title=title,
        artist=artist,
        album=meta["album"],
        album_art_url=meta["album_art_url"],
        genres=meta["genres"],
        file_path=dl["file_path"],
        duration_seconds=dl["duration_seconds"],
        youtube_video_id=dl["youtube_video_id"],
        youtube_title=dl["youtube_title"],
        file_key=dl["file_key"],
    )


def _ensure_cached(record: SongRecord):
    """If the song isn't in local cache, download it from Supabase."""
    file_key = record.musicbrainz_id or record.id
    if song_cache.has(file_key):
        return
    try:
        import httpx
        resp = httpx.get(record.file_path, timeout=30, follow_redirects=True)
        if resp.status_code == 200:
            song_cache.put_from_bytes(file_key, resp.content)
    except Exception:
        pass  # Graceful fallback — Supabase URL still works
