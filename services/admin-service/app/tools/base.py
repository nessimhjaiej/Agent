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


class AdminTool(Protocol):
    name: str
    metadata: ToolMetadata

    def execute(self, arguments: dict) -> ToolExecutionResult: ...
