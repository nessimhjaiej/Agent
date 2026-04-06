from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from app.config import Settings
from app.errors import ConfigurationError, IngestionServiceError, UpstreamServiceError
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
def list_documents(user_id: str | None = Query(default=None, min_length=1)) -> ListDocumentsResponse:
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
def update_document_status(document_id: str, payload: UpdateDocumentStatusRequest) -> DocumentResponse:
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
def get_document_signed_url(document_id: str, expires_in: int | None = Query(default=None, gt=0)) -> SignedUrlResponse:
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
def delete_document(document_id: str) -> DeleteDocumentResponse:
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
