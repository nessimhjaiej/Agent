from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

from app.config import Settings


class AuditLogger:
    def __init__(self, settings: Settings) -> None:
        self._path = settings.audit_log_file

    async def log_mutation(
        self,
        *,
        user_id: str,
        user_email: str,
        tool_name: str,
        service: str,
        operation: str,
        arguments: dict,
        session_id: str,
        status: str,
        result: dict,
        metadata: dict | None = None,
    ) -> str:
        event_id = f"audit_{uuid4().hex}"
        record = {
            "event_id": event_id,
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "user_id": user_id,
            "user_email": user_email,
            "session_id": session_id,
            "tool_name": tool_name,
            "service": service,
            "operation": operation,
            "arguments": arguments,
            "status": status,
            "result": result,
            "metadata": metadata or {},
        }
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")
        return event_id
