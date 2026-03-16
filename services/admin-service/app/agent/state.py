from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


AgentActionType = Literal["respond", "call_tool", "request_confirmation", "stop"]
AgentRunStatus = Literal["running", "paused_for_confirmation", "completed", "blocked", "failed"]


@dataclass(slots=True)
class AgentGoal:
    message: str
    subject: str = ""
    desired_outcome: str = ""
    constraints: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)


@dataclass(slots=True)
class AgentObservation:
    source: str
    content: str = ""
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AgentPendingConfirmation:
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    reason: str = ""


@dataclass(slots=True)
class AgentDecision:
    action_type: AgentActionType
    message: str = ""
    tool_name: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    expected_observation: str = ""


@dataclass(slots=True)
class AgentRunState:
    run_id: str | None = None
    goal: AgentGoal | None = None
    status: AgentRunStatus = "running"
    iteration_count: int = 0
    tool_call_count: int = 0
    max_iterations: int = 25
    max_tool_calls: int = 10
    facts: dict[str, Any] = field(default_factory=dict)
    observations: list[AgentObservation] = field(default_factory=list)
    decision_history: list[AgentDecision] = field(default_factory=list)
    proposed_steps: list[dict[str, Any]] = field(default_factory=list)
    pending_confirmation: AgentPendingConfirmation | None = None
    final_answer: str = ""
    stop_reason: str = ""
