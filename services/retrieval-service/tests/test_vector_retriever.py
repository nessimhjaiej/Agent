from pathlib import Path
import sys

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.models import QueryContext  # noqa: E402
from retrievers.vector import VectorRetriever  # noqa: E402


class _FakeEmbedder:
    def __init__(self, vector: list[float]) -> None:
        self._vector = vector
        self.calls: list[str] = []

    def embed_query(self, query: str) -> list[float]:
        self.calls.append(query)
        return self._vector


class _FakeWeaviateClient:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows
        self.calls: list[dict] = []

    def vector_search(self, query_vector: list[float], top_k: int, filters: dict) -> list[dict]:
        self.calls.append({"query_vector": query_vector, "top_k": top_k, "filters": filters})
        return self._rows


def test_vector_retriever_calls_embedder_and_client() -> None:
    embedder = _FakeEmbedder(vector=[0.1, 0.2, 0.3])
    client = _FakeWeaviateClient(rows=[])
    retriever = VectorRetriever(embedder=embedder, weaviate_client=client)
    ctx = QueryContext(query="bank regulation", top_k_retrieve=5, top_k_return=3, filters={"language": "fr"})

    _ = retriever.retrieve(ctx)

    assert embedder.calls == ["bank regulation"]
    assert len(client.calls) == 1
    assert client.calls[0]["query_vector"] == [0.1, 0.2, 0.3]
    assert client.calls[0]["top_k"] == 5
    assert client.calls[0]["filters"] == {"language": "fr"}


def test_vector_retriever_maps_rows_with_rank_and_similarity_score() -> None:
    rows = [
        {
            "chunk_id": "doc-1:0",
            "document_id": "doc-1",
            "chunk_text": "alpha text",
            "language": "en",
            "_additional": {"distance": 0.12},
        },
        {
            "chunk_id": "doc-1:1",
            "document_id": "doc-1",
            "chunk_text": "beta text",
            "_additional": {"distance": "0.25"},
        },
    ]
    retriever = VectorRetriever(
        embedder=_FakeEmbedder([0.1]),
        weaviate_client=_FakeWeaviateClient(rows=rows),
    )
    ctx = QueryContext(query="alpha", top_k_retrieve=5, top_k_return=3)

    candidates = retriever.retrieve(ctx)

    assert len(candidates) == 2
    assert candidates[0].rank_vector == 1
    assert round(candidates[0].vector_score or 0.0, 2) == 0.88
    assert candidates[1].rank_vector == 2
    assert round(candidates[1].vector_score or 0.0, 2) == 0.75


def test_vector_retriever_skips_invalid_rows() -> None:
    rows = [
        {"document_id": "doc-1", "chunk_text": "missing chunk_id"},
        {"chunk_id": "doc-2:0", "chunk_text": "missing document_id"},
        {"chunk_id": "doc-3:0", "document_id": "doc-3", "chunk_text": "ok"},
    ]
    retriever = VectorRetriever(
        embedder=_FakeEmbedder([0.1]),
        weaviate_client=_FakeWeaviateClient(rows=rows),
    )
    ctx = QueryContext(query="x", top_k_retrieve=5, top_k_return=3)

    candidates = retriever.retrieve(ctx)

    assert len(candidates) == 1
    assert candidates[0].chunk_id == "doc-3:0"
