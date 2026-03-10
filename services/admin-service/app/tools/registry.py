from app.errors import ToolExecutionError
from app.tools.base import AdminTool


class ToolRegistry:
    def __init__(self, tools: list[AdminTool]) -> None:
        self._tools = {tool.name: tool for tool in tools}

    def get(self, tool_name: str) -> AdminTool:
        tool = self._tools.get(tool_name)
        if tool is None:
            raise ToolExecutionError(f"Unknown admin tool: {tool_name}")
        return tool

