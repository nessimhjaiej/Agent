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

def test_service_maps_request_to_orchestrator_response() -> None:
    service = AdminService(orchestrator=_FakeOrchestrator())  # type: ignore[arg-type]
    payload = AdminChatRequest(message="show pipeline status", session_id="session-1")

    response = service.chat(payload)

    assert response["status"] == "ok"
    assert response["mode"] == "qa"
    assert response["session_id"] == "session-1"
    assert response["intent"] == "qa"
