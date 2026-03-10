from app.clients.auth_client import AuthClient
from app.clients.embedding_client import EmbeddingClient
from app.clients.generation_client import GenerationClient
from app.clients.ingestion_client import IngestionClient
from app.clients.retrieval_client import RetrievalClient
from app.clients.security_client import SecurityClient
from app.config import Settings
from app.models import AdminRequestContext, PlanStep, PlannedAction
from app.planner.confirmation import needs_confirmation
from app.planner.tool_selector import ToolSelector
from app.schemas import AdminChatResponse, AdminCitationResponse, AdminPendingAction, AdminPlanStep
from app.tools.config_tools import (
    GetChunkingConfigTool,
    GetEmbeddingConfigTool,
    GetPipelineStatusTool,
    GetRerankerConfigTool,
    UpdateChunkingConfigTool,
    UpdateEmbeddingModelTool,
    UpdateRerankerConfigTool,
)
from app.tools.evaluation_tools import GetEvaluationReportTool, RunRagEvaluationTool
from app.tools.knowledge_tools import (
    DeleteDocumentTool,
    DeleteDocumentsBatchTool,
    DeleteValidatedDocumentsTool,
    EmbedDocumentTool,
    EmbedValidatedDocumentsTool,
    ReindexCorpusTool,
)
from app.tools.registry import ToolRegistry
from app.tools.restart_tools import RestartServicesTool


class AdminOrchestrator:
    def __init__(
        self,
        settings: Settings,
        selector: ToolSelector | None = None,
        registry: ToolRegistry | None = None,
        security_client: SecurityClient | None = None,
        generation_client: GenerationClient | None = None,
    ) -> None:
        self._settings = settings
        self._generation_client = generation_client or GenerationClient(settings)
        self._selector = selector or ToolSelector(settings)
        self._security_client = security_client or SecurityClient(settings)
        ingestion_client = IngestionClient(settings)
        self._registry = registry or ToolRegistry(
            tools=[
                GetPipelineStatusTool(
                    auth_client=AuthClient(settings),
                    embedding_client=EmbeddingClient(settings),
                    retrieval_client=RetrievalClient(settings),
                    generation_client=self._generation_client,
                    ingestion_client=ingestion_client,
                ),
                GetEmbeddingConfigTool(settings=settings),
                UpdateEmbeddingModelTool(),
                GetChunkingConfigTool(),
                UpdateChunkingConfigTool(),
                GetRerankerConfigTool(),
                UpdateRerankerConfigTool(),
                DeleteDocumentTool(ingestion_client=ingestion_client),
                DeleteDocumentsBatchTool(ingestion_client=ingestion_client),
                DeleteValidatedDocumentsTool(ingestion_client=ingestion_client),
                EmbedDocumentTool(ingestion_client=ingestion_client),
                EmbedValidatedDocumentsTool(ingestion_client=ingestion_client),
                ReindexCorpusTool(ingestion_client=ingestion_client),
                RunRagEvaluationTool(),
                GetEvaluationReportTool(),
                RestartServicesTool(),
            ]
        )

    def handle(self, context: AdminRequestContext) -> AdminChatResponse:
        planned = self._resolve_action(context)
        self._publish_event("admin.agent.intent_resolved", context, planned, {})

        if planned.mode == "qa":
            return self._handle_qa(context)

        steps = self._resolve_steps(planned)
        if not steps:
            return AdminChatResponse(
                status="error",
                mode="tool_call",
                session_id=context.session_id,
                message=context.message,
                answer="I could not determine which admin action to run.",
                intent=planned.intent,
                tool=planned.tool_name,
                arguments=planned.arguments,
                requires_confirmation=False,
                executed=False,
                pending_action=None,
                citations=[],
                result={},
            )

        if self._requires_confirmation(planned, steps) and not context.confirm:
            return AdminChatResponse(
                status="needs_confirmation",
                mode="tool_call",
                session_id=context.session_id,
                message=context.message,
                answer=planned.answer
                or f"Are you sure you want to run '{planned.tool_name or planned.intent}'?",
                intent=planned.intent,
                tool=planned.tool_name,
                arguments=planned.arguments,
                requires_confirmation=True,
                executed=False,
                pending_action=AdminPendingAction(
                    intent=planned.intent,
                    tool=planned.tool_name or planned.intent,
                    arguments=planned.arguments,
                    steps=[
                        AdminPlanStep(tool=step.tool_name, arguments=step.arguments) for step in steps
                    ],
                ),
                citations=[],
                result={"steps": [{"tool": step.tool_name, "arguments": step.arguments} for step in steps]},
            )

        execution_payload = self._execute_steps(steps)
        event_type = (
            "admin.agent.tool_execution_succeeded"
            if execution_payload.get("status") == "ok"
            else "admin.agent.tool_execution_failed"
        )
        self._publish_event(event_type, context, planned, execution_payload)
        return AdminChatResponse(
            status=str(execution_payload.get("status", "ok")),
            mode="tool_call",
            session_id=context.session_id,
            message=context.message,
            answer=str(execution_payload.get("answer", "")),
            intent=planned.intent,
            tool=planned.tool_name,
            arguments=planned.arguments,
            requires_confirmation=False,
            executed=bool(execution_payload.get("executed", True)),
            pending_action=None,
            citations=[],
            result=execution_payload,
        )

    def _resolve_action(self, context: AdminRequestContext) -> PlannedAction:
        if context.confirm and context.pending_action is not None:
            return PlannedAction(
                mode="tool_call",
                intent=context.pending_action.intent,
                tool_name=context.pending_action.tool_name,
                arguments=context.pending_action.arguments,
                answer="Confirmed. Executing the requested admin plan.",
                requires_confirmation=False,
                steps=context.pending_action.steps,
            )
        return self._selector.select(context)

    def _resolve_steps(self, planned: PlannedAction) -> list[PlanStep]:
        if planned.steps:
            return planned.steps
        if planned.tool_name is None:
            return []
        return [PlanStep(tool_name=planned.tool_name, arguments=planned.arguments)]

    def _requires_confirmation(self, planned: PlannedAction, steps: list[PlanStep]) -> bool:
        if planned.requires_confirmation:
            return True
        return any(
            needs_confirmation(
                step.tool_name,
                require_confirmation_for_mutations=self._settings.require_confirmation_for_mutations,
            )
            for step in steps
        )

    def _execute_steps(self, steps: list[PlanStep]) -> dict:
        executed_steps: list[dict] = []
        final_answer = ""
        overall_status = "ok"
        executed_any = False

        for step in steps:
            tool = self._registry.get(step.tool_name)
            execution = tool.execute(step.arguments)
            executed_any = executed_any or execution.executed
            final_answer = execution.answer or final_answer
            step_payload = {
                "tool": step.tool_name,
                "arguments": step.arguments,
                "status": execution.status,
                "answer": execution.answer,
                "result": execution.result,
                "executed": execution.executed,
            }
            executed_steps.append(step_payload)
            if execution.status != "ok":
                overall_status = execution.status
                break

        if len(executed_steps) > 1 and overall_status == "ok":
            final_answer = "Completed admin plan successfully."

        return {
            "status": overall_status,
            "answer": final_answer,
            "executed": executed_any,
            "steps": executed_steps,
            "step_count": len(executed_steps),
        }

    def _handle_qa(self, context: AdminRequestContext) -> AdminChatResponse:
        payload = self._generation_client.ask(
            query=context.message,
            chat_history=[
                {"role": turn.role, "content": turn.content}
                for turn in context.chat_history[-12:]
                if turn.content.strip()
            ],
        )
        citations = payload.get("citations", [])
        response_citations = []
        if isinstance(citations, list):
            for item in citations:
                if isinstance(item, dict):
                    response_citations.append(AdminCitationResponse(**item))

        result = {
            "retrieval_count": payload.get("retrieval_count", 0),
            "returned_count": payload.get("returned_count", 0),
            "retrieval_mode": payload.get("retrieval_mode", ""),
            "fusion_type": payload.get("fusion_type", ""),
            "rerank_type": payload.get("rerank_type", ""),
        }
        upstream_status = str(payload.get("status", "ok"))
        return AdminChatResponse(
            status="ok" if upstream_status in {"ok", "degraded"} else "error",
            mode="qa",
            session_id=context.session_id,
            message=context.message,
            answer=str(payload.get("answer", "")),
            intent="qa",
            tool=None,
            arguments={},
            requires_confirmation=False,
            executed=True,
            pending_action=None,
            citations=response_citations,
            result=result,
        )

    def _publish_event(
        self,
        event_type: str,
        context: AdminRequestContext,
        planned: PlannedAction,
        result: dict,
    ) -> None:
        self._security_client.publish_event(
            {
                "event_type": event_type,
                "session_id": context.session_id,
                "message": context.message,
                "actor": (
                    {
                        "id": context.actor.id,
                        "email": context.actor.email,
                        "role": context.actor.role,
                    }
                    if context.actor
                    else None
                ),
                "mode": planned.mode,
                "intent": planned.intent,
                "tool": planned.tool_name,
                "arguments": planned.arguments,
                "steps": [
                    {"tool": step.tool_name, "arguments": step.arguments}
                    for step in self._resolve_steps(planned)
                ],
                "result": result,
            }
        )
