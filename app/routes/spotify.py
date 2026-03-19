from fastapi import APIRouter, Body, Depends, Query, status
from fastapi.responses import HTMLResponse

from app.auth import validate_api_key
from app.services.download_manager import download_musicbrainz_song
from app.services.musicbrainz import search_recordings
from app.services import spotify as spotify_service

router = APIRouter(prefix="/spotify", tags=["spotify"])


@router.get("/status")
def spotify_status(_key: str = Depends(validate_api_key)):
    return spotify_service.status_info()


@router.get("/auth-url")
def spotify_auth_url(_key: str = Depends(validate_api_key)):
    return {"auth_url": spotify_service.auth_url()}


@router.get("/callback", response_class=HTMLResponse)
def spotify_callback(code: str = "", state: str = ""):
    spotify_service.complete_oauth_callback(code=code, state=state)
    return """
    <html>
      <body style="font-family: sans-serif; padding: 24px;">
        <h3>Spotify connected</h3>
        <p>You can close this window.</p>
        <script>
          if (window.opener) {
            window.opener.postMessage({ type: "spotify_connected" }, "*");
          }
          setTimeout(() => window.close(), 500);
        </script>
      </body>
    </html>
    """


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def spotify_logout(_key: str = Depends(validate_api_key)):
    spotify_service.disconnect()


@router.get("/playlists")
def spotify_playlists(_key: str = Depends(validate_api_key)):
    return {"items": spotify_service.list_playlists()}


@router.get("/playlists/{playlist_id}/items")
@router.get("/playlists/{playlist_id}/tracks", deprecated=True)
def spotify_playlist_tracks(
    playlist_id: str,
    resolve: bool = Query(True, description="Resolve tracks against MusicBrainz"),
    _key: str = Depends(validate_api_key),
):
    tracks = spotify_service.playlist_tracks(playlist_id)
    total_tracks = len(tracks)
    if not resolve:
        print(f"[spotify] playlist={playlist_id} fetched_tracks={total_tracks} resolve=false")
        return {"items": tracks, "total": total_tracks, "matched": 0, "unmatched": total_tracks}

    resolved_items = []
    matched = 0
    for t in tracks:
        mbid, match_score = _resolve_musicbrainz_id(t["title"], t["artist"])
        t["musicbrainz_id"] = mbid
        t["match_score"] = match_score
        if mbid:
            matched += 1
        resolved_items.append(t)
    unmatched = total_tracks - matched
    print(
        f"[spotify] playlist={playlist_id} fetched_tracks={total_tracks} "
        f"matched={matched} unmatched={unmatched} resolve=true"
    )
    return {
        "items": resolved_items,
        "total": total_tracks,
        "matched": matched,
        "unmatched": unmatched,
    }


@router.post("/download")
def spotify_download_tracks(
    body: dict = Body(default={}),
    _key: str = Depends(validate_api_key),
):
    """
    Download selected Spotify tracks via MusicBrainz -> YouTube pipeline.
    body = { "items": [ { musicbrainz_id?, title, artist } ] }
    """
    items = body.get("items") or []
    if not isinstance(items, list) or not items:
        return {"items": [], "total": 0, "success": 0, "failed": 0}

    results = []
    success = 0
    failed = 0
    for item in items:
        title = (item.get("title") or "").strip()
        artist = (item.get("artist") or "").strip()
        mbid = (item.get("musicbrainz_id") or "").strip()

        if not mbid and title and artist:
            mbid, _score = _resolve_musicbrainz_id(title=title, artist=artist)

        if not mbid:
            failed += 1
            results.append(
                {
                    "title": title,
                    "artist": artist,
                    "status": "failed",
                    "error": "No MusicBrainz match found",
                }
            )
            continue

        try:
            song = download_musicbrainz_song(mbid)
            success += 1
            results.append(
                {
                    "title": song.title,
                    "artist": song.artist,
                    "musicbrainz_id": mbid,
                    "status": "downloaded",
                    "song": song.model_dump(),
                }
            )
        except Exception as exc:
            failed += 1
            results.append(
                {
                    "title": title,
                    "artist": artist,
                    "musicbrainz_id": mbid,
                    "status": "failed",
                    "error": str(exc),
                }
            )

    return {
        "items": results,
        "total": len(items),
        "success": success,
        "failed": failed,
    }


def _resolve_musicbrainz_id(title: str, artist: str) -> tuple[str | None, int]:
    try:
        results, _artists = search_recordings(
            query=f"{artist} {title}",
            title=title,
            artist=artist,
            limit=5,
            fast=True,
        )
        if not results:
            return None, 0
        best = results[0]
        return best.musicbrainz_id, int(best.score)
    except Exception:
        return None, 0
