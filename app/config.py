import os
from dotenv import load_dotenv

load_dotenv()

MASTER_API_KEY: str = os.environ["MASTER_API_KEY"]
SONGS_DIR: str = os.getenv("SONGS_DIR", "/songs")
HOST: str = os.getenv("HOST", "0.0.0.0")
PORT: int = int(os.getenv("PORT", "8000"))
RATE_LIMIT: str = os.getenv("RATE_LIMIT", "60/minute")
API_KEYS_FILE: str = os.getenv("API_KEYS_FILE", "/app/api_keys.json")
MANIFEST_FILE: str = os.path.join(SONGS_DIR, "manifest.json")

SUPABASE_URL: str = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_KEY: str = os.environ["SUPABASE_SERVICE_KEY"]
SUPABASE_BUCKET: str = "song-files"

SEARCH_CACHE_MAX_SIZE: int = int(os.getenv("SEARCH_CACHE_MAX_SIZE", "500"))
SONG_CACHE_DIR: str = os.getenv("SONG_CACHE_DIR", "/songs/cache")
SONG_CACHE_MAX_MB: float = float(os.getenv("SONG_CACHE_MAX_MB", "2048"))  # default 2 GB
