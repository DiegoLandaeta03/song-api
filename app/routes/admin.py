from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import (
    create_api_key,
    list_api_keys,
    revoke_api_key,
    validate_api_key,
)
from app.config import MASTER_API_KEY
from app.models.schemas import ApiKeyEntry, CreateKeyRequest, RevokeKeyRequest

router = APIRouter(prefix="/admin", tags=["admin"])


def require_master(x_api_key: str = Depends(validate_api_key)) -> str:
    if x_api_key != MASTER_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Master API key required for admin operations",
        )
    return x_api_key


@router.get("/keys", response_model=list[ApiKeyEntry])
def get_keys(_key: str = Depends(require_master)):
    return list_api_keys()


@router.post("/keys", response_model=ApiKeyEntry, status_code=status.HTTP_201_CREATED)
def create_key(body: CreateKeyRequest, _key: str = Depends(require_master)):
    return create_api_key(body.name)


@router.delete("/keys", status_code=status.HTTP_204_NO_CONTENT)
def revoke_key(body: RevokeKeyRequest, _key: str = Depends(require_master)):
    found = revoke_api_key(body.key)
    if not found:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Key not found")
