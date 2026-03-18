import hashlib
import os
import tempfile
import threading
from pathlib import Path
from typing import Optional

import yt_dlp

# Thread-safe set of file keys currently being downloaded
_in_progress: set[str] = set()
_lock = threading.Lock()


def _file_key(musicbrainz_id: Optional[str], title: str, artist: str) -> str:
    if musicbrainz_id:
        return musicbrainz_id
    raw = f"{title.lower().strip()}{artist.lower().strip()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def is_in_progress(musicbrainz_id: Optional[str], title: str, artist: str) -> bool:
    key = _file_key(musicbrainz_id, title, artist)
    with _lock:
        return key in _in_progress


def download_song(
    musicbrainz_id: Optional[str],
    title: str,
    artist: str,
    timeout_seconds: int = 60,
) -> dict:
    """
    Download a song via yt-dlp into a temp directory and return metadata dict.
    The caller is responsible for uploading and deleting the file.
    Raises RuntimeError on failure, TimeoutError on timeout.
    """
    key = _file_key(musicbrainz_id, title, artist)

    with _lock:
        if key in _in_progress:
            raise RuntimeError("Download already in progress for this song")
        _in_progress.add(key)

    tmp_dir = tempfile.mkdtemp(prefix="mixd_")
    output_path = os.path.join(tmp_dir, f"{key}.%(ext)s")
    final_path = os.path.join(tmp_dir, f"{key}.mp3")

    result: dict = {}
    error: list[Exception] = []

    def _do_download():
        try:
            ydl_opts = {
                "format": "bestaudio/best",
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }
                ],
                "outtmpl": output_path,
                "default_search": "ytsearch1",
                "noplaylist": True,
                "quiet": True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"{title} - {artist}", download=True)
                if "entries" in info:
                    info = info["entries"][0]
                result["info"] = info
        except Exception as exc:
            error.append(exc)

    thread = threading.Thread(target=_do_download, daemon=True)
    thread.start()
    thread.join(timeout=timeout_seconds)

    with _lock:
        _in_progress.discard(key)

    if thread.is_alive():
        raise TimeoutError(f"Download timed out after {timeout_seconds}s")

    if error:
        raise RuntimeError(f"yt-dlp error: {error[0]}") from error[0]

    info = result.get("info", {})

    return {
        "file_path": final_path,
        "duration_seconds": int(info["duration"]) if info.get("duration") else None,
        "youtube_video_id": info.get("id"),
        "youtube_title": info.get("title"),
        "file_key": key,
    }
