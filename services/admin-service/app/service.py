from app.config import Settings
from app.clients.auth_client import AuthClient
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
        self._auth_client = AuthClient(self._settings)
        self._orchestrator = orchestrator or AdminOrchestrator(settings=self._settings)

    def chat(self, payload: AdminChatRequest, access_token: str) -> AdminChatResponse:
        current_user = self._auth_client.require_admin(access_token)
        context = AdminRequestContext(
            message=payload.message,
            session_id=payload.session_id,
            confirm=payload.confirm,
            actor=AdminActor(
                id=current_user["id"],
                email=current_user["email"],
                role=current_user["role"],
            ),
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
