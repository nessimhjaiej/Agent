from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AdminChatTurn:
    role: str
    content: str


@dataclass(slots=True)
class AdminActor:
    id: str
    email: str
    role: str


@dataclass(slots=True)
class PlanStep:
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PendingAction:
    intent: str
    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    steps: list[PlanStep] = field(default_factory=list)


@dataclass(slots=True)
class AdminRequestContext:
    message: str
    selected_mode: str = "qa"
    session_id: str | None = None
    confirm: bool = False
    actor: AdminActor | None = None
    pending_action: PendingAction | None = None
    chat_history: list[AdminChatTurn] = field(default_factory=list)


@dataclass(slots=True)
class PlannedAction:
    mode: str
    intent: str
    tool_name: str | None
    arguments: dict[str, Any] = field(default_factory=dict)
    answer: str = ""
    requires_confirmation: bool = False
    steps: list[PlanStep] = field(default_factory=list)


@dataclass(slots=True)
class ToolExecutionResult:
    status: str
    answer: str
    result: dict[str, Any] = field(default_factory=dict)
    executed: bool = True
