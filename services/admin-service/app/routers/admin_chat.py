from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.config import Settings
from app.errors import (
    AdminServiceError,
    ConfigurationError,
    ToolExecutionError,
    UpstreamServiceError,
)
from app.schemas import AdminChatRequest, AdminChatResponse
from app.service import AdminService


router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/chat", response_model=AdminChatResponse)
def admin_chat(payload: AdminChatRequest) -> AdminChatResponse:
    try:
        service = AdminService(settings=Settings.from_env())
        return service.chat(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except UpstreamServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ToolExecutionError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except AdminServiceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/chat/stream")
def admin_chat_stream(payload: AdminChatRequest) -> StreamingResponse:
    service = AdminService(settings=Settings.from_env())
    return StreamingResponse(
        service.stream_chat(payload),
        media_type="application/x-ndjson",
    )
