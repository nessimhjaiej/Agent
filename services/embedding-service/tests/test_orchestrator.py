from pathlib import Path
import sys

import httpx
import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.config import Settings  # noqa: E402
from app.errors import EmbeddingServiceError  # noqa: E402
from app.orchestrator import EmbeddingOrchestrator  # noqa: E402


_DOC_ID = "11111111-1111-4111-8111-111111111111"


def _validated_document() -> dict:
    return {
        "id": _DOC_ID,
        "user_id": "user-1",
        "original_name": "d.pdf",
        "storage_path": "validated/user-1/d.pdf",
        "status": "validated",
        # Supabase says embedded -- but the vectors live only in each machine's
        # local Weaviate, so this flag must not decide whether to skip.
        "embedded": True,
        "size_bytes": 1,
        "created_at": "2026-01-01T00:00:00Z",
        "embedded_at": "2026-01-01T00:00:00Z",
    }


def _make_orchestrator(shared_raw_dir: str) -> EmbeddingOrchestrator:
    settings = Settings(
        openai_key="test-key",
        supabase_url="https://supabase.example",
        supabase_key="service-role-key",
        weaviate_http_url="http://weaviate.example",
        shared_raw_dir=shared_raw_dir,
    )
    return EmbeddingOrchestrator(
        settings=settings,
        embedder=_DummyEmbedder(),
        indexer=_DummyIndexer(),
    )


class _DummyEmbedder:
    def embed_texts(self, texts):  # noqa: ANN001
        return [[0.1, 0.2, 0.3] for _ in texts]


class _DummyIndexer:
    def upsert_chunks(self, chunks, vectors):  # noqa: ANN001
        return []


def test_get_document_flexible_resolves_indexed_document_id_to_supabase_uuid() -> None:
    settings = Settings(
        openai_key="test-key",
        supabase_url="https://supabase.example",
        supabase_key="service-role-key",
    )
    orchestrator = EmbeddingOrchestrator(
        settings=settings,
        embedder=_DummyEmbedder(),
        indexer=_DummyIndexer(),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["storage_path"] == (
            "ilike.*ICC-2024_Protecting-the-cybersecurity-of-critical-infrastructures-and-their-supply-chains*"
        )
        return httpx.Response(
            200,
            json=[
                {
                    "id": "11111111-1111-4111-8111-111111111111",
                    "user_id": "user-1",
                    "original_name": "ICC-2024_Protecting-the-cybersecurity-of-critical-infrastructures-and-their-supply-chains.pdf",
                    "storage_path": (
                        "validated/user-1/"
                        "ICC-2024_Protecting-the-cybersecurity-of-critical-infrastructures-and-their-supply-chains.pdf"
                    ),
                    "status": "validated",
                    "embedded": True,
                    "size_bytes": 123,
                    "created_at": "2026-05-24T00:00:00Z",
                    "embedded_at": "2026-05-24T00:00:00Z",
                }
            ],
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        document = orchestrator._get_document_flexible(  # noqa: SLF001
            client,
            "ICC-2024_Protecting-the-cybersecurity-of-critical-infrastructures-and-their-supply-chains-0d602fedb4f9",
        )

    assert document["id"] == "11111111-1111-4111-8111-111111111111"


def test_index_document_skips_when_local_weaviate_already_has_objects(tmp_path) -> None:
    orchestrator = _make_orchestrator(str(tmp_path))

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "weaviate.example":
            return httpx.Response(
                200,
                json={"data": {"Get": {"Chunk": [{"_additional": {"id": "obj-1"}}]}}},
            )
        return httpx.Response(200, json=[_validated_document()])

    orchestrator._client = lambda: httpx.Client(transport=httpx.MockTransport(handler))  # noqa: SLF001

    result = orchestrator.index_document(_DOC_ID)

    assert result.status == "already_embedded"
    assert result.embedded is True


def test_index_document_ignores_supabase_flag_when_local_weaviate_empty(tmp_path) -> None:
    # Regression: another machine set embedded=True in shared Supabase, but THIS
    # machine's local Weaviate has no objects. We must get past the skip gate and
    # attempt to (re)embed -- here the download 404s, proving the gate was crossed.
    orchestrator = _make_orchestrator(str(tmp_path))

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "weaviate.example":
            return httpx.Response(200, json={"data": {"Get": {"Chunk": []}}})
        if "/storage/v1/" in request.url.path:
            return httpx.Response(404, text="object not found")
        return httpx.Response(200, json=[_validated_document()])

    orchestrator._client = lambda: httpx.Client(transport=httpx.MockTransport(handler))  # noqa: SLF001

    with pytest.raises(EmbeddingServiceError):
        orchestrator.index_document(_DOC_ID)
