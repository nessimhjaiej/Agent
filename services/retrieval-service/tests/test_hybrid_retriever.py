from pathlib import Path
import sys

import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.models import CandidateChunk, QueryContext  # noqa: E402
from retrievers.hybrid import HybridRetriever  # noqa: E402


def _chunk(chunk_id: str) -> CandidateChunk:
    return CandidateChunk(
        chunk_id=chunk_id,
        document_id="doc",
        chunk_text=f"text-{chunk_id}",
        metadata={},
    )


class _FakeRetriever:
    def __init__(self, tag: str) -> None:
        self.tag = tag
        self.calls = 0

    def retrieve(self, ctx: QueryContext) -> list[CandidateChunk]:
        self.calls += 1
        return [_chunk(f"{self.tag}-1")]


def test_hybrid_mode_calls_both_retrievers() -> None:
    bm25 = _FakeRetriever("bm25")
    vector = _FakeRetriever("vec")
    r = HybridRetriever(bm25_retriever=bm25, vector_retriever=vector)  # type: ignore[arg-type]

    ctx = QueryContext(query="q", top_k_retrieve=5, top_k_return=3, mode="hybrid")
    bm25_rows, vector_rows = r.retrieve(ctx)

    assert bm25.calls == 1
    assert vector.calls == 1
    assert [c.chunk_id for c in bm25_rows] == ["bm25-1"]
    assert [c.chunk_id for c in vector_rows] == ["vec-1"]


def test_bm25_mode_calls_only_bm25_retriever() -> None:
    bm25 = _FakeRetriever("bm25")
    vector = _FakeRetriever("vec")
    r = HybridRetriever(bm25_retriever=bm25, vector_retriever=vector)  # type: ignore[arg-type]

    ctx = QueryContext(query="q", top_k_retrieve=5, top_k_return=3, mode="bm25")
    bm25_rows, vector_rows = r.retrieve(ctx)

    assert bm25.calls == 1
    assert vector.calls == 0
    assert len(vector_rows) == 0
    assert [c.chunk_id for c in bm25_rows] == ["bm25-1"]


def test_vector_mode_calls_only_vector_retriever() -> None:
    bm25 = _FakeRetriever("bm25")
    vector = _FakeRetriever("vec")
    r = HybridRetriever(bm25_retriever=bm25, vector_retriever=vector)  # type: ignore[arg-type]

    ctx = QueryContext(query="q", top_k_retrieve=5, top_k_return=3, mode="vector")
    bm25_rows, vector_rows = r.retrieve(ctx)

    assert bm25.calls == 0
    assert vector.calls == 1
    assert len(bm25_rows) == 0
    assert [c.chunk_id for c in vector_rows] == ["vec-1"]


def test_invalid_mode_raises_value_error() -> None:
    r = HybridRetriever()
    ctx = QueryContext(query="q", top_k_retrieve=5, top_k_return=3, mode="bad")

    with pytest.raises(ValueError):
        _ = r.retrieve(ctx)
