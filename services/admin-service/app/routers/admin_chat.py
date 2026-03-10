from fastapi import APIRouter, Header, HTTPException

from app.config import Settings
from app.errors import (
    AdminServiceError,
    AuthorizationError,
    ConfigurationError,
    ToolExecutionError,
    UpstreamServiceError,
)
from app.schemas import AdminChatRequest, AdminChatResponse
from app.service import AdminService


router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/chat", response_model=AdminChatResponse)
def admin_chat(
    payload: AdminChatRequest,
    authorization: str | None = Header(default=None),
) -> AdminChatResponse:
    try:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
        access_token = authorization[7:]
        service = AdminService(settings=Settings.from_env())
        return service.chat(payload, access_token=access_token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except AuthorizationError as exc:
        detail = str(exc)
        status_code = 401 if "token" in detail.lower() else 403
        raise HTTPException(status_code=status_code, detail=detail) from exc
    except UpstreamServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ToolExecutionError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except AdminServiceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
