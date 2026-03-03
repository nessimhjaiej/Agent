from pathlib import Path
import sys

from fastapi.testclient import TestClient

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.main import create_app  # noqa: E402
import app.routers.retrieval as retrieval_router_module  # noqa: E402


class _FakeRetrievalService:
    captured_mode: str | None = None

    def search(self, payload):  # noqa: ANN001
        _FakeRetrievalService.captured_mode = payload.mode
        return {
            "status": "ok",
            "query": payload.query,
            "mode": payload.mode,
            "retrieval_count": 0,
            "returned_count": 0,
            "fusion_type": payload.fusion.type,
            "rerank_type": "none",
            "chunks": [],
            "documents": [],
        }


def test_search_rejects_invalid_mode() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/retrieval/search",
        json={
            "query": "bank regulation",
            "mode": "invalid_mode",
            "top_k_retrieve": 5,
            "top_k_return": 3,
        },
    )

    assert response.status_code == 422


def test_search_defaults_mode_to_hybrid_when_omitted(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr(retrieval_router_module, "RetrievalService", _FakeRetrievalService)
    _FakeRetrievalService.captured_mode = None

    app = create_app()
    client = TestClient(app)
    response = client.post(
        "/retrieval/search",
        json={
            "query": "bank regulation",
            "top_k_retrieve": 5,
            "top_k_return": 3,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "hybrid"
    assert _FakeRetrievalService.captured_mode == "hybrid"
