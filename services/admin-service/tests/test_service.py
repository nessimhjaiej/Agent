from pathlib import Path
import sys

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.service import AdminService  # noqa: E402
from app.schemas import AdminChatRequest  # noqa: E402
from app.config import Settings  # noqa: E402
from app.clients.auth_client import AuthClient  # noqa: E402


class _FakeOrchestrator:
    def handle(self, context):  # noqa: ANN001
        return {
            "status": "ok",
            "mode": "qa",
            "session_id": context.session_id,
            "message": context.message,
            "answer": "Admin answer.",
            "intent": "qa",
            "tool": None,
            "arguments": {},
            "requires_confirmation": False,
            "executed": True,
            "pending_action": None,
            "citations": [],
            "result": {},
        }


class _FakeAuthClient:
    def require_admin(self, access_token: str) -> dict:
        assert access_token == "token-123"
        return {"id": "admin-1", "email": "admin@example.com", "role": "admin"}


def test_service_maps_request_to_orchestrator_response() -> None:
    service = AdminService(orchestrator=_FakeOrchestrator())  # type: ignore[arg-type]
    service._auth_client = _FakeAuthClient()  # type: ignore[attr-defined]
    payload = AdminChatRequest(message="show pipeline status", session_id="session-1")

    response = service.chat(payload, access_token="token-123")

    assert response["status"] == "ok"
    assert response["mode"] == "qa"
    assert response["session_id"] == "session-1"
    assert response["intent"] == "qa"


def test_auth_client_prefers_direct_supabase_lookup(monkeypatch) -> None:  # noqa: ANN001
    captured: dict = {}

    class _FakeResponse:
        status_code = 200

        def json(self):  # noqa: ANN001
            return {
                "id": "admin-1",
                "email": "admin@example.com",
                "user_metadata": {"role": "admin"},
            }

        text = ""

    def _fake_get(url, headers, timeout, trust_env):  # noqa: ANN001
        captured["url"] = url
        captured["headers"] = headers
        captured["trust_env"] = trust_env
        return _FakeResponse()

    monkeypatch.setattr("app.clients.auth_client.httpx.get", _fake_get)
    client = AuthClient(
        Settings(
            auth_supabase_url="https://example.supabase.co",
            auth_supabase_key="anon-key",
        )
    )

    payload = client.require_admin("token-123")

    assert payload["role"] == "admin"
    assert captured["url"] == "https://example.supabase.co/auth/v1/user"
