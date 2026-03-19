from fastapi import APIRouter, Depends, status

from app.auth import validate_api_key
from app.models.schemas import DownloadRequest, SongRecord
from app.services.download_manager import download_musicbrainz_song

router = APIRouter(tags=["download"])


@router.post("/download", response_model=SongRecord, status_code=status.HTTP_200_OK)
def download(
    body: DownloadRequest,
    _key: str = Depends(validate_api_key),
):
    return download_musicbrainz_song(body.musicbrainz_id)
