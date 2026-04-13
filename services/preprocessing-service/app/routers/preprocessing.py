import re
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from app.config import Settings
from app.schemas import (
    ChunkResponse,
    PreprocessingConfigResponse,
    ProcessSourceRequest,
    ProcessSourceResponse,
    UpdatePreprocessingConfigRequest,
    UpdatePreprocessingConfigResponse,
)
from app.service import PreprocessingService


router = APIRouter(prefix="/preprocessing", tags=["preprocessing"])


def _runtime_settings(request: Request) -> Settings:
    settings = getattr(request.app.state, "settings", None)
    if not isinstance(settings, Settings):
        settings = Settings.from_env()
        request.app.state.settings = settings
    return settings

def _config_payload(settings: Settings) -> dict[str, int | str]:
    return {
        "chunk_strategy": settings.chunk_strategy,
        "chunk_size": settings.chunk_size,
        "chunk_overlap": settings.chunk_overlap,
        "pipeline_version": settings.pipeline_version,
    }


def _source_payload() -> dict[str, str]:
    source = "preprocessing-service runtime"
    return {
        "chunk_strategy": source,
        "chunk_size": source,
        "chunk_overlap": source,
        "pipeline_version": source,
    }


def _env_local_path(request: Request) -> Path:
    override = getattr(request.app.state, "env_local_path", None)
    if override:
        return Path(str(override))
    return Path(__file__).resolve().parents[3] / ".env.local"


def _persist_runtime_overrides(updated: dict[str, int | str], request: Request) -> None:
    env_local = _env_local_path(request)
    lines: list[str] = []
    if env_local.exists():
        lines = env_local.read_text(encoding="utf-8").splitlines()

    env_mapping = {
        "chunk_strategy": "PREPROCESSING_CHUNK_STRATEGY",
        "chunk_size": "PREPROCESSING_CHUNK_SIZE",
        "chunk_overlap": "PREPROCESSING_CHUNK_OVERLAP",
        "pipeline_version": "PREPROCESSING_PIPELINE_VERSION",
    }

    for field_name, value in updated.items():
        env_name = env_mapping[field_name]
        pattern = re.compile(rf"^\s*{re.escape(env_name)}=")
        rendered = str(value)
        replaced = False
        for index, line in enumerate(lines):
            if pattern.match(line):
                lines[index] = f"{env_name}={rendered}"
                replaced = True
                break
        if not replaced:
            lines.append(f"{env_name}={rendered}")

    env_local.parent.mkdir(parents=True, exist_ok=True)
    env_local.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


@router.post("/process-source", response_model=ProcessSourceResponse)
def process_source(payload: ProcessSourceRequest, request: Request) -> ProcessSourceResponse:
    service = PreprocessingService(_runtime_settings(request))
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


@router.get("/config", response_model=PreprocessingConfigResponse)
def get_config(request: Request) -> PreprocessingConfigResponse:
    settings = _runtime_settings(request)
    return PreprocessingConfigResponse(
        status="ok",
        scope="preprocessing",
        config=_config_payload(settings),
        sources=_source_payload(),
    )


@router.put("/config", response_model=UpdatePreprocessingConfigResponse)
def update_config(payload: UpdatePreprocessingConfigRequest, request: Request) -> UpdatePreprocessingConfigResponse:
    updates = payload.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="At least one preprocessing setting must be provided.")

    settings = _runtime_settings(request)
    updated: dict[str, int | str] = {}
    for field_name, value in updates.items():
        if field_name not in {"chunk_strategy", "chunk_size", "chunk_overlap", "pipeline_version"}:
            raise HTTPException(status_code=400, detail=f"Unsupported preprocessing setting: {field_name}")
        setattr(settings, field_name, value)
        updated[field_name] = value

    _persist_runtime_overrides(updated, request)
    return UpdatePreprocessingConfigResponse(
        status="ok",
        scope="preprocessing",
        updated=updated,
        applied_via="preprocessing-service",
        restart_required=False,
    )
