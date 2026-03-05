from fastapi import APIRouter, HTTPException

from app.config import Settings
from app.errors import ConfigurationError, IngestionServiceError, UpstreamServiceError
from app.schemas import (
    IndexDocumentRequest,
    IndexDocumentResponse,
    IngestionDocumentResponse,
    RunIngestionRequest,
    RunIngestionResponse,
)
from app.service import IngestionService


router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.post("/run", response_model=RunIngestionResponse)
def run_ingestion(payload: RunIngestionRequest) -> RunIngestionResponse:
    try:
        service = IngestionService(settings=Settings.from_env())
        result = service.run_ingestion(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except UpstreamServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except IngestionServiceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return RunIngestionResponse(
        status="ok",
        documents_processed=result.documents_processed,
        documents_failed=result.documents_failed,
        chunks_total=result.chunks_total,
        chunks_indexed=result.chunks_indexed,
        failed_files=result.failed_files,
        results=[
            IngestionDocumentResponse(
                file_path=item.file_path,
                source_path=item.source_path,
                chunks_count=item.chunks_count,
                indexed_count=item.indexed_count,
                status=item.status,
                error=item.error,
            )
            for item in result.results
        ],
    )


@router.post("/index-document", response_model=IndexDocumentResponse)
def index_document(payload: IndexDocumentRequest) -> IndexDocumentResponse:
    try:
        service = IngestionService(settings=Settings.from_env())
        result = service.index_document(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except UpstreamServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except IngestionServiceError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return IndexDocumentResponse(
        status=result.status,
        source_path=result.source_path,
        exists_in_weaviate=result.exists_in_weaviate,
        indexed=result.indexed,
        chunks_count=result.chunks_count,
        indexed_count=result.indexed_count,
        message=result.message,
    )
