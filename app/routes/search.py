from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth import validate_api_key
from app.models.schemas import SearchRequest, SearchResponse
from app.services.musicbrainz import search_recordings

router = APIRouter(tags=["search"])


@router.post("/search", response_model=SearchResponse)
def search(
    body: SearchRequest,
    fast: bool = Query(False, description="Single MB request, best for real-time/typeahead"),
    _key: str = Depends(validate_api_key),
):
    if not body.query.strip() and not (body.title and body.artist):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Provide query or both title and artist")

    results, artists = search_recordings(
        query=body.query.strip(),
        title=body.title,
        artist=body.artist,
        fast=fast,
    )
    return SearchResponse(results=results, artists=artists)
