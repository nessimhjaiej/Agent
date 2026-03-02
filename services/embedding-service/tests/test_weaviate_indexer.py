from pathlib import Path
import sys

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.config import Settings  # noqa: E402
from app.models import Chunk, ChunkMetadata  # noqa: E402
from indexers.weaviate_indexer import WeaviateIndexer  # noqa: E402


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, object] | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text

    def json(self) -> dict[str, object]:
        return self._payload


class _FakeClient:
    def __init__(self, put_responses: list[_FakeResponse], post_responses: list[_FakeResponse]) -> None:
        self._put_responses = put_responses
        self._post_responses = post_responses
        self.put_calls: list[dict[str, object]] = []
        self.post_calls: list[dict[str, object]] = []

    def put(self, url: str, json: dict[str, object]) -> _FakeResponse:
        self.put_calls.append({"url": url, "json": json})
        return self._put_responses.pop(0)

    def post(self, url: str, json: dict[str, object]) -> _FakeResponse:
        self.post_calls.append({"url": url, "json": json})
        return self._post_responses.pop(0)


def _chunk() -> Chunk:
    metadata = ChunkMetadata(
        source_type="txt",
        source_uri="c:/tmp/test.txt",
        language="en",
        chunk_index=0,
        start_char=0,
        end_char=11,
        char_count=11,
        token_count_estimate=2,
        chunking_strategy="overlap",
        source_filename="test.txt",
        document_checksum="checksum",
        normalization_version="basic-v1",
        pipeline_version="v1",
        created_at="2026-03-02T00:00:00Z",
    )
    return Chunk(
        chunk_id="doc-1:0",
        document_id="doc-1",
        chunk_text="hello world",
        metadata=metadata,
    )


def test_upsert_updates_existing_object() -> None:
    settings = Settings(
        openai_key="unused",
        fail_if_collection_missing=False,
        weaviate_batch_size=10,
    )
    indexer = WeaviateIndexer(settings)
    indexer._client = _FakeClient(
        put_responses=[_FakeResponse(204)],
        post_responses=[],
    )

    results = indexer.upsert_chunks([_chunk()], [[0.1, 0.2, 0.3]])

    assert len(results) == 1
    assert results[0].indexed is True
    assert results[0].reason == "upsert_update"
    assert len(indexer._client.put_calls) == 1
    assert len(indexer._client.post_calls) == 0


def test_upsert_creates_when_update_returns_404() -> None:
    settings = Settings(
        openai_key="unused",
        fail_if_collection_missing=False,
        weaviate_batch_size=10,
    )
    indexer = WeaviateIndexer(settings)
    indexer._client = _FakeClient(
        put_responses=[_FakeResponse(404, text="not found")],
        post_responses=[_FakeResponse(200, payload={"id": "x"})],
    )

    results = indexer.upsert_chunks([_chunk()], [[0.1, 0.2, 0.3]])

    assert len(results) == 1
    assert results[0].indexed is True
    assert results[0].reason == "upsert_create"
    assert len(indexer._client.put_calls) == 1
    assert len(indexer._client.post_calls) == 1


def test_upsert_creates_when_update_reports_missing_object_message() -> None:
    settings = Settings(
        openai_key="unused",
        fail_if_collection_missing=False,
        weaviate_batch_size=10,
    )
    indexer = WeaviateIndexer(settings)
    indexer._client = _FakeClient(
        put_responses=[_FakeResponse(422, payload={"error": "no object with id 'abc'"})],
        post_responses=[_FakeResponse(200, payload={"id": "x"})],
    )

    results = indexer.upsert_chunks([_chunk()], [[0.1, 0.2, 0.3]])

    assert len(results) == 1
    assert results[0].indexed is True
    assert results[0].reason == "upsert_create"
    assert len(indexer._client.put_calls) == 1
    assert len(indexer._client.post_calls) == 1
