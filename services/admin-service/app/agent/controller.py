from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from app.agent.state import (
    AgentDecision,
    AgentObservation,
    AgentPendingConfirmation,
    AgentRunState,
)


class AgentPolicy(Protocol):
    def __call__(self, state: AgentRunState) -> AgentDecision: ...


class AgentToolExecutor(Protocol):
    def __call__(self, tool_name: str, arguments: dict) -> AgentObservation: ...


class RecursiveAgentController:
    def __init__(
        self,
        policy: AgentPolicy,
        tool_executor: AgentToolExecutor,
    ) -> None:
        self._policy = policy
        self._tool_executor = tool_executor

    def run(
        self,
        state: AgentRunState,
        progress_callback: Callable[[dict], None] | None = None,
    ) -> AgentRunState:
        while True:
            if state.iteration_count >= state.max_iterations:
                state.status = "blocked"
                state.stop_reason = "max_iterations_reached"
                return state
            if state.tool_call_count >= state.max_tool_calls:
                state.status = "blocked"
                state.stop_reason = "max_tool_calls_reached"
                return state

            state.iteration_count += 1
            decision = self._policy(state)
            state.decision_history.append(decision)
            self._emit(
                progress_callback,
                {
                    "type": "agent_decision",
                    "iteration": state.iteration_count,
                    "decision": {
                        "action_type": decision.action_type,
                        "message": decision.message,
                        "tool_name": decision.tool_name,
                        "arguments": decision.arguments,
                        "reason": decision.reason,
                        "expected_observation": decision.expected_observation,
                    },
                },
            )

            if decision.action_type == "call_tool":
                self._execute_tool(state, decision, progress_callback)
                if state.status == "failed":
                    return state
                continue

            if decision.action_type == "request_confirmation":
                if not decision.tool_name:
                    state.status = "failed"
                    state.stop_reason = "missing_confirmation_tool_name"
                    state.final_answer = "The agent requested confirmation without specifying a tool."
                    return state
                state.pending_confirmation = AgentPendingConfirmation(
                    tool_name=decision.tool_name,
                    arguments=decision.arguments,
                    reason=decision.reason or decision.message,
                )
                state.status = "paused_for_confirmation"
                state.final_answer = decision.message
                state.stop_reason = "confirmation_required"
                return state

            if decision.action_type == "respond":
                state.status = "completed"
                state.final_answer = decision.message
                state.stop_reason = "responded"
                return state

            if decision.action_type == "stop":
                state.status = "completed"
                if decision.message:
                    state.final_answer = decision.message
                state.stop_reason = decision.reason or "stopped"
                return state

            state.status = "failed"
            state.stop_reason = "unsupported_action"
            state.final_answer = f"Unsupported agent action '{decision.action_type}'."
            return state

    def _execute_tool(
        self,
        state: AgentRunState,
        decision: AgentDecision,
        progress_callback: Callable[[dict], None] | None = None,
    ) -> None:
        if not decision.tool_name:
            state.status = "failed"
            state.stop_reason = "missing_tool_name"
            state.final_answer = "The agent attempted a tool call without a tool name."
            return

        state.tool_call_count += 1
        self._emit(
            progress_callback,
            {
                "type": "agent_tool_call",
                "iteration": state.iteration_count,
                "tool_name": decision.tool_name,
                "arguments": decision.arguments,
            },
        )
        try:
            observation = self._tool_executor(decision.tool_name, decision.arguments)
        except Exception as exc:
            state.status = "failed"
            state.stop_reason = "tool_execution_failed"
            state.final_answer = f"Tool '{decision.tool_name}' failed: {exc}"
            state.observations.append(
                AgentObservation(
                    source=decision.tool_name,
                    content=f"Tool execution failed: {exc}",
                    data={"error": str(exc)},
                )
            )
            return

        state.observations.append(observation)
        self._emit(
            progress_callback,
            {
                "type": "agent_observation",
                "iteration": state.iteration_count,
                "observation": {
                    "source": observation.source,
                    "content": observation.content,
                    "data": observation.data,
                },
            },
        )

    def _emit(
        self,
        progress_callback: Callable[[dict], None] | None,
        payload: dict,
    ) -> None:
        if progress_callback is None:
            return
        progress_callback(payload)
