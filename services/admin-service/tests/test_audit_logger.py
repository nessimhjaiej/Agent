import asyncio
import json
from pathlib import Path

from app.audit.history import AuditLogger
from app.config import Settings


def test_audit_logger_records_mutation_outcome(tmp_path: Path) -> None:
    async def scenario() -> None:
        settings = Settings(
            audit_log_path=str(tmp_path / "audit_history.jsonl"),
            state_log_path=str(tmp_path / "session_state.json"),
        )
        logger = AuditLogger(settings)
        event_id = await logger.log_mutation(
            user_id="admin-1",
            user_email="admin@example.com",
            tool_name="restart_service",
            service="platform-runtime",
            operation="restart_service",
            arguments={"service_name": "retrieval-service"},
            session_id="session-1",
            status="accepted",
            result={"status": "accepted", "service_name": "retrieval-service"},
            metadata={"trace_id": "trace-1"},
        )
        assert event_id.startswith("audit_")

        lines = settings.audit_log_file.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["tool_name"] == "restart_service"
        assert record["service"] == "platform-runtime"
        assert record["operation"] == "restart_service"
        assert record["status"] == "accepted"
        assert record["result"]["service_name"] == "retrieval-service"
        assert record["metadata"]["trace_id"] == "trace-1"

    asyncio.run(scenario())
