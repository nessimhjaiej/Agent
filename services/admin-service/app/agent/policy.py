from __future__ import annotations

import json

from app.agent.state import AgentDecision, AgentGoal, AgentRunState
from app.tools.base import ToolMetadata


class LLMToolCatalogPolicy:
    _ALLOWED_ACTIONS = {"respond", "call_tool", "request_confirmation", "stop"}

    def __init__(self, client, tool_catalog: list[ToolMetadata]) -> None:  # noqa: ANN001
        self._client = client
        self._tool_catalog = tool_catalog
        self._tool_metadata = {tool.name: tool for tool in tool_catalog}

    def __call__(self, state: AgentRunState) -> AgentDecision:
        try:
            raw = self._client.complete_json(
                system_prompt=self._build_system_prompt(),
                user_prompt=self._build_user_prompt(state),
            ).strip()
            payload = json.loads(raw)
        except Exception:
            return self._legacy_fallback()

        decision = self._parse_and_validate(payload, state)
        if decision is None:
            return self._legacy_fallback()
        return decision

    def _build_system_prompt(self) -> str:
        return (
            "You are the recursive planning policy for an admin agent. "
            "Respond with valid JSON only. "
            "Choose exactly one next action from: respond, call_tool, request_confirmation, stop. "
            "You must choose from the provided tool catalog only. "
            "Use read-only inspection tools first when they help you reason toward the goal. "
            "If you already have enough observations to answer or recommend a next action, prefer respond instead of stop. "
            "If a mutation is appropriate, do not execute it directly; return request_confirmation and provide grounded tool arguments. "
            "If multiple actions are needed, include them in proposed_steps and set tool_name/arguments to the first mutation step when asking for confirmation. "
            "If the request is outside the safe tool catalog and should be handled by the legacy planner, "
            "return action_type='stop' and reason='fallback_legacy_planner'. "
            "Do not use fallback_legacy_planner for informational or comparative questions if the existing observations are enough to produce a useful answer. "
            "You must support multilingual user input."
        )

    def _build_user_prompt(self, state: AgentRunState) -> str:
        goal = state.goal or AgentGoal(message="")
        return json.dumps(
            {
                "goal": {
                    "message": goal.message,
                    "subject": goal.subject,
                    "desired_outcome": goal.desired_outcome,
                    "constraints": goal.constraints,
                    "success_criteria": goal.success_criteria,
                },
                "run_state": {
                    "status": state.status,
                    "iteration_count": state.iteration_count,
                    "tool_call_count": state.tool_call_count,
                    "max_iterations": state.max_iterations,
                    "max_tool_calls": state.max_tool_calls,
                    "facts": state.facts,
                    "observations": [
                        {
                            "source": item.source,
                            "content": item.content,
                            "data": item.data,
                        }
                        for item in state.observations[-8:]
                    ],
                    "decision_history": [
                        {
                            "action_type": item.action_type,
                            "message": item.message,
                            "tool_name": item.tool_name,
                            "arguments": item.arguments,
                            "reason": item.reason,
                            "expected_observation": item.expected_observation,
                        }
                        for item in state.decision_history[-8:]
                    ],
                    "proposed_steps": state.proposed_steps,
                    "pending_confirmation": (
                        {
                            "tool_name": state.pending_confirmation.tool_name,
                            "arguments": state.pending_confirmation.arguments,
                            "reason": state.pending_confirmation.reason,
                        }
                        if state.pending_confirmation is not None
                        else None
                    ),
                },
                "tool_catalog": [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "arguments_schema": tool.arguments_schema,
                        "output_description": tool.output_description,
                        "requires_confirmation": tool.requires_confirmation,
                    }
                    for tool in self._tool_catalog
                ],
                "required_output_schema": {
                    "action_type": "respond | call_tool | request_confirmation | stop",
                    "message": "string",
                    "tool_name": "string or null",
                    "arguments": "object",
                    "reason": "string",
                    "expected_observation": "string",
                    "goal_subject": "string",
                    "proposed_steps": [
                        {
                            "tool": "string",
                            "arguments": "object",
                        }
                    ],
                },
            },
            ensure_ascii=True,
            indent=2,
        )

    def _parse_and_validate(self, payload: object, state: AgentRunState) -> AgentDecision | None:
        if not isinstance(payload, dict):
            return None

        action_type = str(payload.get("action_type", "")).strip()
        if action_type not in self._ALLOWED_ACTIONS:
            return None

        goal_subject = str(payload.get("goal_subject", "")).strip()
        if goal_subject and state.goal is not None:
            state.goal.subject = goal_subject

        tool_name_raw = payload.get("tool_name")
        tool_name = str(tool_name_raw).strip() if isinstance(tool_name_raw, str) and tool_name_raw.strip() else None
        arguments = payload.get("arguments", {})
        if not isinstance(arguments, dict):
            arguments = {}
        message = str(payload.get("message", "")).strip()
        reason = str(payload.get("reason", "")).strip()
        expected_observation = str(payload.get("expected_observation", "")).strip()
        proposed_steps = self._validated_proposed_steps(payload.get("proposed_steps", []))

        if action_type == "stop":
            return AgentDecision(
                action_type="stop",
                message=message,
                reason=reason or "stopped",
            )

        if action_type == "respond":
            if not message:
                return None
            if proposed_steps:
                state.proposed_steps = proposed_steps
            return AgentDecision(
                action_type="respond",
                message=message,
                reason=reason,
                expected_observation=expected_observation,
            )

        if action_type == "call_tool":
            if tool_name is None or tool_name not in self._tool_metadata:
                return None
            metadata = self._tool_metadata[tool_name]
            if metadata.requires_confirmation:
                return None
            return AgentDecision(
                action_type="call_tool",
                message=message,
                tool_name=tool_name,
                arguments=arguments,
                reason=reason,
                expected_observation=expected_observation,
            )

        if action_type == "request_confirmation":
            if proposed_steps:
                state.proposed_steps = proposed_steps
                primary_step = proposed_steps[0]
                tool_name = primary_step["tool"]
                arguments = primary_step["arguments"]
            if tool_name is None or tool_name not in self._tool_metadata:
                return None
            metadata = self._tool_metadata[tool_name]
            if not metadata.requires_confirmation:
                return None
            if not state.proposed_steps:
                state.proposed_steps = [{"tool": tool_name, "arguments": arguments}]
            if not message:
                return None
            return AgentDecision(
                action_type="request_confirmation",
                message=message,
                tool_name=tool_name,
                arguments=arguments,
                reason=reason,
                expected_observation=expected_observation,
            )

        return None

    def _validated_proposed_steps(self, raw_steps: object) -> list[dict]:
        if not isinstance(raw_steps, list):
            return []
        steps: list[dict] = []
        for item in raw_steps:
            if not isinstance(item, dict):
                continue
            tool = str(item.get("tool", "")).strip()
            arguments = item.get("arguments", {})
            if not tool or tool not in self._tool_metadata or not isinstance(arguments, dict):
                continue
            steps.append({"tool": tool, "arguments": arguments})
        return steps

    def _legacy_fallback(self) -> AgentDecision:
        return AgentDecision(
            action_type="stop",
            reason="fallback_legacy_planner",
            message="",
        )
