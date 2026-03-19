import json
import secrets
import time
from pathlib import Path
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, status

from app.config import (
    SPOTIFY_CLIENT_ID,
    SPOTIFY_CLIENT_SECRET,
    SPOTIFY_REDIRECT_URI,
    SPOTIFY_TOKEN_FILE,
)

SPOTIFY_AUTH_URL = "https://accounts.spotify.com/authorize"
SPOTIFY_TOKEN_URL = "https://accounts.spotify.com/api/token"
SPOTIFY_API_BASE = "https://api.spotify.com/v1"
SPOTIFY_SCOPES = ["playlist-read-private", "playlist-read-collaborative"]

_pending_states: set[str] = set()


def is_configured() -> bool:
    return bool(SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET and SPOTIFY_REDIRECT_URI)


def auth_url() -> str:
    _ensure_configured()
    state = secrets.token_urlsafe(24)
    _pending_states.add(state)
    params = {
        "response_type": "code",
        "client_id": SPOTIFY_CLIENT_ID,
        "scope": " ".join(SPOTIFY_SCOPES),
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "state": state,
    }
    return f"{SPOTIFY_AUTH_URL}?{urlencode(params)}"


def complete_oauth_callback(code: str, state: str) -> None:
    _ensure_configured()
    if not state or state not in _pending_states:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid Spotify OAuth state")
    _pending_states.discard(state)

    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": SPOTIFY_REDIRECT_URI,
        "client_id": SPOTIFY_CLIENT_ID,
        "client_secret": SPOTIFY_CLIENT_SECRET,
    }
    try:
        with httpx.Client(timeout=20) as client:
            res = client.post(SPOTIFY_TOKEN_URL, data=data)
        if res.status_code != 200:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Spotify token exchange failed: {res.text}")
        payload = res.json()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Spotify token exchange error: {exc}")

    payload["obtained_at"] = int(time.time())
    _save_tokens(payload)


def disconnect() -> None:
    token_path = Path(SPOTIFY_TOKEN_FILE)
    try:
        token_path.unlink(missing_ok=True)
    except OSError:
        pass


def status_info() -> dict:
    configured = is_configured()
    if not configured:
        return {"configured": False, "connected": False}
    tokens = _load_tokens()
    if not tokens or not tokens.get("access_token"):
        return {"configured": True, "connected": False}
    profile = _get_me()
    return {
        "configured": True,
        "connected": True,
        "display_name": profile.get("display_name"),
        "id": profile.get("id"),
    }


def list_playlists() -> list[dict]:
    items = _paginate("/me/playlists", {"limit": 50})
    playlists = []
    for p in items:
        owner = (p.get("owner") or {}).get("display_name")
        playlists.append(
            {
                "id": p.get("id"),
                "name": p.get("name"),
                "description": p.get("description") or "",
                "tracks_total": (p.get("tracks") or {}).get("total", 0),
                "owner": owner,
                "image_url": ((p.get("images") or [{}])[0] or {}).get("url"),
            }
        )
    return playlists


def playlist_tracks(playlist_id: str) -> list[dict]:
    endpoint = f"/playlists/{playlist_id}/items"
    fields = "items(track(id,name,artists(name),album(name,images),external_ids(isrc))),next,total"
    items = _paginate(endpoint, {"limit": 100, "fields": fields})
    tracks: list[dict] = []
    for item in items:
        track = item.get("track") or {}
        if not track:
            continue
        artists = [a.get("name") for a in track.get("artists", []) if a.get("name")]
        artist = ", ".join(artists)
        if not track.get("id") or not track.get("name") or not artist:
            continue
        tracks.append(
            {
                "spotify_track_id": track.get("id"),
                "title": track.get("name"),
                "artist": artist,
                "album": (track.get("album") or {}).get("name"),
                "album_art_url": (((track.get("album") or {}).get("images") or [{}])[0] or {}).get("url"),
                "isrc": ((track.get("external_ids") or {}).get("isrc")),
            }
        )
    return tracks


def _paginate(path: str, params: dict) -> list[dict]:
    all_items: list[dict] = []
    url = f"{SPOTIFY_API_BASE}{path}"
    query = params.copy()

    while url:
        payload = _get(url, params=query)
        all_items.extend(payload.get("items", []))
        url = payload.get("next")
        query = None
    return all_items


def _get_me() -> dict:
    return _get(f"{SPOTIFY_API_BASE}/me")


def _get(url: str, params: dict | None = None) -> dict:
    token = _access_token()
    headers = {"Authorization": f"Bearer {token}"}
    try:
        with httpx.Client(timeout=20) as client:
            res = client.get(url, headers=headers, params=params)
        if res.status_code == 401:
            _refresh_access_token(force=True)
            headers = {"Authorization": f"Bearer {_access_token()}"}
            with httpx.Client(timeout=20) as client:
                res = client.get(url, headers=headers, params=params)
        if res.status_code != 200:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Spotify API error: {res.text}")
        return res.json()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Spotify API request failed: {exc}")


def _access_token() -> str:
    _ensure_configured()
    token = _refresh_access_token(force=False)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Spotify is not connected")
    return token


def _refresh_access_token(force: bool = False) -> str:
    tokens = _load_tokens()
    if not tokens:
        return ""
    access_token = tokens.get("access_token", "")
    expires_in = int(tokens.get("expires_in", 0))
    obtained_at = int(tokens.get("obtained_at", 0))
    still_valid = access_token and (time.time() < (obtained_at + expires_in - 60))
    if still_valid and not force:
        return access_token

    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        return ""
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": SPOTIFY_CLIENT_ID,
        "client_secret": SPOTIFY_CLIENT_SECRET,
    }
    try:
        with httpx.Client(timeout=20) as client:
            res = client.post(SPOTIFY_TOKEN_URL, data=data)
        if res.status_code != 200:
            return ""
        refreshed = res.json()
    except Exception:
        return ""

    tokens["access_token"] = refreshed.get("access_token", access_token)
    tokens["expires_in"] = refreshed.get("expires_in", expires_in)
    tokens["obtained_at"] = int(time.time())
    if refreshed.get("refresh_token"):
        tokens["refresh_token"] = refreshed["refresh_token"]
    _save_tokens(tokens)
    return tokens.get("access_token", "")


def _load_tokens() -> dict:
    path = Path(SPOTIFY_TOKEN_FILE)
    if not path.exists():
        return {}
    try:
        with open(path) as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _save_tokens(data: dict) -> None:
    path = Path(SPOTIFY_TOKEN_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _ensure_configured() -> None:
    if not is_configured():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Spotify is not configured. Set SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI.",
        )
