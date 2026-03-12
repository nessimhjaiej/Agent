from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(default="ok")
    service: str
    version: str


class AdminChatTurnInput(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1)


class AdminPlanStep(BaseModel):
    tool: str = Field(..., min_length=1)
    arguments: dict = Field(default_factory=dict)


class AdminPendingAction(BaseModel):
    intent: str = Field(..., min_length=1)
    tool: str = Field(..., min_length=1)
    arguments: dict = Field(default_factory=dict)
    steps: list[AdminPlanStep] = Field(default_factory=list)


class AdminChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    selected_mode: str = Field(default="qa", pattern="^(qa|plan)$")
    session_id: str | None = None
    confirm: bool = False
    pending_action: AdminPendingAction | None = None
    chat_history: list[AdminChatTurnInput] = Field(default_factory=list)


class AdminCitationResponse(BaseModel):
    chunk_id: str
    document_id: str
    document_name: str
    chunk_text: str


class AdminActivityItem(BaseModel):
    phase: str = Field(..., min_length=1)
    status: str = Field(..., pattern="^(pending|in_progress|completed|failed|skipped)$")
    title: str = Field(..., min_length=1)
    detail: str = ""
    tool: str | None = None
    arguments: dict = Field(default_factory=dict)


class AdminChatResponse(BaseModel):
    status: str = Field(..., pattern="^(ok|needs_confirmation|error)$")
    mode: str = Field(..., pattern="^(qa|tool_call)$")
    selected_mode: str = Field(..., pattern="^(qa|plan)$")
    session_id: str | None = None
    message: str
    answer: str
    intent: str
    tool: str | None = None
    arguments: dict = Field(default_factory=dict)
    requires_confirmation: bool = False
    executed: bool = False
    pending_action: AdminPendingAction | None = None
    citations: list[AdminCitationResponse] = Field(default_factory=list)
    thinking_summary: str = ""
    activity: list[AdminActivityItem] = Field(default_factory=list)
    result: dict = Field(default_factory=dict)
