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

    response = client.post("/admin/chat", json={"message": ""})

    assert response.status_code == 422


def test_admin_chat_endpoint_allows_request_without_authorization_header() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post("/admin/chat", json={"message": "show status", "selected_mode": "qa"})

    assert response.status_code != 401


def test_admin_chat_endpoint_returns_hybrid_contract(monkeypatch) -> None:  # noqa: ANN001
    class _FakeAdminService(AdminService):
        def chat(self, payload, access_token=None):  # noqa: ANN001
            return {
                "status": "needs_confirmation",
                "mode": "tool_call",
                "selected_mode": "plan",
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
                "thinking_summary": "Confirmation required before deletion.",
                "activity": [],
                "result": {},
            }

    monkeypatch.setattr(admin_chat_router_module, "AdminService", _FakeAdminService)

    app = create_app()
    client = TestClient(app)
    response = client.post(
        "/admin/chat",
        json={"message": "delete document doc.pdf", "selected_mode": "plan", "session_id": "admin-1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "needs_confirmation"
    assert body["mode"] == "tool_call"
    assert body["selected_mode"] == "plan"
    assert body["pending_action"]["tool"] == "delete_document"


def test_admin_chat_stream_endpoint_returns_final_event(monkeypatch) -> None:  # noqa: ANN001
    class _FakeAdminService(AdminService):
        def stream_chat(self, payload):  # noqa: ANN001
            yield '{"type":"activity","activity":[{"phase":"planning","status":"completed","title":"Resolved request","detail":"Built a plan."}]}\n'
            yield (
                '{"type":"final","response":{"status":"ok","mode":"tool_call","selected_mode":"plan","session_id":"admin-1",'
                '"message":"do thing","answer":"Done.","intent":"restart_services","tool":"restart_services",'
                '"arguments":{},"requires_confirmation":false,"executed":true,"pending_action":null,'
                '"citations":[],"thinking_summary":"Executed requested action.","activity":[],"result":{}}}\n'
            )

    monkeypatch.setattr(admin_chat_router_module, "AdminService", _FakeAdminService)

    app = create_app()
    client = TestClient(app)
    response = client.post(
        "/admin/chat/stream",
        json={"message": "do thing", "selected_mode": "plan", "session_id": "admin-1"},
    )

    assert response.status_code == 200
    assert '"type":"activity"' in response.text
    assert '"type":"final"' in response.text


def test_admin_chat_response_allows_agent_run_state() -> None:
    app = create_app()
    client = TestClient(app)

    class _FakeAdminService(AdminService):
        def chat(self, payload, access_token=None):  # noqa: ANN001
            return {
                "status": "ok",
                "mode": "advisory",
                "selected_mode": "plan",
                "session_id": payload.session_id,
                "message": payload.message,
                "answer": "I inspected the current reranker setup and prepared a recommendation.",
                "intent": "recommend_reranker",
                "tool": None,
                "arguments": {},
                "requires_confirmation": False,
                "executed": False,
                "pending_action": None,
                "citations": [],
                "thinking_summary": "The agent gathered state but did not execute a mutation.",
                "activity": [],
                "result": {},
                "agent_run": {
                    "run_id": "run-1",
                    "goal": {
                        "message": payload.message,
                        "subject": "reranking",
                        "desired_outcome": "recommend a reranker",
                        "constraints": ["low resource usage"],
                        "success_criteria": ["return a grounded recommendation"],
                    },
                    "status": "running",
                    "iteration_count": 1,
                    "tool_call_count": 1,
                    "max_iterations": 25,
                    "max_tool_calls": 10,
                    "facts": {"default_ranker": "cross_encoder"},
                    "observations": [
                        {
                            "source": "get_reranker_config",
                            "content": "Read the current reranker configuration.",
                            "data": {"default_ranker": "cross_encoder"},
                        }
                    ],
                    "decision_history": [
                        {
                            "action_type": "call_tool",
                            "message": "Inspect current reranker configuration.",
                            "tool_name": "get_reranker_config",
                            "arguments": {},
                            "reason": "Need current state before recommending a change.",
                            "expected_observation": "Current reranker and top_n values.",
                        }
                    ],
                    "proposed_steps": [],
                    "pending_confirmation": None,
                    "final_answer": "",
                    "stop_reason": "",
                },
            }

    admin_chat_router_module.AdminService = _FakeAdminService
    response = client.post(
        "/admin/chat",
        json={
            "message": "Recommend a reranker for good quality with low resource usage.",
            "selected_mode": "plan",
            "session_id": "admin-1",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "advisory"
    assert body["agent_run"]["goal"]["subject"] == "reranking"
    assert body["agent_run"]["observations"][0]["source"] == "get_reranker_config"
