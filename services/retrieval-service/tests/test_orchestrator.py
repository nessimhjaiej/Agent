from pathlib import Path
import sys

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.models import CandidateChunk, QueryContext  # noqa: E402
from app.orchestrator import RetrievalOrchestrator  # noqa: E402


def _chunk(chunk_id: str) -> CandidateChunk:
    return CandidateChunk(
        chunk_id=chunk_id,
        document_id="doc-1",
        chunk_text=f"text-{chunk_id}",
        metadata={},
    )


class _FakeRetriever:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.bm25 = [_chunk("a"), _chunk("b")]
        self.vector = [_chunk("b"), _chunk("c")]

    def retrieve_bm25(self, ctx: QueryContext) -> list[CandidateChunk]:
        self.calls.append("bm25")
        return self.bm25

    def retrieve_vector(self, ctx: QueryContext) -> list[CandidateChunk]:
        self.calls.append("vector")
        return self.vector

    def retrieve(self, ctx: QueryContext) -> tuple[list[CandidateChunk], list[CandidateChunk]]:
        mode = ctx.mode
        if mode == "bm25":
            return self.retrieve_bm25(ctx), []
        if mode == "vector":
            return [], self.retrieve_vector(ctx)
        return self.retrieve_bm25(ctx), self.retrieve_vector(ctx)


class _FakeFusion:
    def __init__(self) -> None:
        self.called = False
        self.last_args: tuple | None = None

    def combine(
        self,
        bm25_candidates: list[CandidateChunk],
        vector_candidates: list[CandidateChunk],
        ctx: QueryContext,
    ) -> list[CandidateChunk]:
        self.called = True
        self.last_args = (bm25_candidates, vector_candidates, ctx)
        # return deterministic order
        return [_chunk("b"), _chunk("a"), _chunk("c")]


class _FakeFusionFactory:
    def __init__(self, fusion: _FakeFusion) -> None:
        self._fusion = fusion
        self.calls: list[str] = []

    def create(self, fusion_type: str):  # noqa: ANN001
        self.calls.append(fusion_type)
        return self._fusion


class _FakeRanker:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def rank(self, query: str, candidates: list[CandidateChunk], top_n: int) -> list[CandidateChunk]:
        self.calls.append({"query": query, "top_n": top_n, "candidates": [c.chunk_id for c in candidates]})
        return candidates[:top_n]


class _FakeRankerFactory:
    def __init__(self, ranker: _FakeRanker) -> None:
        self._ranker = ranker
        self.calls: list[dict] = []

    def create(self, ranker_type: str, enabled: bool):  # noqa: ANN001
        self.calls.append({"ranker_type": ranker_type, "enabled": enabled})
        return self._ranker


def test_orchestrator_runs_hybrid_then_fusion_then_ranker() -> None:
    retriever = _FakeRetriever()
    fusion = _FakeFusion()
    fusion_factory = _FakeFusionFactory(fusion)
    ranker = _FakeRanker()
    ranker_factory = _FakeRankerFactory(ranker)

    orchestrator = RetrievalOrchestrator(
        retriever=retriever,
        fusion_factory=fusion_factory,  # type: ignore[arg-type]
        ranker_factory=ranker_factory,  # type: ignore[arg-type]
    )
    ctx = QueryContext(
        query="q",
        top_k_retrieve=5,
        top_k_return=3,
        fusion_type="alpha",
        rerank_type="cross_encoder",
        rerank_enabled=True,
        rerank_top_n=2,
    )

    result = orchestrator.search(ctx)

    assert retriever.calls == ["bm25", "vector"]
    assert fusion_factory.calls == ["alpha"]
    assert fusion.called is True
    assert ranker_factory.calls == [{"ranker_type": "cross_encoder", "enabled": True}]
    assert len(ranker.calls) == 1
    assert ranker.calls[0]["top_n"] == 2
    assert ranker.calls[0]["candidates"] == ["b", "a", "c"]
    assert [c.chunk_id for c in result] == ["b", "a"]


def test_orchestrator_passes_fusion_and_ranker_choices_from_context() -> None:
    retriever = _FakeRetriever()
    fusion = _FakeFusion()
    fusion_factory = _FakeFusionFactory(fusion)
    ranker = _FakeRanker()
    ranker_factory = _FakeRankerFactory(ranker)

    orchestrator = RetrievalOrchestrator(
        retriever=retriever,
        fusion_factory=fusion_factory,  # type: ignore[arg-type]
        ranker_factory=ranker_factory,  # type: ignore[arg-type]
    )
    ctx = QueryContext(
        query="new query",
        top_k_retrieve=5,
        top_k_return=3,
        fusion_type="rrf",
        rerank_type="none",
        rerank_enabled=False,
        rerank_top_n=3,
    )

    _ = orchestrator.search(ctx)

    assert fusion_factory.calls == ["rrf"]
    assert ranker_factory.calls == [{"ranker_type": "none", "enabled": False}]
