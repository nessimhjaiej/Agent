import inspect
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from app.config import Settings
from app.schemas import (
    RetrievalConfigResponse,
    RetrievalRerankersResponse,
    RerankerMethodItem,
    SearchRequest,
    SearchResponse,
    UpdateRetrievalConfigRequest,
    UpdateRetrievalConfigResponse,
)
from app.service import RetrievalService
from rankers.factory import RankerFactory


router = APIRouter(prefix="/retrieval", tags=["retrieval"])


def _runtime_settings(request: Request) -> Settings:
    settings = getattr(request.app.state, "settings", None)
    if not isinstance(settings, Settings):
        settings = Settings.from_env()
        request.app.state.settings = settings
    return settings


def _config_path(request: Request) -> Path:
    override = getattr(request.app.state, "config_path", None)
    if override:
        return Path(str(override))
    return Path(__file__).resolve().parents[1] / "config.py"


def _rewrite_retrieval_config(updated: dict[str, str | int], request: Request) -> None:
    config_path = _config_path(request)
    content = config_path.read_text(encoding="utf-8")
    for field_name, value in updated.items():
        if field_name == "default_ranker_type":
            content, count = re.subn(
                r'default_ranker_type: str = "[^"]*"',
                f'default_ranker_type: str = "{value}"',
                content,
                count=1,
            )
        elif field_name == "top_k_retrieve":
            content, count = re.subn(
                r"default_top_k_retrieve: int = \d+",
                f"default_top_k_retrieve: int = {value}",
                content,
                count=1,
            )
        elif field_name == "top_k_return":
            content, count = re.subn(
                r"default_top_k_return: int = \d+",
                f"default_top_k_return: int = {value}",
                content,
                count=1,
            )
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported retrieval setting: {field_name}")
        if count != 1:
            raise HTTPException(status_code=500, detail=f"Could not persist {field_name} into retrieval config.py.")
    config_path.write_text(content, encoding="utf-8")


def _config_payload(settings: Settings) -> RetrievalConfigResponse:
    source = "services/retrieval-service/app/config.py"
    return RetrievalConfigResponse(
        status="ok",
        scope="retrieval",
        config={
            "default_ranker_type": settings.default_ranker_type,
            "top_k_retrieve": settings.default_top_k_retrieve,
            "top_k_return": settings.default_top_k_return,
        },
        sources={
            "default_ranker_type": source,
            "top_k_retrieve": source,
            "top_k_return": source,
        },
    )


def _rerankers_payload(settings: Settings) -> RetrievalRerankersResponse:
    methods: list[RerankerMethodItem] = []
    for name, ranker_cls in sorted(RankerFactory._registry.items()):
        try:
            source = inspect.getsource(ranker_cls.rank)
        except (OSError, TypeError):
            source = ""
        implemented = "raise NotImplementedError" not in source
        methods.append(RerankerMethodItem(name=name, exists=True, implemented=implemented))
    return RetrievalRerankersResponse(
        status="ok",
        scope="retrieval",
        current_default_ranker_type=settings.default_ranker_type,
        methods=methods,
    )


@router.post("/search", response_model=SearchResponse)
def search(payload: SearchRequest, request: Request) -> SearchResponse:
    service = RetrievalService(_runtime_settings(request))
    return service.search(payload)


@router.get("/config", response_model=RetrievalConfigResponse)
def get_config(request: Request) -> RetrievalConfigResponse:
    return _config_payload(_runtime_settings(request))


@router.put("/config", response_model=UpdateRetrievalConfigResponse)
def update_config(payload: UpdateRetrievalConfigRequest, request: Request) -> UpdateRetrievalConfigResponse:
    settings = _runtime_settings(request)
    updated = payload.model_dump(exclude_none=True)
    if not updated:
        raise HTTPException(status_code=400, detail="At least one retrieval setting must be provided.")
    if payload.default_ranker_type is not None:
        settings.default_ranker_type = payload.default_ranker_type
    if payload.top_k_retrieve is not None:
        settings.default_top_k_retrieve = payload.top_k_retrieve
    if payload.top_k_return is not None:
        settings.default_top_k_return = payload.top_k_return
    _rewrite_retrieval_config(updated, request)
    return UpdateRetrievalConfigResponse(
        status="ok",
        scope="retrieval",
        updated=updated,
        applied_via="retrieval-service",
        restart_required=False,
    )


@router.get("/rerankers", response_model=RetrievalRerankersResponse)
def get_rerankers(request: Request) -> RetrievalRerankersResponse:
    return _rerankers_payload(_runtime_settings(request))
