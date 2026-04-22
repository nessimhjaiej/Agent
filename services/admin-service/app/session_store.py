from __future__ import annotations

import json
from pathlib import Path
from time import time
from uuid import uuid4


class SessionStore:
    def __init__(self, path: str) -> None:
        self._path = Path(path)

    def ensure_session_id(self, session_id: str | None) -> str:
        return session_id.strip() if session_id and session_id.strip() else str(uuid4())

    def load(self, session_id: str) -> dict:
        payload = self._read_all()
        return payload.get(session_id, {}) if isinstance(payload, dict) else {}

    def save(self, session_id: str, data: dict) -> None:
        payload = self._read_all()
        payload[session_id] = self._compact_session(data)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def append_turn(self, session_id: str, role: str, content: str) -> None:
        payload = self._read_all()
        session = payload.get(session_id, {})
        if not isinstance(session, dict):
            session = {}
        history = session.get("history", [])
        if not isinstance(history, list):
            history = []
        history.append({"role": role, "content": content})
        session["history"] = history[-12:]
        payload[session_id] = session
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def clear_pending_action(self, session_id: str) -> None:
        payload = self._read_all()
        session = payload.get(session_id, {})
        if isinstance(session, dict):
            session["pending_action"] = None
            session["pending_executed_steps"] = []
            session["workflow_tasks"] = []
            session["active_task_index"] = 0
            payload[session_id] = session
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def upsert_tool_cache(self, session_id: str, entries: dict) -> None:
        payload = self._read_all()
        session = payload.get(session_id, {})
        if not isinstance(session, dict):
            session = {}
        tool_cache = session.get("tool_cache", {})
        if not isinstance(tool_cache, dict):
            tool_cache = {}
        for key, value in entries.items():
            tool_cache[key] = value
        if len(tool_cache) > 12:
            ordered = sorted(
                tool_cache.items(),
                key=lambda item: float(item[1].get("created_at", 0) if isinstance(item[1], dict) else 0),
                reverse=True,
            )
            tool_cache = dict(ordered[:12])
        session["tool_cache"] = tool_cache
        payload[session_id] = session
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def invalidate_tool_cache(self, session_id: str, tags: list[str] | None = None) -> None:
        payload = self._read_all()
        session = payload.get(session_id, {})
        if not isinstance(session, dict):
            return
        if not tags:
            session["tool_cache"] = {}
        else:
            tool_cache = session.get("tool_cache", {})
            if isinstance(tool_cache, dict):
                kept = {}
                for key, entry in tool_cache.items():
                    entry_tags = entry.get("tags", []) if isinstance(entry, dict) else []
                    if not any(tag in entry_tags for tag in tags):
                        kept[key] = entry
                session["tool_cache"] = kept
        session["cache_invalidated_at"] = time()
        payload[session_id] = session
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _read_all(self) -> dict:
        if not self._path.exists():
            return {}
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _compact_session(self, data: dict) -> dict:
        session = dict(data) if isinstance(data, dict) else {}
        history = session.get("history", [])
        if isinstance(history, list):
            session["history"] = history[-6:]
        else:
            session["history"] = []

        tool_cache = session.get("tool_cache", {})
        if isinstance(tool_cache, dict):
            ordered = sorted(
                tool_cache.items(),
                key=lambda item: float(item[1].get("created_at", 0) if isinstance(item[1], dict) else 0),
                reverse=True,
            )
            session["tool_cache"] = dict(ordered[:8])
        else:
            session["tool_cache"] = {}

        last_result = session.get("last_result")
        if isinstance(last_result, dict):
            session["last_result"] = {
                "route": last_result.get("route"),
                "tool_result": self._compact_tool_result(last_result.get("tool_result")),
            }
        else:
            session["last_result"] = {}

        for key in list(session.keys()):
            if key not in {
                "history",
                "tool_cache",
                "pending_action",
                "pending_executed_steps",
                "workflow_tasks",
                "active_task_index",
                "last_message",
                "last_response",
                "last_route",
                "last_topic",
                "last_result",
                "access_token",
                "cache_invalidated_at",
            }:
                session.pop(key, None)
        pending_steps = session.get("pending_executed_steps", [])
        if isinstance(pending_steps, list):
            session["pending_executed_steps"] = pending_steps[-10:]
        else:
            session["pending_executed_steps"] = []
        workflow_tasks = session.get("workflow_tasks", [])
        if isinstance(workflow_tasks, list):
            session["workflow_tasks"] = workflow_tasks[-20:]
        else:
            session["workflow_tasks"] = []
        active_task_index = session.get("active_task_index", 0)
        session["active_task_index"] = active_task_index if isinstance(active_task_index, int) and active_task_index >= 0 else 0
        return session

    def _compact_tool_result(self, tool_result: object) -> dict:
        if not isinstance(tool_result, dict):
            return {}
        compact = dict(tool_result)
        if "documents" in compact and isinstance(compact["documents"], list):
            compact["documents"] = compact["documents"][:3]
        if "reports" in compact and isinstance(compact["reports"], list):
            compact["reports"] = compact["reports"][:3]
        return compact
