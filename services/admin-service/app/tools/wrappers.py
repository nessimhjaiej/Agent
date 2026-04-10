from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from app.mcp.client import MCPClient, MCPToolDescriptor, MCPToolResult


@dataclass(slots=True)
class MCPToolWrapper:
    descriptor: MCPToolDescriptor
    executor: Callable[[dict[str, Any]], Awaitable[MCPToolResult]]

    @property
    def name(self) -> str:
        return self.descriptor.name

    @property
    def description(self) -> str:
        return self.descriptor.description

    async def ainvoke(self, arguments: dict[str, Any]) -> MCPToolResult:
        return await self.executor(arguments)


async def build_tool_wrappers(client: MCPClient) -> list[MCPToolWrapper]:
    descriptors = await client.discover_tools()
    wrappers: list[MCPToolWrapper] = []
    for descriptor in descriptors:
        wrappers.append(
            MCPToolWrapper(
                descriptor=descriptor,
                executor=_build_executor(client, descriptor.name),
            )
        )
    return wrappers


def _build_executor(
    client: MCPClient,
    tool_name: str,
) -> Callable[[dict[str, Any]], Awaitable[MCPToolResult]]:
    async def _executor(arguments: dict[str, Any]) -> MCPToolResult:
        return await client.execute_tool(tool_name, arguments)

    return _executor
