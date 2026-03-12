from app.errors import ToolExecutionError
from app.tools.base import AdminTool, ToolMetadata


class ToolRegistry:
    def __init__(self, tools: list[AdminTool]) -> None:
        self._tools = {tool.name: tool for tool in tools}
        self._metadata = {
            name: getattr(tool, "metadata", ToolMetadata(name=name, description=""))
            for name, tool in self._tools.items()
        }

    def get(self, tool_name: str) -> AdminTool:
        tool = self._tools.get(tool_name)
        if tool is None:
            raise ToolExecutionError(f"Unknown admin tool: {tool_name}")
        return tool

    def has(self, tool_name: str) -> bool:
        return tool_name in self._tools

    def planning_tools(self) -> list[ToolMetadata]:
        return [
            metadata
            for metadata in self._metadata.values()
            if metadata.planning_enabled and metadata.description.strip()
        ]
