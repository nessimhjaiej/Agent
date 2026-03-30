from dataclasses import dataclass, field
from typing import Any, Protocol

from app.models import ToolExecutionResult


@dataclass(slots=True)
class ToolMetadata:
    name: str
    description: str
    arguments_schema: dict[str, Any] = field(default_factory=dict)
    output_description: str = ""
    planning_enabled: bool = True
    requires_confirmation: bool = False
    goal_tags: list[str] = field(default_factory=list)
    affects: list[str] = field(default_factory=list)
    impact_summary: str = ""
    expected_tradeoffs: list[str] = field(default_factory=list)
    best_for: list[str] = field(default_factory=list)
    risk_level: str = "low"
    requires_reindex: bool = False
    requires_restart: bool = False
    typical_followups: list[str] = field(default_factory=list)


class AdminTool(Protocol):
    name: str
    metadata: ToolMetadata

    def execute(self, arguments: dict) -> ToolExecutionResult: ...
