from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from app.agent.state import (
    AgentDecision,
    AgentGoal,
    AgentObservation,
    AgentPendingConfirmation,
    AgentRunState,
)


class AgentRunStateStore:
    def __init__(self, project_root: Path | None = None, state_path: Path | None = None) -> None:
        self._project_root = project_root or Path(__file__).resolve().parents[4]
        self._state_path = state_path or (
            self._project_root / "services" / "admin-service" / "data" / "agent_run_states.json"
        )

    def load(self, session_id: str) -> AgentRunState | None:
        key = str(session_id).strip()
        if not key:
            return None
        payload = self._load_all()
        state_payload = payload.get(key)
        if not isinstance(state_payload, dict):
            return None
        return self._deserialize_state(state_payload)

    def save(self, session_id: str, state: AgentRunState) -> None:
        key = str(session_id).strip()
        if not key:
            raise ValueError("session_id is required to save agent run state")
        payload = self._load_all()
        payload[key] = self._serialize_state(state)
        self._write_all(payload)

    def delete(self, session_id: str) -> None:
        key = str(session_id).strip()
        if not key:
            return
        payload = self._load_all()
        if key not in payload:
            return
        del payload[key]
        self._write_all(payload)

    def _load_all(self) -> dict[str, dict]:
        if not self._state_path.exists():
            legacy_path = self._project_root / "services" / "services" / "admin-service" / "data" / "agent_run_states.json"
            if legacy_path.exists():
                self._state_path.parent.mkdir(parents=True, exist_ok=True)
                self._state_path.write_text(legacy_path.read_text(encoding="utf-8"), encoding="utf-8")
            else:
                return {}
        try:
            payload = json.loads(self._state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    def _write_all(self, payload: dict[str, dict]) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")

    def _serialize_state(self, state: AgentRunState) -> dict:
        return asdict(state)

    def _deserialize_state(self, payload: dict) -> AgentRunState:
        goal_payload = payload.get("goal")
        pending_payload = payload.get("pending_confirmation")
        observations_payload = payload.get("observations", [])
        decisions_payload = payload.get("decision_history", [])

        return AgentRunState(
            run_id=payload.get("run_id"),
            goal=(
                AgentGoal(
                    message=str(goal_payload.get("message", "")).strip(),
                    subject=str(goal_payload.get("subject", "")).strip(),
                    desired_outcome=str(goal_payload.get("desired_outcome", "")).strip(),
                    constraints=[str(item) for item in goal_payload.get("constraints", []) if str(item).strip()],
                    success_criteria=[
                        str(item) for item in goal_payload.get("success_criteria", []) if str(item).strip()
                    ],
                )
                if isinstance(goal_payload, dict) and str(goal_payload.get("message", "")).strip()
                else None
            ),
            status=str(payload.get("status", "running")).strip() or "running",
            iteration_count=int(payload.get("iteration_count", 0) or 0),
            tool_call_count=int(payload.get("tool_call_count", 0) or 0),
            max_iterations=int(payload.get("max_iterations", 25) or 25),
            max_tool_calls=int(payload.get("max_tool_calls", 10) or 10),
            facts=payload.get("facts", {}) if isinstance(payload.get("facts"), dict) else {},
            observations=[
                AgentObservation(
                    source=str(item.get("source", "")).strip(),
                    content=str(item.get("content", "")).strip(),
                    data=item.get("data", {}) if isinstance(item.get("data"), dict) else {},
                )
                for item in observations_payload
                if isinstance(item, dict) and str(item.get("source", "")).strip()
            ],
            decision_history=[
                AgentDecision(
                    action_type=str(item.get("action_type", "")).strip(),  # type: ignore[arg-type]
                    message=str(item.get("message", "")).strip(),
                    tool_name=str(item.get("tool_name", "")).strip() or None,
                    arguments=item.get("arguments", {}) if isinstance(item.get("arguments"), dict) else {},
                    reason=str(item.get("reason", "")).strip(),
                    expected_observation=str(item.get("expected_observation", "")).strip(),
                )
                for item in decisions_payload
                if isinstance(item, dict) and str(item.get("action_type", "")).strip()
            ],
            proposed_steps=[
                item for item in payload.get("proposed_steps", []) if isinstance(item, dict)
            ],
            pending_confirmation=(
                AgentPendingConfirmation(
                    tool_name=str(pending_payload.get("tool_name", "")).strip(),
                    arguments=(
                        pending_payload.get("arguments", {})
                        if isinstance(pending_payload.get("arguments"), dict)
                        else {}
                    ),
                    reason=str(pending_payload.get("reason", "")).strip(),
                )
                if isinstance(pending_payload, dict) and str(pending_payload.get("tool_name", "")).strip()
                else None
            ),
            final_answer=str(payload.get("final_answer", "")).strip(),
            stop_reason=str(payload.get("stop_reason", "")).strip(),
        )
