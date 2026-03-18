from fastapi import APIRouter
import yt_dlp

from app.models.schemas import HealthResponse
from app.services.storage import songs_count, storage_used_mb

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check():
    return HealthResponse(
        status="healthy",
        songs_count=songs_count(),
        storage_used_mb=storage_used_mb(),
        yt_dlp_version=yt_dlp.version.__version__,
    )
