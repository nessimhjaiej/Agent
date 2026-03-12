import logging
from time import perf_counter

from fastapi import APIRouter, HTTPException

from app.config import Settings
from app.errors import ConfigurationError, EmbeddingProviderError, EmbeddingServiceError, VectorStoreError
from app.schemas import (
    IndexDocumentRequest,
    IndexDocumentResponse,
    IndexChunksRequest,
    IndexedChunkResponse,
    IndexChunksResponse,
    RemoveDocumentRequest,
    RemoveDocumentResponse,
)
from app.service import EmbeddingService


router = APIRouter(prefix="/embedding", tags=["embedding"])
logger = logging.getLogger(__name__)


@router.post(
    "/index-chunks",
    response_model=IndexChunksResponse,
    summary="Embed and index chunks",
    description=(
        "Receives preprocessed chunks, generates embeddings with OpenAI, "
        "and upserts vectors + metadata into Weaviate."
    ),
    responses={
        200: {"description": "Chunks processed and indexing results returned."},
        400: {"description": "Invalid service/runtime configuration."},
        422: {"description": "Invalid request payload format."},
        502: {"description": "Embedding provider error (OpenAI)."},
        503: {"description": "Vector store error (Weaviate unavailable/schema issue)."},
        500: {"description": "Unexpected internal service error."},
    },
)
def index_chunks(payload: IndexChunksRequest) -> IndexChunksResponse:
    started_at = perf_counter()
    try:
        settings = Settings.from_env()
        service = EmbeddingService(settings=settings)
        results = service.index_chunks(payload.chunks)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except VectorStoreError as exc:
        logger.exception("embedding.index_chunks.vector_store_error")
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except EmbeddingProviderError as exc:
        logger.exception("embedding.index_chunks.embedding_provider_error")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except EmbeddingServiceError as exc:
        logger.exception("embedding.index_chunks.internal_error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    response_items = [
        IndexedChunkResponse(chunk_id=item.chunk_id, indexed=item.indexed, reason=item.reason)
        for item in results
    ]
    duplicate_count = sum(1 for item in response_items if item.reason == "duplicate_chunk_id_in_request")
    indexed_count = sum(1 for item in response_items if item.indexed)
    failed_count = len(response_items) - indexed_count
    duration_ms = int((perf_counter() - started_at) * 1000)

    logger.info(
        "embedding.index_chunks.completed requested=%d indexed=%d failed=%d duplicates=%d duration_ms=%d collection=%s",
        len(payload.chunks),
        indexed_count,
        failed_count,
        duplicate_count,
        duration_ms,
        settings.weaviate_collection,
    )

    return IndexChunksResponse(
        status="ok",
        collection=settings.weaviate_collection,
        total_count=len(response_items),
        indexed_count=indexed_count,
        results=response_items,
    )


@router.post("/index-document", response_model=IndexDocumentResponse)
def index_document(payload: IndexDocumentRequest) -> IndexDocumentResponse:
    try:
        settings = Settings.from_env()
        result = EmbeddingService(settings=settings).index_document(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except VectorStoreError as exc:
        logger.exception("embedding.index_document.vector_store_error")
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except EmbeddingProviderError as exc:
        logger.exception("embedding.index_document.embedding_provider_error")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except EmbeddingServiceError as exc:
        logger.exception("embedding.index_document.internal_error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return IndexDocumentResponse(
        status=result.status,
        document_id=result.document_id,
        storage_path=result.storage_path,
        chunks_count=result.chunks_count,
        indexed_count=result.indexed_count,
        embedded=result.embedded,
        message=result.message,
    )


@router.post("/remove-document", response_model=RemoveDocumentResponse)
def remove_document(payload: RemoveDocumentRequest) -> RemoveDocumentResponse:
    try:
        settings = Settings.from_env()
        result = EmbeddingService(settings=settings).remove_document(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ConfigurationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except VectorStoreError as exc:
        logger.exception("embedding.remove_document.vector_store_error")
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except EmbeddingServiceError as exc:
        logger.exception("embedding.remove_document.internal_error")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return RemoveDocumentResponse(
        status=result.status,
        document_id=result.document_id,
        storage_path=result.storage_path,
        matched_objects_count=result.matched_objects_count,
        deleted_count=result.deleted_count,
    )
