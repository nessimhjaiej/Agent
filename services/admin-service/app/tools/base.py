from typing import Protocol

from app.models import ToolExecutionResult


class AdminTool(Protocol):
    name: str

    def execute(self, arguments: dict) -> ToolExecutionResult: ...

