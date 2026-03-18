# Mixd Song API

A self-hosted song search and download API powered by MusicBrainz, YouTube, and Supabase. Search for songs by title/artist, download them as MP3s, and serve them with local caching for fast playback.

## Quick Start

### Prerequisites

- Docker & Docker Compose
- A [Supabase](https://supabase.com) project with:
  - A `songs` table (see [Database Setup](#database-setup))
  - A `song-files` storage bucket

### Run

```bash
cp .env.example .env
# Edit .env with your keys (see Configuration below)

docker compose up -d --build
```

The API will be available at `http://localhost:6493`. A web UI is served at the root (`/`).

---

## Configuration

| Variable | Default | Description |
|---|---|---|
| `MASTER_API_KEY` | *(required)* | Admin API key for managing sub-keys |
| `SUPABASE_URL` | *(required)* | Your Supabase project URL |
| `SUPABASE_SERVICE_KEY` | *(required)* | Supabase service role key |
| `SONGS_DIR` | `/songs` | Local directory for song storage |
| `RATE_LIMIT` | `60/minute` | Global rate limit per IP |
| `SEARCH_CACHE_MAX_SIZE` | `500` | Max entries in the in-memory search cache (LRU) |
| `SONG_CACHE_MAX_MB` | `2048` | Max local disk cache for MP3 files in MB |

---

## Authentication

All endpoints (except `/api/health`) require an API key via the `X-API-Key` header.

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

Downloads the song from YouTube, uploads to Supabase Storage, and caches locally.

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

The `file_path` will be a local cache URL (`/api/cache/{id}`) if cached, or a Supabase signed URL otherwise.

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

## Database Setup

Create a `songs` table in your Supabase project:

```sql
CREATE TABLE songs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  musicbrainz_id TEXT UNIQUE,
  title TEXT NOT NULL,
  artist TEXT NOT NULL,
  album TEXT,
  album_art_url TEXT,
  file_key TEXT NOT NULL UNIQUE,
  duration_seconds INTEGER,
  youtube_video_id TEXT,
  youtube_title TEXT,
  genres TEXT[] DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_songs_mbid ON songs(musicbrainz_id);
```

Create a `song-files` storage bucket (public or private, the API uses signed URLs).

---

## Architecture

```
Client  ->  FastAPI  ->  MusicBrainz (search/metadata)
                     ->  YouTube (download via yt-dlp)
                     ->  Supabase Storage (persistent MP3 storage)
                     ->  Local disk cache (fast playback)
```

- **Search cache**: In-memory LRU with 1-hour TTL. Configurable max size.
- **Song cache**: On-disk LRU. MP3s served directly, bypassing Supabase for cached songs. Configurable max size in MB.
- **Smart search**: Tries title/artist field splits in both directions to find the best match. Parallel MusicBrainz queries.
- **Artist detection**: When a query matches an artist, returns the artist card with their top songs ranked by popularity.
