from pathlib import Path
import sys

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.config import Settings  # noqa: E402
from app.models import CandidateChunk, QueryContext  # noqa: E402
from app.schemas import SearchRequest  # noqa: E402
from app.service import RetrievalService  # noqa: E402


class _FakeOrchestrator:
    def __init__(self) -> None:
        self.last_ctx: QueryContext | None = None

    def search(self, ctx: QueryContext) -> list[CandidateChunk]:
        self.last_ctx = ctx
        return [
            CandidateChunk(
                chunk_id="doc-1:0",
                document_id="doc-1",
                chunk_text="chunk one",
                metadata={"source_filename": "doc-1.pdf"},
                fusion_score=0.9,
                rerank_score=0.8,
            ),
            CandidateChunk(
                chunk_id="doc-2:0",
                document_id="doc-2",
                chunk_text="chunk two",
                metadata={"source_filename": "doc-2.pdf"},
                fusion_score=0.8,
                rerank_score=0.7,
            ),
        ]


def test_service_uses_env_defaults_when_optional_fields_omitted() -> None:
    orchestrator = _FakeOrchestrator()
    settings = Settings(
        default_top_k_retrieve=8,
        default_top_k_return=1,
        default_fusion_type="rrf",
        default_alpha=0.5,
        default_rrf_k=77,
        default_ranker_type="cross_encoder",
        default_rerank_top_n=6,
    )
    service = RetrievalService(settings=settings, orchestrator=orchestrator)  # type: ignore[arg-type]

    response = service.search(SearchRequest(query="what is kyc?"))

    assert orchestrator.last_ctx is not None
    assert orchestrator.last_ctx.top_k_retrieve == 8
    assert orchestrator.last_ctx.top_k_return == 1
    assert orchestrator.last_ctx.fusion_type == "rrf"
    assert orchestrator.last_ctx.alpha == 0.5
    assert orchestrator.last_ctx.rrf_k == 77
    assert orchestrator.last_ctx.rerank_type == "cross_encoder"
    assert orchestrator.last_ctx.rerank_enabled is True
    assert orchestrator.last_ctx.rerank_top_n == 6

    assert response.fusion_type == "rrf"
    assert response.rerank_type == "cross_encoder"
    assert response.returned_count == 1
    assert len(response.chunks) == 1
    assert response.chunks[0].document_name == "doc-1.pdf"


def test_service_disables_rerank_when_request_explicitly_sets_enabled_false() -> None:
    orchestrator = _FakeOrchestrator()
    settings = Settings(default_ranker_type="cross_encoder")
    service = RetrievalService(settings=settings, orchestrator=orchestrator)  # type: ignore[arg-type]

    response = service.search(
        SearchRequest(
            query="what is aml?",
            rerank={"enabled": False},
        )
    )

    assert orchestrator.last_ctx is not None
    assert orchestrator.last_ctx.rerank_type == "cross_encoder"
    assert orchestrator.last_ctx.rerank_enabled is False
    assert response.rerank_type == "none"
