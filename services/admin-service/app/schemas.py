from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str
    version: str


class AdminChatTurnInput(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = Field(..., min_length=1)


class AdminPlanStep(BaseModel):
    tool: str = Field(..., min_length=1)
    arguments: dict = Field(default_factory=dict)


class AdminWorkflowTask(BaseModel):
    task_id: str = Field(..., min_length=1)
    kind: str = Field(default="read", pattern="^(read|mutation|advice)$")
    clause: str = ""
    status: str = Field(default="pending", pattern="^(pending|completed|rejected|skipped)$")
    steps: list[AdminPlanStep] = Field(default_factory=list)
    outcome: dict = Field(default_factory=dict)


class AdminPendingAction(BaseModel):
    intent: str = Field(..., min_length=1)
    tool: str = Field(..., min_length=1)
    arguments: dict = Field(default_factory=dict)
    steps: list[AdminPlanStep] = Field(default_factory=list)
    task_index: int | None = None
    workflow_tasks: list[AdminWorkflowTask] = Field(default_factory=list)
    # Human-readable description of exactly what will happen (names the target
    # documents). Shown on the frontend confirmation card so it is never empty.
    summary: str = ""


class AdminActivityItem(BaseModel):
    phase: str = Field(..., min_length=1)
    status: str = Field(..., pattern="^(pending|in_progress|completed|failed|skipped)$")
    title: str = Field(..., min_length=1)
    detail: str = ""
    tool: str | None = None
    arguments: dict = Field(default_factory=dict)


class AdminAgentRunState(BaseModel):
    run_id: str | None = None
    status: str = Field(default="running", pattern="^(running|paused_for_confirmation|completed|blocked|failed)$")
    iteration_count: int = Field(default=0, ge=0)
    tool_call_count: int = Field(default=0, ge=0)
    max_iterations: int = Field(default=1, ge=1)
    max_tool_calls: int = Field(default=1, ge=1)
    facts: dict = Field(default_factory=dict)
    observations: list[dict] = Field(default_factory=list)
    decision_history: list[dict] = Field(default_factory=list)
    proposed_steps: list[dict] = Field(default_factory=list)
    pending_confirmation: dict | None = None
    final_answer: str = ""
    stop_reason: str = ""


class IntentClassification(BaseModel):
    category: str = Field(..., pattern="^(advisory|inspect|mutate)$")
    intent: str = Field(..., min_length=1)
    reasoning: str = Field(..., min_length=1)


class AdminChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    selected_mode: str = Field(default="qa", pattern="^(qa|plan)$")
    session_id: str | None = None
    confirm: bool = False
    reject: bool = False
    pending_action: AdminPendingAction | None = None
    chat_history: list[AdminChatTurnInput] = Field(default_factory=list)
    access_token: str | None = None
    actor_user_id: str | None = None
    actor_email: str | None = None
    actor_role: str | None = None


class AdminCitationResponse(BaseModel):
    chunk_id: str
    document_id: str
    document_name: str
    chunk_text: str


class AdminChatResponse(BaseModel):
    status: str = Field(default="ok", pattern="^(ok|needs_confirmation|error)$")
    mode: str = Field(default="qa", pattern="^(qa|advisory|inspect|mutate|tool_call)$")
    selected_mode: str = Field(default="qa", pattern="^(qa|plan)$")
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
