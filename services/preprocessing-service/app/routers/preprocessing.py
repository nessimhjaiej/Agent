import re
import inspect
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from app.config import Settings
from app.schemas import (
    ChunkingStrategiesResponse,
    ChunkingStrategyItem,
    ChunkResponse,
    PreprocessingConfigResponse,
    ProcessSourceRequest,
    ProcessSourceResponse,
    UpdatePreprocessingConfigRequest,
    UpdatePreprocessingConfigResponse,
)
from app.service import PreprocessingService
from chunking.factory import ChunkerFactory


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
    source = "services/preprocessing-service/app/config.py"
    return {
        "chunk_strategy": source,
        "chunk_size": source,
        "chunk_overlap": source,
        "pipeline_version": source,
    }


def _chunking_methods_payload(settings: Settings) -> ChunkingStrategiesResponse:
    methods: list[ChunkingStrategyItem] = []
    for name, chunker_cls in sorted(ChunkerFactory._registry.items()):
        try:
            source = inspect.getsource(chunker_cls.chunk)
        except (OSError, TypeError):
            source = ""
        implemented = "raise NotImplementedError" not in source
        methods.append(
            ChunkingStrategyItem(
                name=name,
                exists=True,
                implemented=implemented,
            )
        )

    return ChunkingStrategiesResponse(
        status="ok",
        scope="preprocessing",
        current_strategy=settings.chunk_strategy,
        current_chunk_size=settings.chunk_size,
        current_chunk_overlap=settings.chunk_overlap,
        methods=methods,
    )


def _config_path(request: Request) -> Path:
    override = getattr(request.app.state, "config_path", None)
    if override:
        return Path(str(override))
    return Path(__file__).resolve().parents[1] / "config.py"


def _rewrite_config_defaults(updated: dict[str, int | str], request: Request) -> None:
    config_path = _config_path(request)
    content = config_path.read_text(encoding="utf-8")
    field_patterns = {
        "chunk_strategy": r'chunk_strategy: str = "[^"]*"',
        "chunk_size": r"chunk_size: int = \d+",
        "chunk_overlap": r"chunk_overlap: int = \d+",
        "pipeline_version": r'pipeline_version: str = "[^"]*"',
    }

    for field_name, value in updated.items():
        pattern = field_patterns[field_name]
        replacement_value = f'"{value}"' if isinstance(value, str) else str(value)
        content, count = re.subn(
            pattern,
            f"{field_name}: {'str' if isinstance(value, str) else 'int'} = {replacement_value}",
            content,
            count=1,
        )
        if count != 1:
            raise HTTPException(status_code=500, detail=f"Could not persist {field_name} into preprocessing config.py.")

    config_path.write_text(content, encoding="utf-8")


def _env_local_path(request: Request) -> Path:
    override = getattr(request.app.state, "env_local_path", None)
    if override:
        return Path(str(override))
    return Path(__file__).resolve().parents[3] / ".env.local"


def _remove_chunking_overrides_from_env_local(request: Request) -> None:
    env_local = _env_local_path(request)
    if not env_local.exists():
        return

    forbidden = {
        "PREPROCESSING_CHUNK_STRATEGY",
        "PREPROCESSING_CHUNK_SIZE",
        "PREPROCESSING_CHUNK_OVERLAP",
    }
    kept_lines = []
    changed = False
    for raw_line in env_local.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        key = stripped.split("=", 1)[0].strip() if "=" in stripped else ""
        if key in forbidden:
            changed = True
            continue
        kept_lines.append(raw_line)

    if changed:
        env_local.write_text("\n".join(kept_lines) + ("\n" if kept_lines else ""), encoding="utf-8")


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


@router.get("/chunking-strategies", response_model=ChunkingStrategiesResponse)
def get_chunking_strategies(request: Request) -> ChunkingStrategiesResponse:
    return _chunking_methods_payload(_runtime_settings(request))


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

    _rewrite_config_defaults(updated, request)
    _remove_chunking_overrides_from_env_local(request)
    return UpdatePreprocessingConfigResponse(
        status="ok",
        scope="preprocessing",
        updated=updated,
        applied_via="preprocessing-service",
        restart_required=False,
    )
