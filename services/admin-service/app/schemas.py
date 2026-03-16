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


class AdminAgentGoal(BaseModel):
    message: str = Field(..., min_length=1)
    subject: str = ""
    desired_outcome: str = ""
    constraints: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)


class AdminAgentObservation(BaseModel):
    source: str = Field(..., min_length=1)
    content: str = ""
    data: dict = Field(default_factory=dict)


class AdminAgentPendingConfirmation(BaseModel):
    tool_name: str = Field(..., min_length=1)
    arguments: dict = Field(default_factory=dict)
    reason: str = ""


class AdminAgentDecision(BaseModel):
    action_type: str = Field(..., pattern="^(respond|call_tool|request_confirmation|stop)$")
    message: str = ""
    tool_name: str | None = None
    arguments: dict = Field(default_factory=dict)
    reason: str = ""
    expected_observation: str = ""


class AdminAgentRunState(BaseModel):
    run_id: str | None = None
    goal: AdminAgentGoal | None = None
    status: str = Field(
        default="running",
        pattern="^(running|paused_for_confirmation|completed|blocked|failed)$",
    )
    iteration_count: int = Field(default=0, ge=0)
    tool_call_count: int = Field(default=0, ge=0)
    max_iterations: int = Field(default=25, ge=1)
    max_tool_calls: int = Field(default=10, ge=1)
    facts: dict = Field(default_factory=dict)
    observations: list[AdminAgentObservation] = Field(default_factory=list)
    decision_history: list[AdminAgentDecision] = Field(default_factory=list)
    proposed_steps: list[dict] = Field(default_factory=list)
    pending_confirmation: AdminAgentPendingConfirmation | None = None
    final_answer: str = ""
    stop_reason: str = ""


class AdminChatResponse(BaseModel):
    status: str = Field(..., pattern="^(ok|needs_confirmation|error)$")
    mode: str = Field(..., pattern="^(qa|advisory|tool_call)$")
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
    agent_run: AdminAgentRunState | None = None
