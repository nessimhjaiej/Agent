from pathlib import Path
import sys

from fastapi.testclient import TestClient

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.main import create_app  # noqa: E402
from app.service import AdminService  # noqa: E402
import app.routers.admin_chat as admin_chat_router_module  # noqa: E402


def test_health_endpoint() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "service" in body
    assert "version" in body


def test_admin_chat_endpoint_rejects_empty_message() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post("/admin/chat", json={"message": ""}, headers={"Authorization": "Bearer token"})

    assert response.status_code == 422


def test_admin_chat_endpoint_requires_authorization_header() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post("/admin/chat", json={"message": "show status"})

    assert response.status_code == 401


def test_admin_chat_endpoint_returns_hybrid_contract(monkeypatch) -> None:  # noqa: ANN001
    class _FakeAdminService(AdminService):
        def chat(self, payload, access_token):  # noqa: ANN001
            assert access_token == "token-123"
            return {
                "status": "needs_confirmation",
                "mode": "tool_call",
                "session_id": payload.session_id,
                "message": payload.message,
                "answer": "Are you sure you want to delete doc.pdf?",
                "intent": "delete_document",
                "tool": "delete_document",
                "arguments": {"target_relative_path": "doc.pdf"},
                "requires_confirmation": True,
                "executed": False,
                "pending_action": {
                    "intent": "delete_document",
                    "tool": "delete_document",
                    "arguments": {"target_relative_path": "doc.pdf"},
                },
                "citations": [],
                "result": {},
            }

    monkeypatch.setattr(admin_chat_router_module, "AdminService", _FakeAdminService)

    app = create_app()
    client = TestClient(app)
    response = client.post(
        "/admin/chat",
        json={"message": "delete document doc.pdf", "session_id": "admin-1"},
        headers={"Authorization": "Bearer token-123"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "needs_confirmation"
    assert body["mode"] == "tool_call"
    assert body["pending_action"]["tool"] == "delete_document"
