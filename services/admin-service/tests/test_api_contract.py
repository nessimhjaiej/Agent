from pathlib import Path
import sys

from fastapi.testclient import TestClient

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

import app.routers.admin as admin_router_module  # noqa: E402
from app.main import create_app  # noqa: E402


def test_health_endpoint() -> None:
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "admin-service"


def test_admin_chat_returns_contract_shape() -> None:
    original = admin_router_module.AdminAccessChecker.require_admin
    admin_router_module.AdminAccessChecker.require_admin = lambda self, **kwargs: None
    try:
        client = TestClient(create_app())
        response = client.post("/admin/chat", json={"message": "hello", "access_token": "token"})
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["mode"] == "advisory"
        assert body["intent"]
        assert body["result"]["route"] == "advisory"
    finally:
        admin_router_module.AdminAccessChecker.require_admin = original


def test_admin_chat_requires_admin_access() -> None:
    client = TestClient(create_app())
    response = client.post("/admin/chat", json={"message": "hello"})
    assert response.status_code == 401


def test_admin_chat_stream_returns_ndjson() -> None:
    original = admin_router_module.AdminAccessChecker.require_admin
    admin_router_module.AdminAccessChecker.require_admin = lambda self, **kwargs: None
    try:
        client = TestClient(create_app())
        response = client.post("/admin/chat/stream", json={"message": "hello", "access_token": "token"})
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/x-ndjson")
        lines = [line for line in response.text.splitlines() if line.strip()]
        assert len(lines) >= 3
        assert '"type": "status"' in lines[0]
        assert any('"type": "response"' in line for line in lines)
        assert '"type": "done"' in lines[-1]
    finally:
        admin_router_module.AdminAccessChecker.require_admin = original


def test_admin_graph_returns_mermaid() -> None:
    original = admin_router_module.AdminAccessChecker.require_admin
    admin_router_module.AdminAccessChecker.require_admin = lambda self, **kwargs: None
    try:
        client = TestClient(create_app())
        response = client.get("/admin/graph", headers={"Authorization": "Bearer token"})
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["format"] == "mermaid"
        assert "classify_intent_llm" in body["graph"]
    finally:
        admin_router_module.AdminAccessChecker.require_admin = original
