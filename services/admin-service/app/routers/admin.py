import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.config import Settings
from app.graph import get_graph_mermaid
from app.schemas import AdminChatRequest, AdminChatResponse
from app.service import AdminService


router = APIRouter(prefix="/admin", tags=["admin"])


def _service() -> AdminService:
    return AdminService()


@router.post("/chat", response_model=AdminChatResponse)
def chat(payload: AdminChatRequest) -> AdminChatResponse:
    return _service().chat(payload)


@router.post("/chat/stream")
def chat_stream(payload: AdminChatRequest) -> StreamingResponse:
    def _iter():
        for event in _service().chat_events(payload):
            yield json.dumps(event) + "\n"

    return StreamingResponse(_iter(), media_type="application/x-ndjson")


@router.get("/graph")
def get_graph() -> dict:
    return {
        "status": "ok",
        "format": "mermaid",
        "graph": get_graph_mermaid(Settings.from_env()),
    }
