from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import validate_api_key
from app.models.schemas import SongRecord
from app.services.storage import get_song_by_mbid

router = APIRouter(tags=["songs"])


@router.get("/songs/{musicbrainz_id}", response_model=SongRecord)
def get_song(
    musicbrainz_id: str,
    _key: str = Depends(validate_api_key),
):
    record = get_song_by_mbid(musicbrainz_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Song with id '{musicbrainz_id}' not found",
        )
    return record
