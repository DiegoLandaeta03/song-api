# Mixd Song API

A self-hosted song search and download API powered by MusicBrainz + YouTube. Search for songs by title/artist, download them as MP3s to local disk, and serve them with local caching for fast playback.

## Quick Start

### Prerequisites

- Python 3.11+
- `ffmpeg` (required by `yt-dlp`)

### Run

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# Edit .env with your keys (see Configuration below)
# For an external drive on macOS, set:
# SONGS_DIR=/Volumes/Deegs Drive/Vanessa's Quince

uvicorn app.main:app --host 0.0.0.0 --port 6493
```

The API will be available at `http://localhost:6493`. A web UI is served at the root (`/`).

#### Optional: Run with Docker

```bash
cp .env.example .env
# In .env, set SONGS_DIR=/songs for container path
# In .env, set HOST_SONGS_DIR to your host folder (optional)
# Example: HOST_SONGS_DIR=/Volumes/Deegs Drive/Vanessa's Quince

docker compose up -d --build
```

---

## Configuration

| Variable | Default | Description |
|---|---|---|
| `MASTER_API_KEY` | `mxd_master_local_only` | Master API key (required only when `AUTH_REQUIRED=true`) |
| `AUTH_REQUIRED` | `false` | Require API keys for protected endpoints when set to `true` |
| `SONGS_DIR` | `./songs` | Local directory for song storage (can be an external drive path) |
| `SONG_LIBRARY_DIR` | `./songs/library` | Final MP3 destination folder (use this for Serato library imports) |
| `API_KEYS_FILE` | `./api_keys.json` | Path to local JSON file for generated API keys |
| `SONG_CACHE_DIR` | `./songs/cache` | Local on-disk cache directory for MP3 files |
| `SPOTIFY_CLIENT_ID` | *(empty)* | Spotify app client ID for playlist import |
| `SPOTIFY_CLIENT_SECRET` | *(empty)* | Spotify app client secret for OAuth token exchange |
| `SPOTIFY_REDIRECT_URI` | *(empty)* | Redirect URI configured in Spotify app (recommended: `http://127.0.0.1:6493/api/spotify/callback`) |
| `SPOTIFY_TOKEN_FILE` | `./spotify_token.json` | Local file used to persist Spotify OAuth tokens |
| `RATE_LIMIT` | `60/minute` | Global rate limit per IP |
| `SEARCH_CACHE_MAX_SIZE` | `500` | Max entries in the in-memory search cache (LRU) |
| `SONG_CACHE_MAX_MB` | `2048` | Max local disk cache for MP3 files in MB |

---

## Authentication

By default, authentication is disabled for local use (`AUTH_REQUIRED=false`).
When disabled, you can use all endpoints without an API key.

To enable authentication, set:

```env
AUTH_REQUIRED=true
MASTER_API_KEY=your_secret_master_key
```

When auth is enabled, all endpoints (except `/api/health`) require an API key via the `X-API-Key` header.

```bash
curl -H "X-API-Key: YOUR_KEY" http://localhost:6493/api/search ...
```

**Key types:**

| Type | Format | Access |
|---|---|---|
| Master key | Set in `.env` | Full access + admin |
| Regular key | `mxd_live_...` | Search, download, playback |

Regular keys are created/revoked via the admin endpoints.

---

## API Reference

### Spotify Playlists (Optional)

You can connect your Spotify account to browse playlists, resolve tracks to MusicBrainz IDs, and batch-download using the same YouTube + MusicBrainz flow.

Required env vars for Spotify features:

```env
SPOTIFY_CLIENT_ID=...
SPOTIFY_CLIENT_SECRET=...
SPOTIFY_REDIRECT_URI=http://127.0.0.1:6493/api/spotify/callback
```

Use `127.0.0.1` for Spotify local OAuth callbacks to avoid "URI is not secure" issues with non-HTTPS redirects.

Key endpoints:

```
GET  /api/spotify/status
GET  /api/spotify/auth-url
GET  /api/spotify/callback
GET  /api/spotify/playlists
GET  /api/spotify/playlists/{playlist_id}/items?resolve=true
POST /api/spotify/download
POST /api/spotify/logout
```

### Search Songs

```
POST /api/search?fast=false
```

Search MusicBrainz for songs. Returns matching recordings and, when the query matches an artist, the artist with their top songs.

**Request body:**

```json
{
  "query": "green day welcome to paradise"
}
```

Or search with explicit fields:

```json
{
  "title": "Welcome to Paradise",
  "artist": "Green Day"
}
```

**Query parameters:**

| Param | Type | Default | Description |
|---|---|---|---|
| `fast` | bool | `false` | Use fast mode (fewer MB requests, best for typeahead) |

**Response:**

```json
{
  "results": [
    {
      "musicbrainz_id": "c2d8ca4f-503a-452b-ae1e-9646022eaf50",
      "title": "Welcome to Paradise",
      "artist": "Green Day",
      "album": "Dookie",
      "album_art_url": "https://coverartarchive.org/release/.../front-250",
      "youtube_query": "Welcome to Paradise - Green Day",
      "score": 100
    }
  ],
  "artists": [
    {
      "musicbrainz_id": "084308bd-1654-436f-ba03-df6697104e19",
      "name": "Green Day",
      "type": "Group",
      "country": "US",
      "tags": ["rock", "punk", "alternative rock"],
      "top_songs": [
        {
          "musicbrainz_id": "6af5abdb-...",
          "title": "Longview",
          "artist": "Green Day",
          "album": "Dookie",
          "album_art_url": "https://...",
          "youtube_query": "Longview - Green Day",
          "score": 100
        }
      ]
    }
  ]
}
```

### Download a Song

```
POST /api/download
```

Downloads the song from YouTube, saves the MP3 locally, and caches it for fast playback.

**Request body:**

```json
{
  "musicbrainz_id": "c2d8ca4f-503a-452b-ae1e-9646022eaf50"
}
```

**Response:**

```json
{
  "id": "uuid",
  "musicbrainz_id": "c2d8ca4f-...",
  "title": "Welcome to Paradise",
  "artist": "Green Day",
  "album": "Dookie",
  "album_art_url": "https://...",
  "file_path": "/api/cache/c2d8ca4f-...",
  "duration_seconds": 227,
  "genres": ["punk rock", "pop punk"],
  "youtube_video_id": "...",
  "youtube_title": "...",
  "downloaded_at": "2026-03-18T...",
  "status": "downloaded"
}
```

The `file_path` will usually be a local cache URL (`/api/cache/{id}`). If a file has been evicted from cache, the API can return the local absolute path on disk.

### Get a Song

```
GET /api/songs/{musicbrainz_id}
```

Retrieve metadata and a playback URL for a previously downloaded song.

### Stream a Cached Song

```
GET /api/cache/{file_key}?key=YOUR_API_KEY
```

Serves the MP3 directly from local disk. The `key` query parameter is an alternative to the `X-API-Key` header (useful for `<audio>` elements that can't set headers).

### Cache Stats

```
GET /api/cache-stats
```

```json
{
  "cached_songs": 12,
  "used_mb": 54.3,
  "max_mb": 2048.0
}
```

### Health Check

```
GET /api/health
```

No authentication required.

```json
{
  "status": "healthy",
  "songs_count": 12,
  "storage_used_mb": 54.0,
  "yt_dlp_version": "2026.03.17"
}
```

### Admin: Manage API Keys

**List keys:**

```
GET /api/admin/keys
```

**Create a key:**

```
POST /api/admin/keys
```

```json
{ "name": "my-app" }
```

**Revoke a key:**

```
DELETE /api/admin/keys
```

```json
{ "key": "mxd_live_..." }
```

All admin endpoints require the master API key.

---

## Local Library Layout

Songs are saved to `SONG_LIBRARY_DIR` as MP3 files:

```text
{artist} - {title}.mp3
```

If a filename already exists, the API appends ` (2)`, ` (3)`, etc.

Each file is tagged with ID3 metadata (`title`, `artist`, `album`, and `genre` when available), so DJ software like Serato can populate columns correctly.
When album art is available from MusicBrainz metadata, it is embedded into the MP3 as cover art.

Metadata is stored in a local JSON manifest at:

```text
{SONGS_DIR}/manifest.json
```

This format is friendly for importing into DJ software like Serato.

---

## Architecture

```
Client  ->  FastAPI  ->  MusicBrainz (search/metadata)
                     ->  YouTube (download via yt-dlp)
                     ->  Local MP3 library (persistent storage)
                     ->  Local disk cache (fast playback)
```

- **Search cache**: In-memory LRU with 1-hour TTL. Configurable max size.
- **Song cache**: On-disk LRU. MP3s served directly from local cache. Configurable max size in MB.
- **Smart search**: Tries title/artist field splits in both directions to find the best match. Parallel MusicBrainz queries.
- **Artist detection**: When a query matches an artist, returns the artist card with their top songs ranked by popularity.
