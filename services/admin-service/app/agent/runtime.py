from __future__ import annotations

import os
from typing import Any, Literal

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.config import Settings
from app.mcp.client import MCPClient, MCPToolDescriptor, MCPToolSelection


class AgentPlannedTool(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""


class AgentDecision(BaseModel):
    intent: Literal["qa", "diagnostic", "mutation"] = "qa"
    tool_calls: list[AgentPlannedTool] = Field(default_factory=list)
    answer: str = ""
    rationale: str = ""


class AdminAgentRuntime:
    def __init__(self, settings: Settings, mcp_client: MCPClient) -> None:
        self._settings = settings
        self._mcp_client = mcp_client

    async def decide(
        self,
        *,
        message: str,
        chat_history: list[dict[str, str]],
    ) -> AgentDecision:
        tools = await self._mcp_client.discover_tools()
        if not self._should_use_llm():
            return await self._fallback_decision(message, tools)

        try:
            prompt = ChatPromptTemplate.from_messages(
                [
                    (
                        "system",
                        "You are the decision layer for an admin control-plane. "
                        f"Choose at most {self._settings.agent_max_plan_steps} tools from the available MCP tools when the request needs operational inspection or execution. "
                        "Do not invent tools. If no tool is required, return a direct answer. "
                        "Prefer a short inspect-then-act sequence when needed, but keep the plan minimal and bounded.",
                    ),
                    (
                        "human",
                        "Available tools:\n{tools}\n\n"
                        "Recent conversation:\n{history}\n\n"
                        "Admin message:\n{message}\n\n"
                        "Return a structured decision.",
                    ),
                ]
            )
            model = ChatOpenAI(
                api_key=self._settings.openai_key,
                model=self._settings.planner_model,
                temperature=0,
            )
            chain = prompt | model.with_structured_output(AgentDecision)
            decision = await chain.ainvoke(
                {
                    "tools": self._format_tools(tools),
                    "history": self._format_history(chat_history),
                    "message": message,
                }
            )
        except Exception:
            fallback = await self._fallback_decision(message, tools)
            fallback.rationale = (
                "The model-driven decision layer failed, so the deterministic fallback selector was used."
            )
            return fallback
        normalized = self._normalize_decision(decision, tools)
        if normalized is None:
            fallback = await self._fallback_decision(message, tools)
            fallback.rationale = (
                "The model produced an invalid or unsafe plan shape, so the deterministic fallback selector was used."
            )
            return fallback
        if not normalized.tool_calls:
            fallback = await self._fallback_decision(message, tools)
            if fallback.tool_calls:
                fallback.rationale = (
                    "The model returned no actionable tool, so the deterministic fallback selector was used."
                )
                return fallback
        return normalized

    async def synthesize_tool_response(
        self,
        *,
        message: str,
        tool_name: str,
        tool_result: dict[str, Any],
        is_mutation: bool,
    ) -> str:
        if not self._should_use_llm():
            return self._fallback_tool_response(tool_name=tool_name, tool_result=tool_result, is_mutation=is_mutation)

        try:
            prompt = ChatPromptTemplate.from_messages(
                [
                    (
                        "system",
                        "You are an admin operations assistant. Summarize tool results clearly and conservatively. "
                        "Do not claim side effects beyond the provided result.",
                    ),
                    (
                        "human",
                        "Admin request:\n{message}\n\n"
                        "Tool name: {tool_name}\n"
                        "Tool mode: {tool_mode}\n"
                        "Tool result:\n{tool_result}\n\n"
                        "Write a short operator-facing response.",
                    ),
                ]
            )
            model = ChatOpenAI(
                api_key=self._settings.openai_key,
                model=self._settings.planner_model,
                temperature=0,
            )
            chain = prompt | model
            response = await chain.ainvoke(
                {
                    "message": message,
                    "tool_name": tool_name,
                    "tool_mode": "mutation" if is_mutation else "diagnostic",
                    "tool_result": tool_result,
                }
            )
            content = getattr(response, "content", "")
            if isinstance(content, str) and content.strip():
                return content.strip()
            if isinstance(content, list):
                parts = [part.get("text", "") for part in content if isinstance(part, dict)]
                joined = "".join(parts).strip()
                if joined:
                    return joined
            return f"The tool '{tool_name}' completed, but the response synthesizer returned no text."
        except Exception:
            return self._fallback_tool_response(tool_name=tool_name, tool_result=tool_result, is_mutation=is_mutation)

    async def _fallback_decision(
        self,
        message: str,
        tools: list[MCPToolDescriptor],
    ) -> AgentDecision:
        selections = await self._fallback_plan(message)
        if not selections:
            return AgentDecision(
                intent="qa",
                answer=(
                    "Admin-service v2 is initialized with the new contract, session state model, and confirmation contract. "
                    "Agent reasoning will be added next. The MCP adapter, sliding-window memory, and metadata-driven tool policy are now in place."
                ),
                rationale="No MCP tool matched the request, so the service returned a direct platform status answer.",
            )

        intent: Literal["qa", "diagnostic", "mutation"] = "diagnostic"
        if any(
            tool.name == call.tool_name and tool.mutation
            for call in selections
            for tool in tools
        ):
            intent = "mutation"
        return AgentDecision(
            intent=intent,
            tool_calls=[
                AgentPlannedTool(
                    tool_name=selection.tool_name,
                    arguments=dict(selection.arguments),
                    rationale=selection.rationale,
                )
                for selection in selections[: self._settings.agent_max_plan_steps]
            ],
            rationale="Deterministic fallback selected a bounded tool plan.",
        )

    def _normalize_decision(
        self,
        decision: AgentDecision,
        tools: list[MCPToolDescriptor],
    ) -> AgentDecision | None:
        if not decision.tool_calls:
            return AgentDecision(
                intent=decision.intent,
                tool_calls=[],
                answer=decision.answer,
                rationale=decision.rationale,
            )

        tool_map = {tool.name: tool for tool in tools}
        normalized_calls: list[AgentPlannedTool] = []
        seen: set[tuple[str, tuple[tuple[str, Any], ...]]] = set()

        for call in decision.tool_calls[: self._settings.agent_max_plan_steps]:
            descriptor = tool_map.get(call.tool_name)
            if descriptor is None:
                return None
            key = (call.tool_name, tuple(sorted(call.arguments.items())))
            if key in seen:
                continue
            seen.add(key)
            normalized_calls.append(call)

        if not normalized_calls:
            return AgentDecision(
                intent="qa",
                tool_calls=[],
                answer=decision.answer,
                rationale=decision.rationale,
            )

        read_only = [call for call in normalized_calls if not tool_map[call.tool_name].mutation]
        mutations = [call for call in normalized_calls if tool_map[call.tool_name].mutation]

        if len(mutations) > 1:
            mutations = mutations[:1]

        ordered_calls = [*read_only, *mutations][: self._settings.agent_max_plan_steps]

        intent: Literal["qa", "diagnostic", "mutation"] = "diagnostic"
        if mutations:
            intent = "mutation"
        if not ordered_calls:
            intent = "qa"

        return AgentDecision(
            intent=intent,
            tool_calls=ordered_calls,
            answer=decision.answer if not ordered_calls else "",
            rationale=decision.rationale,
        )

    def _should_use_llm(self) -> bool:
        if os.getenv("PYTEST_CURRENT_TEST"):
            return False
        return bool(self._settings.openai_key.strip())

    def _format_tools(self, tools: list[MCPToolDescriptor]) -> str:
        lines = []
        for tool in tools:
            lines.append(
                f"- {tool.name}: {tool.description} | service={tool.service} | "
                f"mutation={tool.mutation} | requires_confirmation={tool.requires_confirmation}"
            )
        return "\n".join(lines)

    def _format_history(self, history: list[dict[str, str]]) -> str:
        if not history:
            return "(no prior conversation)"
        return "\n".join(f"{item.get('role', 'user')}: {item.get('content', '')}" for item in history[-6:])

    async def synthesize_plan_response(
        self,
        *,
        message: str,
        completed_tools: list[dict[str, Any]],
    ) -> str:
        if not completed_tools:
            return ""
        if len(completed_tools) == 1:
            tool = completed_tools[0]
            return await self.synthesize_tool_response(
                message=message,
                tool_name=str(tool.get("tool_name", "")),
                tool_result=dict(tool.get("result", {})),
                is_mutation=bool(tool.get("mutation", False)),
            )
        if not self._should_use_llm():
            return self._fallback_plan_response(completed_tools)

        try:
            prompt = ChatPromptTemplate.from_messages(
                [
                    (
                        "system",
                        "You are an admin operations assistant. Summarize the outcome of a short multi-step tool run. "
                        "Be concise and avoid claiming anything not present in the tool outputs.",
                    ),
                    (
                        "human",
                        "Admin request:\n{message}\n\nCompleted tool steps:\n{completed_tools}\n\nWrite a short operator-facing summary.",
                    ),
                ]
            )
            model = ChatOpenAI(
                api_key=self._settings.openai_key,
                model=self._settings.planner_model,
                temperature=0,
            )
            chain = prompt | model
            response = await chain.ainvoke({"message": message, "completed_tools": completed_tools})
            content = getattr(response, "content", "")
            if isinstance(content, str) and content.strip():
                return content.strip()
            return f"Completed {len(completed_tools)} tool steps."
        except Exception:
            return self._fallback_plan_response(completed_tools)

    async def _fallback_plan(self, message: str) -> list[MCPToolSelection]:
        lowered = message.lower()
        separators = [" and then ", " then ", " and "]
        clauses = [message]
        for separator in separators:
            if separator in lowered:
                clauses = [part.strip() for part in message.split(separator) if part.strip()]
                break

        selections: list[MCPToolSelection] = []
        for clause in clauses:
            selection = await self._mcp_client.select_tool_for_message(clause)
            if selection is not None:
                selections.append(selection)
        deduped: list[MCPToolSelection] = []
        seen: set[tuple[str, tuple[tuple[str, Any], ...]]] = set()
        for selection in selections:
            key = (selection.tool_name, tuple(sorted(selection.arguments.items())))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(selection)
        return deduped[: self._settings.agent_max_plan_steps]

    def _fallback_tool_response(
        self,
        *,
        tool_name: str,
        tool_result: dict[str, Any],
        is_mutation: bool,
    ) -> str:
        if tool_name in {"show_config", "get_chunking_config"}:
            config = tool_result.get("config", {})
            service_name = str(tool_result.get("service_name", "the target service"))
            if isinstance(config, dict):
                chunk_strategy = config.get("chunk_strategy")
                chunk_size = config.get("chunk_size")
                chunk_overlap = config.get("chunk_overlap")
                if chunk_strategy is not None and chunk_size is not None and chunk_overlap is not None:
                    return (
                        f"The current chunking strategy in {service_name} is '{chunk_strategy}' "
                        f"with chunk size {chunk_size} and overlap {chunk_overlap}."
                    )
            return f"I loaded the current runtime configuration from {service_name} and returned the relevant settings."
        if tool_name == "get_retrieval_config":
            config = tool_result.get("config", {})
            service_name = str(tool_result.get("service_name", "retrieval-service"))
            if isinstance(config, dict):
                return (
                    f"The current retrieval defaults in {service_name} use fusion '{config.get('fusion_type')}' "
                    f"with top_k_retrieve {config.get('top_k_retrieve')} and top_k_return {config.get('top_k_return')}."
                )
        if tool_name == "get_reranking_config":
            config = tool_result.get("config", {})
            service_name = str(tool_result.get("service_name", "retrieval-service"))
            if isinstance(config, dict):
                return (
                    f"The current reranking strategy in {service_name} is '{config.get('ranker_type')}' "
                    f"with rerank top N {config.get('rerank_top_n')}."
                )
        if tool_name in {"update_chunking_config", "update_retrieval_config", "update_reranking_config"}:
            service_name = str(tool_result.get("service_name", "the target service"))
            updated = tool_result.get("updated", {})
            updated_fields = ", ".join(f"{key}={value}" for key, value in updated.items()) if isinstance(updated, dict) else ""
            return (
                f"Updated configuration for {service_name}"
                + (f": {updated_fields}." if updated_fields else ".")
                + " A service restart is required for the new settings to take effect."
            )
        if is_mutation:
            return f"The tool '{tool_name}' completed successfully through the MCP adapter."
        return f"I executed the read-only tool '{tool_name}' and returned its result."

    def _fallback_plan_response(self, completed_tools: list[dict[str, Any]]) -> str:
        labels = ", ".join(str(item.get("tool_name", "")) for item in completed_tools)
        return f"Completed {len(completed_tools)} tool steps through the MCP adapter: {labels}."
