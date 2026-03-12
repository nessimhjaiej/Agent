from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class AdminOperationHistoryStore:
    def __init__(self, project_root: Path | None = None, history_path: Path | None = None) -> None:
        self._project_root = project_root or Path(__file__).resolve().parents[3]
        self._history_path = history_path or (
            self._project_root / "services" / "admin-service" / "data" / "operation_history.json"
        )

    def append(self, record: dict) -> None:
        payload = self._load_all()
        payload.append(
            {
                **record,
                "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            }
        )
        self._write_all(payload)

    def get_recent(
        self,
        session_id: str,
        limit: int = 1,
        tool_names: list[str] | None = None,
    ) -> list[dict]:
        if not session_id.strip():
            return []
        items = [
            item
            for item in reversed(self._load_all())
            if item.get("session_id") == session_id and item.get("reversible") is True
        ]
        if tool_names:
            allowed = set(tool_names)
            items = [item for item in items if item.get("tool_name") in allowed]
        return items[:limit]

    def _load_all(self) -> list[dict]:
        if not self._history_path.exists():
            return []
        try:
            payload = json.loads(self._history_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
        return payload if isinstance(payload, list) else []

    def _write_all(self, payload: list[dict]) -> None:
        self._history_path.parent.mkdir(parents=True, exist_ok=True)
        self._history_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
