from pathlib import Path
import sys

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.models import QueryContext  # noqa: E402
from retrievers.bm25 import BM25Retriever  # noqa: E402


class _FakeWeaviateClient:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows
        self.calls: list[dict] = []

    def bm25_search(self, query: str, top_k: int, filters: dict) -> list[dict]:
        self.calls.append({"query": query, "top_k": top_k, "filters": filters})
        return self._rows


def test_bm25_retriever_calls_client_with_context_values() -> None:
    client = _FakeWeaviateClient(rows=[])
    retriever = BM25Retriever(client=client)
    ctx = QueryContext(
        query="digital regulation",
        top_k_retrieve=5,
        top_k_return=3,
        filters={"language": "en"},
    )

    _ = retriever.retrieve(ctx)

    assert len(client.calls) == 1
    assert client.calls[0]["query"] == "digital regulation"
    assert client.calls[0]["top_k"] == 5
    assert client.calls[0]["filters"] == {"language": "en"}


def test_bm25_retriever_maps_rows_to_candidates_with_rank_and_score() -> None:
    rows = [
        {
            "chunk_id": "doc-1:0",
            "document_id": "doc-1",
            "chunk_text": "alpha text",
            "language": "en",
            "_additional": {"score": "1.23"},
        },
        {
            "chunk_id": "doc-1:1",
            "document_id": "doc-1",
            "chunk_text": "beta text",
            "source_type": "pdf",
            "_additional": {"score": 0.87},
        },
    ]
    retriever = BM25Retriever(client=_FakeWeaviateClient(rows=rows))
    ctx = QueryContext(query="alpha", top_k_retrieve=5, top_k_return=3)

    candidates = retriever.retrieve(ctx)

    assert len(candidates) == 2
    assert candidates[0].chunk_id == "doc-1:0"
    assert candidates[0].bm25_score == 1.23
    assert candidates[0].rank_bm25 == 1
    assert candidates[0].metadata["language"] == "en"
    assert candidates[1].rank_bm25 == 2


def test_bm25_retriever_skips_invalid_rows() -> None:
    rows = [
        {"document_id": "doc-1", "chunk_text": "missing chunk_id"},
        {"chunk_id": "doc-2:0", "chunk_text": "missing document_id"},
        {"chunk_id": "doc-3:0", "document_id": "doc-3", "chunk_text": "ok"},
    ]
    retriever = BM25Retriever(client=_FakeWeaviateClient(rows=rows))
    ctx = QueryContext(query="x", top_k_retrieve=5, top_k_return=3)

    candidates = retriever.retrieve(ctx)

    assert len(candidates) == 1
    assert candidates[0].chunk_id == "doc-3:0"
