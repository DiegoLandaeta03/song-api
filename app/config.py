import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_BASE_DIR = Path(__file__).resolve().parent.parent


def _resolve_path(path_value: str) -> str:
    """Resolve relative paths against the project root."""
    p = Path(path_value).expanduser()
    if not p.is_absolute():
        p = _BASE_DIR / p
    return str(p)


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


AUTH_REQUIRED: bool = _as_bool(os.getenv("AUTH_REQUIRED"), default=False)
MASTER_API_KEY: str = os.getenv("MASTER_API_KEY", "mxd_master_local_only")
if AUTH_REQUIRED and "MASTER_API_KEY" not in os.environ:
    raise RuntimeError("MASTER_API_KEY is required when AUTH_REQUIRED=true")

SONGS_DIR: str = _resolve_path(os.getenv("SONGS_DIR", "./songs"))
HOST: str = os.getenv("HOST", "0.0.0.0")
PORT: int = int(os.getenv("PORT", "8000"))
RATE_LIMIT: str = os.getenv("RATE_LIMIT", "60/minute")
API_KEYS_FILE: str = _resolve_path(os.getenv("API_KEYS_FILE", "./api_keys.json"))
MANIFEST_FILE: str = os.path.join(SONGS_DIR, "manifest.json")
SONG_LIBRARY_DIR: str = _resolve_path(os.getenv("SONG_LIBRARY_DIR", f"{SONGS_DIR}/library"))

SEARCH_CACHE_MAX_SIZE: int = int(os.getenv("SEARCH_CACHE_MAX_SIZE", "500"))
SONG_CACHE_DIR: str = _resolve_path(os.getenv("SONG_CACHE_DIR", f"{SONGS_DIR}/cache"))
SONG_CACHE_MAX_MB: float = float(os.getenv("SONG_CACHE_MAX_MB", "2048"))  # default 2 GB

# Ensure local file-system targets exist for local runs.
Path(SONGS_DIR).mkdir(parents=True, exist_ok=True)
Path(SONG_LIBRARY_DIR).mkdir(parents=True, exist_ok=True)
Path(SONG_CACHE_DIR).mkdir(parents=True, exist_ok=True)
Path(API_KEYS_FILE).parent.mkdir(parents=True, exist_ok=True)
