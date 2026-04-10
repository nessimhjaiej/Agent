from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from app.agent.confirmation import ConfirmationManager
from app.agent.memory import SessionMemoryStore
from app.agent.nodes import (
    advance_plan_node,
    build_initial_state,
    confirmation_gate_node,
    execute_tool_node,
    load_session_node,
    persist_state_node,
    resume_confirmation_node,
    select_tool_node,
)
from app.agent.runtime import AdminAgentRuntime
from app.audit.history import AuditLogger
from app.config import Settings
from app.mcp.client import MCPClient
from app.schemas import (
    AdminChatRequest,
    AdminChatResponse,
    AuditInfo,
    ConfirmationEnvelope,
    PendingAction,
    RunStep,
    RunSummary,
    StreamEvent,
    ToolResult,
)


class AdminAgentState(BaseModel):
    session_id: str
    user_id: str
    user_email: str
    message: str
    chat_history: list[dict[str, str]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    request_confirmation: bool = False
    request_confirmation_id: str | None = None
    confirmation_requested: bool = False
    confirmation_id: str | None = None
    pending_action: ConfirmationEnvelope | None = None
    planned_tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    current_tool_index: int = 0
    completed_tool_results: list[dict[str, Any]] = Field(default_factory=list)
    selected_tool: str | None = None
    selected_tool_arguments: dict[str, Any] = Field(default_factory=dict)
    selected_tool_service: str | None = None
    selected_tool_operation: str | None = None
    selected_tool_requires_confirmation: bool = False
    selected_tool_mutation: bool = False
    last_tool_name: str | None = None
    last_tool_arguments: dict[str, Any] = Field(default_factory=dict)
    last_tool_result: dict[str, Any] | None = None
    mode: Literal["qa", "diagnostic", "mutation"] = "qa"
    answer: str = ""
    status: Literal["ok", "needs_confirmation", "error"] = "ok"
    audit_event_id: str | None = None
    updated_at_utc: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AdminAgentGraph:
    def __init__(
        self,
        *,
        settings: Settings,
        memory: SessionMemoryStore,
        audit: AuditLogger,
        mcp_client: MCPClient,
    ) -> None:
        self._settings = settings
        self._memory = memory
        self._audit = audit
        self._mcp_client = mcp_client
        self._confirmation = ConfirmationManager(memory)
        self._runtime = AdminAgentRuntime(settings, mcp_client)
        self._workflow = self._build_workflow()

    async def invoke(self, request: AdminChatRequest) -> AdminChatResponse:
        initial_state = self._initial_state(request)
        final_payload = await self._workflow.ainvoke(initial_state.model_dump(mode="json"))
        final_state = AdminAgentState.model_validate(final_payload)
        return self._to_response(final_state)

    async def stream(self, request: AdminChatRequest) -> AsyncIterator[StreamEvent]:
        initial_state = self._initial_state(request)
        current_state = initial_state.model_copy(deep=True)

        yield self._event("session_started", request.session_id, {"message": request.message})
        yield self._event("agent_status", request.session_id, {"status": "loading_session_state"})

        try:
            async for update in self._workflow.astream(initial_state.model_dump(mode="json"), stream_mode="updates"):
                node_name, payload = next(iter(update.items()))
                current_state = current_state.model_copy(update=payload)
                for event in self._events_for_node(node_name, current_state):
                    yield event
        except Exception as exc:
            current_state = current_state.model_copy(
                update={
                    "status": "error",
                    "mode": "qa",
                    "answer": f"Admin-service streaming failed: {exc}",
                }
            )
            yield self._event("error", request.session_id, {"message": current_state.answer})

        if current_state.answer:
            yield self._event("response_delta", current_state.session_id, {"delta": current_state.answer})
        yield StreamEvent(type="final", session_id=current_state.session_id, response=self._to_response(current_state))

    def _build_workflow(self):
        workflow = StateGraph(AdminAgentState)

        workflow.add_node("load_session", self._load_session)
        workflow.add_node("resume_confirmation", self._resume_confirmation)
        workflow.add_node("select_tool", self._select_tool)
        workflow.add_node("confirmation_gate", self._confirmation_gate)
        workflow.add_node("execute_tool", self._execute_tool)
        workflow.add_node("advance_plan", self._advance_plan)
        workflow.add_node("persist_state", self._persist_state)

        workflow.add_edge(START, "load_session")
        workflow.add_conditional_edges(
            "load_session",
            self._route_after_load,
            {
                "resume_confirmation": "resume_confirmation",
                "select_tool": "select_tool",
            },
        )
        workflow.add_conditional_edges(
            "resume_confirmation",
            self._route_after_resume,
            {
                "execute_tool": "execute_tool",
                "persist_state": "persist_state",
            },
        )
        workflow.add_conditional_edges(
            "select_tool",
            self._route_after_selection,
            {
                "confirmation_gate": "confirmation_gate",
                "execute_tool": "execute_tool",
                "persist_state": "persist_state",
            },
        )
        workflow.add_edge("confirmation_gate", "persist_state")
        workflow.add_conditional_edges(
            "execute_tool",
            self._route_after_execute,
            {
                "advance_plan": "advance_plan",
                "persist_state": "persist_state",
            },
        )
        workflow.add_conditional_edges(
            "advance_plan",
            self._route_after_advance,
            {
                "confirmation_gate": "confirmation_gate",
                "execute_tool": "execute_tool",
                "persist_state": "persist_state",
            },
        )
        workflow.add_edge("persist_state", END)

        return workflow.compile()

    def _initial_state(self, request: AdminChatRequest) -> AdminAgentState:
        return build_initial_state(
            session_id=request.session_id,
            user_id=request.user.id,
            user_email=request.user.email,
            message=request.message,
            chat_history=[{"role": item.role, "content": item.content} for item in request.chat_history],
            metadata=request.metadata.model_dump(mode="json"),
            request_confirmation=request.confirmation.confirm,
            request_confirmation_id=request.confirmation.confirmation_id,
        )

    async def _load_session(self, state: AdminAgentState) -> dict[str, Any]:
        return await load_session_node(state, self._memory)

    async def _resume_confirmation(self, state: AdminAgentState) -> dict[str, Any]:
        return await resume_confirmation_node(state, self._confirmation)

    async def _select_tool(self, state: AdminAgentState) -> dict[str, Any]:
        return await select_tool_node(state, self._runtime, self._mcp_client)

    async def _confirmation_gate(self, state: AdminAgentState) -> dict[str, Any]:
        return await confirmation_gate_node(state, self._confirmation, self._settings.session_ttl_seconds)

    async def _execute_tool(self, state: AdminAgentState) -> dict[str, Any]:
        return await execute_tool_node(state, self._runtime, self._mcp_client, self._audit)

    async def _advance_plan(self, state: AdminAgentState) -> dict[str, Any]:
        return await advance_plan_node(state, self._runtime)

    async def _persist_state(self, state: AdminAgentState) -> dict[str, Any]:
        return await persist_state_node(state, self._memory)

    def _route_after_load(self, state: AdminAgentState) -> str:
        return "resume_confirmation" if state.request_confirmation else "select_tool"

    def _route_after_resume(self, state: AdminAgentState) -> str:
        if state.status == "error" or state.selected_tool is None:
            return "persist_state"
        return "execute_tool"

    def _route_after_selection(self, state: AdminAgentState) -> str:
        if state.status == "error":
            return "persist_state"
        if state.selected_tool is None:
            return "persist_state"
        if state.selected_tool_requires_confirmation:
            return "confirmation_gate"
        return "execute_tool"

    def _route_after_execute(self, state: AdminAgentState) -> str:
        if state.status == "error":
            return "persist_state"
        if state.current_tool_index + 1 < len(state.planned_tool_calls):
            return "advance_plan"
        return "persist_state"

    def _route_after_advance(self, state: AdminAgentState) -> str:
        if state.status == "error" or state.selected_tool is None:
            return "persist_state"
        if state.selected_tool_requires_confirmation:
            return "confirmation_gate"
        return "execute_tool"

    def _to_response(self, state: AdminAgentState) -> AdminChatResponse:
        return AdminChatResponse(
            status=state.status,
            session_id=state.session_id,
            message=state.message,
            mode=state.mode,
            answer=state.answer,
            requires_confirmation=bool(state.pending_action),
            confirmation_id=state.confirmation_id,
            confirmation_expires_at_utc=(
                state.pending_action.expires_at_utc if state.pending_action is not None else None
            ),
            pending_action=(
                PendingAction(
                    confirmation_id=state.pending_action.confirmation_id,
                    tool_name=state.pending_action.tool_name,
                    arguments=state.pending_action.arguments,
                    reason=state.pending_action.reason,
                    expires_at_utc=state.pending_action.expires_at_utc,
                )
                if state.pending_action is not None
                else None
            ),
            tool_result=(
                ToolResult(
                    tool_name=state.last_tool_name,
                    arguments=state.last_tool_arguments,
                    result=state.last_tool_result,
                )
                if state.last_tool_name is not None and state.last_tool_result is not None
                else None
            ),
            run_summary=self._run_summary(state),
            audit=AuditInfo(logged=state.audit_event_id is not None, event_id=state.audit_event_id),
        )

    def _events_for_node(self, node_name: str, state: AdminAgentState) -> list[StreamEvent]:
        if node_name == "load_session":
            return []
        if node_name == "resume_confirmation":
            if state.status == "error":
                return [
                    self._event("agent_status", state.session_id, {"status": "resuming_confirmation"}),
                    self._event("error", state.session_id, {"message": state.answer}),
                ]
            return [
                self._event("agent_status", state.session_id, {"status": "resuming_confirmation"}),
            ]
        if node_name == "select_tool":
            if state.status == "error":
                return [self._event("error", state.session_id, {"message": state.answer})]
            if state.selected_tool is None:
                return [self._event("agent_status", state.session_id, {"status": "graph_contract_ready"})]
            return [
                self._event(
                    "tool_discovered",
                    state.session_id,
                    self._with_step_progress(
                        state,
                        {
                        "tool_name": state.selected_tool,
                        "service": state.selected_tool_service,
                        "operation": state.selected_tool_operation,
                        "mutation": state.selected_tool_mutation,
                        "requires_confirmation": state.selected_tool_requires_confirmation,
                        },
                    ),
                ),
                self._event(
                    "tool_selected",
                    state.session_id,
                    self._with_step_progress(
                        state,
                        {"tool_name": state.selected_tool, "arguments": state.selected_tool_arguments},
                    ),
                ),
            ]
        if node_name == "confirmation_gate":
            return [
                self._event(
                    "awaiting_confirmation",
                    state.session_id,
                    self._with_step_progress(
                        state,
                        {
                        "confirmation_id": state.confirmation_id,
                        "tool_name": state.selected_tool,
                        "reason": state.pending_action.reason if state.pending_action is not None else "",
                        },
                    ),
                )
            ]
        if node_name == "execute_tool":
            return [
                self._event(
                    "tool_executing",
                    state.session_id,
                    self._with_step_progress(
                        state,
                        {"tool_name": state.last_tool_name, "arguments": state.last_tool_arguments},
                    ),
                ),
                self._event(
                    "tool_result",
                    state.session_id,
                    self._with_step_progress(
                        state,
                        {"tool_name": state.last_tool_name, "result": state.last_tool_result},
                    ),
                ),
            ]
        if node_name == "advance_plan":
            if state.selected_tool is None:
                return []
            return [
                self._event(
                    "tool_discovered",
                    state.session_id,
                    self._with_step_progress(
                        state,
                        {
                        "tool_name": state.selected_tool,
                        "service": state.selected_tool_service,
                        "operation": state.selected_tool_operation,
                        "mutation": state.selected_tool_mutation,
                        "requires_confirmation": state.selected_tool_requires_confirmation,
                        },
                    ),
                ),
                self._event(
                    "tool_selected",
                    state.session_id,
                    self._with_step_progress(
                        state,
                        {"tool_name": state.selected_tool, "arguments": state.selected_tool_arguments},
                    ),
                ),
            ]
        return []

    def _event(self, event_type: str, session_id: str, data: dict[str, Any]) -> StreamEvent:
        return StreamEvent(type=event_type, session_id=session_id, data=data)

    def _with_step_progress(self, state: AdminAgentState, data: dict[str, Any]) -> dict[str, Any]:
        total_steps = len(state.planned_tool_calls) or (1 if state.selected_tool is not None else 0)
        current_step = min(state.current_tool_index + 1, total_steps) if total_steps else 0
        return {
            **data,
            "current_step": current_step,
            "total_steps": total_steps,
        }

    def _run_summary(self, state: AdminAgentState) -> RunSummary | None:
        if not state.planned_tool_calls and not state.completed_tool_results:
            return None

        planned_steps = [
            RunStep(
                tool_name=str(step.get("tool_name", "")),
                arguments=dict(step.get("arguments", {})),
                service=step.get("service"),
                operation=step.get("operation"),
                mutation=bool(step.get("mutation", False)),
            )
            for step in state.planned_tool_calls
        ]
        completed_steps = [
            RunStep(
                tool_name=str(step.get("tool_name", "")),
                arguments={},
                service=step.get("service"),
                operation=step.get("operation"),
                mutation=bool(step.get("mutation", False)),
                status=(
                    str(step.get("result", {}).get("status"))
                    if isinstance(step.get("result"), dict) and step.get("result", {}).get("status") is not None
                    else None
                ),
                result=dict(step.get("result", {})) if isinstance(step.get("result"), dict) else {},
            )
            for step in state.completed_tool_results
        ]
        total_steps = len(planned_steps) or len(completed_steps)
        current_step = min(state.current_tool_index + 1, total_steps) if total_steps else 0
        return RunSummary(
            total_steps=total_steps,
            completed_steps=len(completed_steps),
            current_step=current_step,
            pending_confirmation=state.pending_action is not None,
            planned_steps=planned_steps,
            completed=completed_steps,
        )


def new_confirmation_id() -> str:
    raise NotImplementedError("Confirmation ids are now created by ConfirmationManager.")
