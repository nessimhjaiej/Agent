from pathlib import Path
import sys

from fastapi.testclient import TestClient

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.main import create_app  # noqa: E402
from app.errors import GenerationProviderError  # noqa: E402
from app.service import GenerationService  # noqa: E402
import app.routers.generation as generation_router_module  # noqa: E402


def _payload() -> dict:
    return {
        "query": "Summarize key obligations.",
        "retrieved_chunks": [
            {
                "chunk_id": "doc-1:0",
                "document_id": "doc-1",
                "document_name": "doc-1.pdf",
                "chunk_text": "Banks must apply strong customer authentication.",
                "metadata": {"source_filename": "doc-1.pdf"},
                "fusion_score": 0.5,
                "rerank_score": 0.9,
            }
        ],
    }


def _ask_payload() -> dict:
    return {
        "query": "Summarize key obligations.",
        "mode": "hybrid",
        "top_k_retrieve": 5,
        "top_k_return": 3,
        "filters": {"language": "en"},
        "fusion": {"type": "rrf", "rrf_k": 60},
        "rerank": {"enabled": True, "type": "cross_encoder", "top_n": 5},
    }


def test_health_endpoint() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "service" in body
    assert "version" in body


def test_chat_endpoint_rejects_empty_chunk_list() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post("/generation/chat", json={"query": "q", "retrieved_chunks": []})

    assert response.status_code == 422


def test_chat_endpoint_returns_contract_shape(monkeypatch) -> None:  # noqa: ANN001
    class _FakeGenerationService(GenerationService):
        def chat(self, payload):  # noqa: ANN001
            return {
                "status": "ok",
                "session_id": payload.session_id,
                "query": payload.query,
                "answer": "Answer text.",
                "citations": [
                    {
                        "chunk_id": "doc-1:0",
                        "document_id": "doc-1",
                        "document_name": "doc-1.pdf",
                        "chunk_text": "Banks must apply strong customer authentication.",
                    }
                ],
                "used_chunk_ids": ["doc-1:0"],
                "model": "gpt-4o",
            }

    monkeypatch.setattr(generation_router_module, "GenerationService", _FakeGenerationService)

    app = create_app()
    client = TestClient(app)
    response = client.post("/generation/chat", json=_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["answer"] == "Answer text."
    assert body["citations"][0]["document_name"] == "doc-1.pdf"
    assert body["used_chunk_ids"] == ["doc-1:0"]


def test_ask_endpoint_rejects_invalid_mode() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/generation/ask",
        json={
            "query": "q",
            "mode": "invalid",
        },
    )

    assert response.status_code == 422


def test_ask_endpoint_returns_contract_shape(monkeypatch) -> None:  # noqa: ANN001
    class _FakeGenerationService(GenerationService):
        def ask(self, payload):  # noqa: ANN001
            return {
                "status": "ok",
                "session_id": payload.session_id,
                "query": payload.query,
                "answer": "Answer text.",
                "citations": [
                    {
                        "chunk_id": "doc-1:0",
                        "document_id": "doc-1",
                        "document_name": "doc-1.pdf",
                        "chunk_text": "Banks must apply strong customer authentication.",
                    }
                ],
                "used_chunk_ids": ["doc-1:0"],
                "model": "gpt-4o",
                "retrieval_count": 7,
                "returned_count": 3,
                "retrieval_mode": "hybrid",
                "fusion_type": "rrf",
                "rerank_type": "cross_encoder",
            }

    monkeypatch.setattr(generation_router_module, "GenerationService", _FakeGenerationService)

    app = create_app()
    client = TestClient(app)
    response = client.post("/generation/ask", json=_ask_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["retrieval_mode"] == "hybrid"
    assert body["fusion_type"] == "rrf"
    assert body["rerank_type"] == "cross_encoder"


def test_ask_endpoint_maps_provider_errors_to_502(monkeypatch) -> None:  # noqa: ANN001
    class _FakeGenerationService(GenerationService):
        def ask(self, payload):  # noqa: ANN001
            raise GenerationProviderError("upstream failed")

    monkeypatch.setattr(generation_router_module, "GenerationService", _FakeGenerationService)

    app = create_app()
    client = TestClient(app)
    response = client.post("/generation/ask", json=_ask_payload())

    assert response.status_code == 502
