from pathlib import Path
import sys

import httpx

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.config import Settings  # noqa: E402
from app.orchestrator import EmbeddingOrchestrator  # noqa: E402


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
