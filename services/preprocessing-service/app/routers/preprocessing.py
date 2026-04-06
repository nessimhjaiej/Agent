from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from app.config import Settings
from app.schemas import ChunkResponse, ProcessSourceRequest, ProcessSourceResponse
from app.service import PreprocessingService


router = APIRouter(prefix="/preprocessing", tags=["preprocessing"])


@router.post("/process-source", response_model=ProcessSourceResponse)
def process_source(payload: ProcessSourceRequest) -> ProcessSourceResponse:
    service = PreprocessingService(Settings.from_env())
    try:
        chunks = service.process_source(
            source_path=payload.source_path,
            document_id=payload.document_id,
            source_type=payload.source_type,
            chunk_strategy=payload.chunk_strategy,
            chunk_size=payload.chunk_size,
            chunk_overlap=payload.chunk_overlap,
            late_size_multiplier=payload.late_size_multiplier,
            late_overlap_multiplier=payload.late_overlap_multiplier,
        )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ImportError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    chunk_payload = [ChunkResponse(**asdict(chunk)) for chunk in chunks]
    return ProcessSourceResponse(
        status="ok",
        chunk_count=len(chunk_payload),
        chunks=chunk_payload,
    )
