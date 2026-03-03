from fastapi import APIRouter

from app.schemas import SearchRequest, SearchResponse
from app.service import RetrievalService


router = APIRouter(prefix="/retrieval", tags=["retrieval"])


@router.post("/search", response_model=SearchResponse)
def search(payload: SearchRequest) -> SearchResponse:
    service = RetrievalService()
    return service.search(payload)
