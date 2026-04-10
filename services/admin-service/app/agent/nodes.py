from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from app.agent.confirmation import ConfirmationManager
from app.agent.memory import SessionMemoryStore
from app.agent.runtime import AdminAgentRuntime
from app.audit.history import AuditLogger
from app.mcp.client import MCPClient

if TYPE_CHECKING:
    from app.agent.graph import AdminAgentState


def build_initial_state(
    *,
    session_id: str,
    user_id: str,
    user_email: str,
    message: str,
    chat_history: list[dict[str, str]],
    metadata: dict[str, Any],
    request_confirmation: bool,
    request_confirmation_id: str | None,
) -> AdminAgentState:
    from app.agent.graph import AdminAgentState

    return AdminAgentState(
        session_id=session_id,
        user_id=user_id,
        user_email=user_email,
        message=message,
        chat_history=chat_history,
        metadata=metadata,
        request_confirmation=request_confirmation,
        request_confirmation_id=request_confirmation_id,
        planned_tool_calls=[],
        current_tool_index=0,
        completed_tool_results=[],
    )


async def load_session_node(
    state: AdminAgentState,
    memory: SessionMemoryStore,
) -> dict[str, Any]:
    existing = await memory.load_state(state.session_id)
    incoming_history = state.chat_history
    if existing is None:
        return {
            "chat_history": memory.merge_history([], incoming_history),
            "updated_at_utc": datetime.now(UTC),
        }

    return {
        "user_id": state.user_id,
        "user_email": state.user_email,
        "message": state.message,
        "chat_history": memory.merge_history(existing.chat_history, incoming_history),
        "metadata": state.metadata,
        "confirmation_requested": False,
        "confirmation_id": None,
        "pending_action": None,
        "planned_tool_calls": existing.planned_tool_calls,
        "current_tool_index": existing.current_tool_index,
        "completed_tool_results": existing.completed_tool_results,
        "selected_tool": None,
        "selected_tool_arguments": {},
        "selected_tool_service": None,
        "selected_tool_operation": None,
        "selected_tool_requires_confirmation": False,
        "selected_tool_mutation": False,
        "last_tool_name": None,
        "last_tool_arguments": {},
        "last_tool_result": None,
        "mode": "qa",
        "answer": "",
        "status": "ok",
        "audit_event_id": None,
        "updated_at_utc": datetime.now(UTC),
    }


async def resume_confirmation_node(
    state: AdminAgentState,
    confirmation: ConfirmationManager,
) -> dict[str, Any]:
    resumed = await confirmation.resume(
        session_id=state.session_id,
        user_id=state.user_id,
        confirmation_id=state.request_confirmation_id,
    )
    if resumed is None:
        return {
            "status": "error",
            "mode": "mutation",
            "answer": "There is no valid pending action for this session, the confirmation id does not match, or it expired.",
            "pending_action": None,
            "confirmation_id": None,
        }

    return {
        "status": "ok",
        "mode": "mutation",
        "pending_action": None,
        "confirmation_id": None,
        "selected_tool": resumed.tool_name,
        "selected_tool_arguments": dict(resumed.arguments),
        "last_tool_name": resumed.tool_name,
        "last_tool_arguments": dict(resumed.arguments),
        "answer": "",
    }


async def select_tool_node(
    state: AdminAgentState,
    runtime: AdminAgentRuntime,
    mcp_client: MCPClient,
) -> dict[str, Any]:
    decision = await runtime.decide(message=state.message, chat_history=state.chat_history)
    if not decision.tool_calls:
        return {
            "status": "ok",
            "mode": decision.intent,
            "answer": decision.answer,
        }

    validated_steps: list[dict[str, Any]] = []
    mode = decision.intent
    for planned_tool in decision.tool_calls:
        descriptor = await mcp_client.get_tool(planned_tool.tool_name)
        validation = await mcp_client.validate_tool_request(planned_tool.tool_name, dict(planned_tool.arguments))
        if not validation.valid:
            return {
                "status": "error",
                "mode": "mutation" if descriptor.mutation else "diagnostic",
                "answer": validation.error or f"The request for tool '{planned_tool.tool_name}' is invalid.",
            }
        if descriptor.mutation:
            mode = "mutation"
        validated_steps.append(
            {
                "tool_name": planned_tool.tool_name,
                "arguments": dict(validation.normalized_arguments),
                "service": descriptor.service,
                "operation": descriptor.operation,
                "requires_confirmation": descriptor.requires_confirmation,
                "mutation": descriptor.mutation,
            }
        )
    first_step = validated_steps[0]
    return {
        "mode": mode,
        "planned_tool_calls": validated_steps,
        "current_tool_index": 0,
        "completed_tool_results": [],
        "selected_tool": first_step["tool_name"],
        "selected_tool_arguments": dict(first_step["arguments"]),
        "selected_tool_service": first_step["service"],
        "selected_tool_operation": first_step["operation"],
        "selected_tool_requires_confirmation": first_step["requires_confirmation"],
        "selected_tool_mutation": first_step["mutation"],
    }


async def confirmation_gate_node(
    state: AdminAgentState,
    confirmation: ConfirmationManager,
    ttl_seconds: int,
) -> dict[str, Any]:
    if not state.selected_tool or not state.selected_tool_requires_confirmation:
        return {}

    reason = confirmation_reason(state.selected_tool)
    pending = await confirmation.create(
        session_id=state.session_id,
        user_id=state.user_id,
        tool_name=state.selected_tool,
        arguments=state.selected_tool_arguments,
        reason=reason,
        ttl_seconds=ttl_seconds,
    )
    await confirmation.pause(state.session_id, pending)
    return {
        "status": "needs_confirmation",
        "mode": "mutation",
        "confirmation_requested": True,
        "confirmation_id": pending.confirmation_id,
        "pending_action": pending,
        "answer": f"This action requires confirmation before execution. Confirm if you want me to run '{state.selected_tool}'.",
    }


async def execute_tool_node(
    state: AdminAgentState,
    runtime: AdminAgentRuntime,
    mcp_client: MCPClient,
    audit: AuditLogger,
) -> dict[str, Any]:
    if not state.selected_tool:
        return {}

    descriptor = await mcp_client.get_tool(state.selected_tool)
    result = await mcp_client.execute_tool(state.selected_tool, state.selected_tool_arguments)
    completed_tool_results = [
        *state.completed_tool_results,
        {
            "tool_name": descriptor.name,
            "service": descriptor.service,
            "operation": descriptor.operation,
            "mutation": descriptor.mutation,
            "result": result.result,
        },
    ]

    audit_event_id = None
    if descriptor.mutation:
        audit_event_id = await audit.log_mutation(
            user_id=state.user_id,
            user_email=state.user_email,
            tool_name=descriptor.name,
            service=descriptor.service,
            operation=descriptor.operation,
            arguments=state.selected_tool_arguments,
            session_id=state.session_id,
            status=str(result.result.get("status", "unknown")),
            result=result.result,
            metadata=state.metadata,
        )

    return {
        "last_tool_name": descriptor.name,
        "last_tool_arguments": dict(state.selected_tool_arguments),
        "last_tool_result": result.result,
        "completed_tool_results": completed_tool_results,
        "status": "ok",
        "mode": "mutation" if descriptor.mutation else "diagnostic",
        "audit_event_id": audit_event_id,
        "answer": await runtime.synthesize_plan_response(
            message=state.message,
            completed_tools=completed_tool_results,
        )
        if state.current_tool_index + 1 >= len(state.planned_tool_calls)
        else "",
    }


async def advance_plan_node(
    state: AdminAgentState,
    runtime: AdminAgentRuntime,
) -> dict[str, Any]:
    next_index = state.current_tool_index + 1
    if next_index >= len(state.planned_tool_calls):
        return {
            "selected_tool": None,
            "selected_tool_arguments": {},
            "selected_tool_service": None,
            "selected_tool_operation": None,
            "selected_tool_requires_confirmation": False,
            "selected_tool_mutation": False,
            "answer": await runtime.synthesize_plan_response(
                message=state.message,
                completed_tools=state.completed_tool_results,
            ),
        }

    next_step = state.planned_tool_calls[next_index]
    return {
        "current_tool_index": next_index,
        "selected_tool": next_step["tool_name"],
        "selected_tool_arguments": dict(next_step["arguments"]),
        "selected_tool_service": next_step["service"],
        "selected_tool_operation": next_step["operation"],
        "selected_tool_requires_confirmation": next_step["requires_confirmation"],
        "selected_tool_mutation": next_step["mutation"],
    }


async def persist_state_node(
    state: AdminAgentState,
    memory: SessionMemoryStore,
) -> dict[str, Any]:
    updated_history = memory.append_exchange(
        state.chat_history,
        user_message=state.message,
        assistant_message=state.answer,
    )
    updated_at = datetime.now(UTC)
    await memory.save_state(
        state.session_id,
        state.model_copy(update={"chat_history": updated_history, "updated_at_utc": updated_at}),
    )
    return {
        "chat_history": updated_history,
        "updated_at_utc": updated_at,
    }


def confirmation_reason(tool_name: str) -> str:
    reasons = {
        "delete_document": "Document deletion is irreversible.",
        "restart_service": "Restarting a live service can temporarily affect availability.",
        "reindex_embeddings": "Reindexing may be expensive and can affect operational workloads.",
    }
    return reasons.get(tool_name, f"The tool '{tool_name}' is marked as requiring confirmation.")
