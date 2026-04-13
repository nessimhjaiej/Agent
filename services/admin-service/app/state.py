from typing import Literal, TypedDict


class AdminActivity(TypedDict, total=False):
    phase: str
    status: str
    title: str
    detail: str
    tool: str | None
    arguments: dict


class AdminState(TypedDict, total=False):
    session_id: str | None
    message: str
    selected_mode: Literal["qa", "plan"]
    access_token: str | None
    status: str
    route: str | None
    intent: str | None
    current_step: str | None
    activity: list[AdminActivity]
    chat_history: list[dict]
    session_context: dict
    tool_cache: dict
    final_answer: str | None
    requires_confirmation: bool
    pending_action: dict | None
    tool_result: dict | None
    tool_call_count: int
    tool_cache_updates: dict
    planned_answer: str | None
    planned_pending_action: dict | None
