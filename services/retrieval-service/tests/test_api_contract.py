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
        fusion_type = payload.fusion.type if payload.fusion and payload.fusion.type else "alpha"
        return {
            "status": "ok",
            "query": payload.query,
            "mode": payload.mode,
            "retrieval_count": 0,
            "returned_count": 0,
            "fusion_type": fusion_type,
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


def test_get_retrieval_config_returns_runtime_default_ranker() -> None:
    from app.config import Settings  # noqa: PLC0415

    app = create_app(Settings(default_ranker_type="cross_encoder", default_top_k_retrieve=9, default_top_k_return=4))
    client = TestClient(app)

    response = client.get("/retrieval/config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["config"]["default_ranker_type"] == "cross_encoder"
    assert payload["config"]["top_k_retrieve"] == 9
    assert payload["config"]["top_k_return"] == 4


def test_get_rerankers_returns_registered_methods() -> None:
    from app.config import Settings  # noqa: PLC0415

    app = create_app(Settings(default_ranker_type="llm_batch"))
    client = TestClient(app)

    response = client.get("/retrieval/rerankers")

    assert response.status_code == 200
    payload = response.json()
    assert payload["current_default_ranker_type"] == "llm_batch"
    names = {item["name"] for item in payload["methods"]}
    assert {"none", "cross_encoder", "llm_batch"} <= names


def test_update_retrieval_config_updates_runtime_and_config_file(tmp_path: Path) -> None:
    from app.config import Settings  # noqa: PLC0415

    config_copy = tmp_path / "config.py"
    config_copy.write_text((SERVICE_ROOT / "app" / "config.py").read_text(encoding="utf-8"), encoding="utf-8")
    app = create_app(Settings(default_ranker_type="none"))
    app.state.config_path = config_copy
    client = TestClient(app)

    response = client.put(
        "/retrieval/config",
        json={"default_ranker_type": "cross_encoder", "top_k_retrieve": 11, "top_k_return": 6},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["updated"]["default_ranker_type"] == "cross_encoder"
    assert payload["updated"]["top_k_retrieve"] == 11
    assert payload["updated"]["top_k_return"] == 6
    assert 'default_ranker_type: str = "cross_encoder"' in config_copy.read_text(encoding="utf-8")
    assert "default_top_k_retrieve: int = 11" in config_copy.read_text(encoding="utf-8")
    assert "default_top_k_return: int = 6" in config_copy.read_text(encoding="utf-8")
    current = client.get("/retrieval/config").json()
    assert current["config"]["default_ranker_type"] == "cross_encoder"
    assert current["config"]["top_k_retrieve"] == 11
    assert current["config"]["top_k_return"] == 6
