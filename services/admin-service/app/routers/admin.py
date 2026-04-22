import json

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.auth import AdminAccessChecker, AdminAccessDenied
from app.config import Settings
from app.graph import get_graph_mermaid
from app.schemas import AdminChatRequest, AdminChatResponse
from app.service import AdminService


router = APIRouter(prefix="/admin", tags=["admin"])


def _service() -> AdminService:
    return AdminService()


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "").strip()
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _require_admin_token(
    request: Request,
    *,
    access_token: str | None = None,
    authorization: str | None = None,
) -> str:
    token = access_token
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    checker = AdminAccessChecker(Settings.from_env())
    try:
        checker.require_admin(
            token=token,
            path=request.url.path,
            method=request.method,
            client_ip=_client_ip(request),
        )
    except AdminAccessDenied as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    return token or ""


@router.post("/chat", response_model=AdminChatResponse)
def chat(
    payload: AdminChatRequest,
    request: Request,
    authorization: str | None = Header(default=None),
) -> AdminChatResponse:
    _require_admin_token(request, access_token=payload.access_token, authorization=authorization)
    return _service().chat(payload)


@router.post("/chat/stream")
def chat_stream(
    payload: AdminChatRequest,
    request: Request,
    authorization: str | None = Header(default=None),
) -> StreamingResponse:
    _require_admin_token(request, access_token=payload.access_token, authorization=authorization)

    def _iter():
        for event in _service().chat_events(payload):
            yield json.dumps(event) + "\n"

    return StreamingResponse(_iter(), media_type="application/x-ndjson")


@router.get("/graph")
def get_graph(
    request: Request,
    authorization: str | None = Header(default=None),
) -> dict:
    _require_admin_token(request, authorization=authorization)
    return {
        "status": "ok",
        "format": "mermaid",
        "graph": get_graph_mermaid(Settings.from_env()),
    }
