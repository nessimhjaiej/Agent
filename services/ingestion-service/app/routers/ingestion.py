import httpx
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile

from app.config import Settings
from app.errors import AuthorizationError, ConfigurationError, IngestionServiceError, UpstreamServiceError
from app.models import UpdateDocumentStatusParams, UploadDocumentParams
from app.schemas import (
    DeleteDocumentResponse,
    DocumentResponse,
    ListDocumentsResponse,
    SignedUrlResponse,
    UpdateDocumentStatusRequest,
)
from app.service import IngestionService


router = APIRouter(prefix="/ingestion", tags=["ingestion"])


def _service() -> IngestionService:
    return IngestionService(settings=Settings.from_env())


def _get_current_user(authorization: str | None) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    settings = Settings.from_env()
    try:
        with httpx.Client(timeout=settings.http_timeout_seconds) as client:
            response = client.get(
                f"{settings.supabase_url.rstrip('/')}/auth/v1/user",
                headers={
                    "apikey": settings.supabase_key,
                    "Authorization": f"Bearer {token}",
                },
            )
        if response.status_code >= 400:
            raise AuthorizationError("Invalid or expired token")
        payload = response.json()
    except AuthorizationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Unable to verify token: {exc}") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload


def _require_verified_user(authorization: str | None = Header(default=None)) -> dict:
    user = _get_current_user(authorization)
    app_metadata = user.get("app_metadata") if isinstance(user.get("app_metadata"), dict) else {}
    user_metadata = user.get("user_metadata") if isinstance(user.get("user_metadata"), dict) else {}
    role = str(user_metadata.get("role") or "user")
    validated = role == "admin" or app_metadata.get("account_validated") is not False
    blocked = app_metadata.get("account_blocked") is True or bool(user.get("banned_until"))
    if blocked:
        raise HTTPException(status_code=403, detail="Account is blocked")
    if not validated:
        raise HTTPException(status_code=403, detail="Account pending admin validation")
    return user


def _require_admin_user(authorization: str | None = Header(default=None)) -> dict:
    user = _require_verified_user(authorization)
    user_metadata = user.get("user_metadata") if isinstance(user.get("user_metadata"), dict) else {}
    role = str(user_metadata.get("role") or "user")
    if role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def _document_response(document) -> DocumentResponse:
    return DocumentResponse(
        id=document.id,
        user_id=document.user_id,
        original_name=document.original_name,
        storage_path=document.storage_path,
        status=document.status,
        embedded=document.embedded,
        size_bytes=document.size_bytes,
        created_at=document.created_at,
        embedded_at=document.embedded_at,
    )


@router.get("/documents", response_model=ListDocumentsResponse)
def list_documents(
    user_id: str | None = Query(default=None, min_length=1),
    _admin_user: dict = Depends(_require_admin_user),
) -> ListDocumentsResponse:
    try:
        documents = _service().list_documents(user_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except UpstreamServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except IngestionServiceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return ListDocumentsResponse(
        status="ok",
        documents=[_document_response(document) for document in documents],
    )


@router.post("/documents/upload", response_model=DocumentResponse)
async def upload_document(
    user_id: str = Form(..., min_length=1),
    file: UploadFile = File(...),
    _admin_user: dict = Depends(_require_admin_user),
) -> DocumentResponse:
    try:
        content = await file.read()
        document = _service().upload_document(
            UploadDocumentParams(
                user_id=user_id,
                original_name=file.filename or "document",
                content=content,
                content_type=file.content_type or "application/octet-stream",
                size_bytes=len(content),
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except UpstreamServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except IngestionServiceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return _document_response(document)


@router.post("/documents/{document_id}/status", response_model=DocumentResponse)
def update_document_status(
    document_id: str,
    payload: UpdateDocumentStatusRequest,
    _admin_user: dict = Depends(_require_admin_user),
) -> DocumentResponse:
    try:
        document = _service().update_document_status(
            UpdateDocumentStatusParams(
                document_id=document_id,
                target_status=payload.target_status,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ConfigurationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UpstreamServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except IngestionServiceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return _document_response(document)


@router.get("/documents/{document_id}/signed-url", response_model=SignedUrlResponse)
def get_document_signed_url(
    document_id: str,
    expires_in: int | None = Query(default=None, gt=0),
    _verified_user: dict = Depends(_require_verified_user),
) -> SignedUrlResponse:
    try:
        result = _service().get_document_signed_url(document_id=document_id, expires_in=expires_in)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ConfigurationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UpstreamServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except IngestionServiceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return SignedUrlResponse(
        status="ok",
        document_id=result.document_id,
        storage_path=result.storage_path,
        signed_url=result.signed_url,
        expires_in=result.expires_in,
    )


@router.get("/documents/signed-url/by-storage-path", response_model=SignedUrlResponse)
def get_document_signed_url_by_storage_path(
    storage_path: str = Query(..., min_length=1),
    expires_in: int | None = Query(default=None, gt=0),
    _verified_user: dict = Depends(_require_verified_user),
) -> SignedUrlResponse:
    try:
        result = _service().get_document_signed_url_by_storage_path(
            storage_path=storage_path,
            expires_in=expires_in,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ConfigurationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UpstreamServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except IngestionServiceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return SignedUrlResponse(
        status="ok",
        document_id=result.document_id,
        storage_path=result.storage_path,
        signed_url=result.signed_url,
        expires_in=result.expires_in,
    )


@router.delete("/documents/{document_id}", response_model=DeleteDocumentResponse)
def delete_document(
    document_id: str,
    _admin_user: dict = Depends(_require_admin_user),
) -> DeleteDocumentResponse:
    try:
        result = _service().delete_document(document_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ConfigurationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UpstreamServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except IngestionServiceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return DeleteDocumentResponse(
        status=result.status,
        document_id=result.document_id,
        storage_path=result.storage_path,
    )
