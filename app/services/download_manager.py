from pathlib import Path

from fastapi import HTTPException, status

from app.models.schemas import SongRecord
from app.services import downloader, song_cache, storage
from app.services.musicbrainz import lookup_recording


def download_musicbrainz_song(musicbrainz_id: str) -> SongRecord:
    # 1. Dedup: already downloaded?
    existing = storage.get_song_by_mbid(musicbrainz_id)
    if existing:
        _ensure_cached(existing)
        return existing

    # 2. Hydrate metadata from MusicBrainz
    try:
        meta = lookup_recording(musicbrainz_id)
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
    if downloader.is_in_progress(musicbrainz_id, title, artist):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Download already in progress for this song. Try again shortly.",
        )

    # 4. Download to temp file
    try:
        dl = downloader.download_song(
            musicbrainz_id=musicbrainz_id,
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

    # 5. Cache locally before persistence
    song_cache.put(dl["file_key"], dl["file_path"])

    # 6. Persist locally + write metadata row
    return storage.save_song(
        musicbrainz_id=musicbrainz_id,
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
    """If the song isn't in local cache, refill it from local disk path."""
    file_key = record.file_key or record.musicbrainz_id or record.id
    if song_cache.has(file_key):
        return

    # If file_path is already a cache URL, there is nothing else to do.
    if record.file_path.startswith("/api/cache/"):
        return

    local_path = Path(record.file_path)
    if local_path.exists() and local_path.is_file():
        try:
            song_cache.put(file_key, str(local_path))
        except OSError:
            pass
