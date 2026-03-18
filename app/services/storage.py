import json
import os
import re
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from mutagen.easyid3 import EasyID3
from mutagen.id3 import APIC, ID3, ID3NoHeaderError

from app.config import MANIFEST_FILE, SONG_LIBRARY_DIR
from app.models.schemas import SongRecord

_lock = threading.Lock()
_manifest_path = Path(MANIFEST_FILE)
_library_dir = Path(SONG_LIBRARY_DIR)
_library_dir.mkdir(parents=True, exist_ok=True)


def _load_manifest() -> dict:
    if not _manifest_path.exists():
        return {"songs": []}
    try:
        with open(_manifest_path) as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("songs"), list):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"songs": []}


def _save_manifest(data: dict) -> None:
    _manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(_manifest_path, "w") as f:
        json.dump(data, f, indent=2)


def _safe_filename(text: str) -> str:
    clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", text).strip()
    return clean[:140] or "song"


def _library_path(title: str, artist: str) -> Path:
    base = _safe_filename(f"{artist} - {title}")
    return _library_dir / f"{base}.mp3"


def _ensure_library_file(
    source_path: str,
    title: str,
    artist: str,
    existing_path: Optional[str] = None,
) -> str:
    if existing_path:
        dest = Path(existing_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            shutil.copy2(source_path, dest)
        return str(dest)

    base_path = _library_path(title=title, artist=artist)
    dest = base_path
    i = 2
    while dest.exists():
        dest = _library_dir / f"{base_path.stem} ({i}){base_path.suffix}"
        i += 1

    shutil.copy2(source_path, dest)
    return str(dest)


def _write_id3_tags(
    file_path: str,
    title: str,
    artist: str,
    album: Optional[str] = None,
    genres: Optional[list[str]] = None,
) -> None:
    """Write core ID3 tags so DJ software can populate metadata columns."""
    try:
        try:
            tags = EasyID3(file_path)
        except ID3NoHeaderError:
            tags = EasyID3()
            tags.save(file_path)
            tags = EasyID3(file_path)

        tags["title"] = [title]
        tags["artist"] = [artist]
        if album:
            tags["album"] = [album]
        if genres:
            tags["genre"] = genres
        tags.save()
    except Exception:
        # Tagging failures should not block downloading the audio file.
        pass


def _embed_cover_art(file_path: str, album_art_url: Optional[str]) -> None:
    """Embed cover art into MP3 so DJ software can display artwork."""
    if not album_art_url:
        return

    try:
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            resp = client.get(album_art_url)
        if resp.status_code != 200 or not resp.content:
            return

        mime = resp.headers.get("content-type", "").split(";")[0].strip().lower()
        if mime not in {"image/jpeg", "image/jpg", "image/png"}:
            # Fallback to JPEG when content-type is missing/odd.
            mime = "image/jpeg"
        if mime == "image/jpg":
            mime = "image/jpeg"

        try:
            tags = ID3(file_path)
        except ID3NoHeaderError:
            tags = ID3()

        # Keep one front-cover image; replace old one if present.
        tags.delall("APIC")
        tags.add(
            APIC(
                encoding=3,
                mime=mime,
                type=3,  # Cover (front)
                desc="Cover",
                data=resp.content,
            )
        )
        tags.save(file_path, v2_version=3)
    except Exception:
        # Artwork failures should not block downloads.
        pass


def get_song_by_mbid(musicbrainz_id: str) -> Optional[SongRecord]:
    with _lock:
        data = _load_manifest()
    for row in data["songs"]:
        if row.get("musicbrainz_id") == musicbrainz_id:
            return _row_to_record(row)
    return None


def get_song_by_key(file_key: str) -> Optional[SongRecord]:
    with _lock:
        data = _load_manifest()
    for row in data["songs"]:
        if row.get("file_key") == file_key:
            return _row_to_record(row)
    return None


def save_song(
    musicbrainz_id: Optional[str],
    title: str,
    artist: str,
    album: Optional[str],
    album_art_url: Optional[str],
    genres: list,
    file_path: str,
    duration_seconds: Optional[int],
    youtube_video_id: Optional[str],
    youtube_title: Optional[str],
    file_key: str,
) -> SongRecord:
    from app.services import song_cache

    with _lock:
        data = _load_manifest()
        existing = next(
            (
                row
                for row in data["songs"]
                if row.get("file_key") == file_key
                or (musicbrainz_id and row.get("musicbrainz_id") == musicbrainz_id)
            ),
            None,
        )
        local_file_path = _ensure_library_file(
            source_path=file_path,
            title=title,
            artist=artist,
            existing_path=existing.get("local_file_path") if existing else None,
        )
        _write_id3_tags(
            file_path=local_file_path,
            title=title,
            artist=artist,
            album=album,
            genres=genres or [],
        )
        _embed_cover_art(file_path=local_file_path, album_art_url=album_art_url)
        if existing:
            existing.update(
                {
                    "musicbrainz_id": musicbrainz_id,
                    "title": title,
                    "artist": artist,
                    "album": album,
                    "album_art_url": album_art_url,
                    "duration_seconds": duration_seconds,
                    "youtube_video_id": youtube_video_id,
                    "youtube_title": youtube_title,
                    "genres": genres or [],
                    "local_file_path": local_file_path,
                    "file_key": file_key,
                }
            )
            row = existing
        else:
            row = {
                "id": str(uuid.uuid4()),
                "musicbrainz_id": musicbrainz_id,
                "title": title,
                "artist": artist,
                "album": album,
                "album_art_url": album_art_url,
                "file_key": file_key,
                "duration_seconds": duration_seconds,
                "youtube_video_id": youtube_video_id,
                "youtube_title": youtube_title,
                "genres": genres or [],
                "local_file_path": local_file_path,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            data["songs"].append(row)
        _save_manifest(data)

    # Temp download file can be cleaned after persisting into library/cache.
    try:
        os.remove(file_path)
    except OSError:
        pass

    if not song_cache.has(file_key) and Path(local_file_path).exists():
        song_cache.put(file_key, local_file_path)

    return _row_to_record(row)


def songs_count() -> int:
    with _lock:
        data = _load_manifest()
    return len(data["songs"])


def storage_used_mb() -> float:
    total_bytes = 0
    if _library_dir.exists():
        for f in _library_dir.iterdir():
            if f.is_file() and f.suffix.lower() == ".mp3":
                total_bytes += f.stat().st_size
    return round(total_bytes / (1024 * 1024), 2)


def _row_to_record(row: dict) -> SongRecord:
    from app.services import song_cache

    file_key = row["file_key"]
    local_file_path = row.get("local_file_path")

    if local_file_path and Path(local_file_path).exists() and not song_cache.has(file_key):
        try:
            song_cache.put(file_key, local_file_path)
        except OSError:
            pass

    if song_cache.has(file_key):
        file_url = f"/api/cache/{file_key}"
    else:
        file_url = local_file_path or ""

    return SongRecord(
        id=row["id"],
        musicbrainz_id=row.get("musicbrainz_id"),
        title=row["title"],
        artist=row["artist"],
        album=row.get("album"),
        album_art_url=row.get("album_art_url"),
        file_path=file_url,
        file_key=file_key,
        duration_seconds=row.get("duration_seconds"),
        genres=row.get("genres") or [],
        youtube_video_id=row.get("youtube_video_id"),
        youtube_title=row.get("youtube_title"),
        downloaded_at=row.get("created_at", ""),
        status="downloaded",
    )
