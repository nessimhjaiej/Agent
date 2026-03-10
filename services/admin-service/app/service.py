from app.config import Settings
from app.models import AdminActor, AdminChatTurn, AdminRequestContext, PendingAction, PlanStep
from app.orchestrator import AdminOrchestrator
from app.schemas import AdminChatRequest, AdminChatResponse


class AdminService:
    def __init__(
        self,
        settings: Settings | None = None,
        orchestrator: AdminOrchestrator | None = None,
    ) -> None:
        self._settings = settings or Settings.from_env()
        self._orchestrator = orchestrator or AdminOrchestrator(settings=self._settings)

    def chat(self, payload: AdminChatRequest, access_token: str | None = None) -> AdminChatResponse:
        context = AdminRequestContext(
            message=payload.message,
            session_id=payload.session_id,
            confirm=payload.confirm,
            actor=None,
            pending_action=(
                PendingAction(
                    intent=payload.pending_action.intent,
                    tool_name=payload.pending_action.tool,
                    arguments=payload.pending_action.arguments,
                    steps=[
                        PlanStep(tool_name=step.tool, arguments=step.arguments)
                        for step in payload.pending_action.steps
                    ],
                )
                if payload.pending_action
                else None
            ),
            chat_history=[
                AdminChatTurn(role=item.role, content=item.content) for item in payload.chat_history
            ],
        )
        return self._orchestrator.handle(context)
