from pathlib import Path
import sys

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.service import AdminService  # noqa: E402
from app.schemas import AdminChatRequest  # noqa: E402
class _FakeOrchestrator:
    def handle(self, context):  # noqa: ANN001
        return {
            "status": "ok",
            "mode": "qa",
            "selected_mode": "qa",
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
            "thinking_summary": "Handled as admin Q&A.",
            "activity": [],
            "result": {},
            "agent_run": None,
            "latest_user_language": context.latest_user_language,
        }

def test_service_maps_request_to_orchestrator_response() -> None:
    service = AdminService(orchestrator=_FakeOrchestrator())  # type: ignore[arg-type]
    payload = AdminChatRequest(message="show pipeline status", selected_mode="qa", session_id="session-1")

    response = service.chat(payload)

    assert response["status"] == "ok"
    assert response["mode"] == "qa"
    assert response["selected_mode"] == "qa"
    assert response["session_id"] == "session-1"
    assert response["intent"] == "qa"


def test_service_detects_latest_user_message_language() -> None:
    service = AdminService(orchestrator=_FakeOrchestrator())  # type: ignore[arg-type]
    payload = AdminChatRequest(message="Quelle est la configuration actuelle ?", selected_mode="plan")

    response = service.chat(payload)

    assert response["latest_user_language"] == "fr"
