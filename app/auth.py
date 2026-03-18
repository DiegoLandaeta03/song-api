import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import Header, HTTPException, status

from app.config import API_KEYS_FILE, AUTH_REQUIRED, MASTER_API_KEY


def _load_keys() -> dict:
    path = Path(API_KEYS_FILE)
    if not path.exists():
        return {"keys": []}
    with open(path) as f:
        return json.load(f)


def _save_keys(data: dict) -> None:
    path = Path(API_KEYS_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def validate_api_key(x_api_key: Optional[str] = Header(default=None)) -> str:
    if not AUTH_REQUIRED:
        return x_api_key or "auth-disabled"

    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )

    # Master key always works
    if x_api_key == MASTER_API_KEY:
        return x_api_key

    data = _load_keys()
    for entry in data["keys"]:
        if entry["key"] == x_api_key and entry["is_active"]:
            return x_api_key

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid or inactive API key",
    )


def _is_valid_key(key: str) -> bool:
    """Check if a key is valid without raising exceptions."""
    if not AUTH_REQUIRED:
        return True

    if not key:
        return False
    if key == MASTER_API_KEY:
        return True
    data = _load_keys()
    return any(e["key"] == key and e["is_active"] for e in data["keys"])


def create_api_key(name: str) -> dict:
    key = f"mxd_live_{secrets.token_urlsafe(32)}"
    entry = {
        "key": key,
        "name": name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "is_active": True,
    }
    data = _load_keys()
    data["keys"].append(entry)
    _save_keys(data)
    return entry


def revoke_api_key(key: str) -> bool:
    data = _load_keys()
    for entry in data["keys"]:
        if entry["key"] == key:
            entry["is_active"] = False
            _save_keys(data)
            return True
    return False


def list_api_keys() -> list:
    data = _load_keys()
    return data["keys"]
