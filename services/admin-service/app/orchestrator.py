import json
import queue
import threading
from collections.abc import Callable, Iterator
from dataclasses import asdict

from app.agent import (
    AgentGoal,
    AgentObservation,
    AgentRunState,
    AgentRunStateStore,
    LLMToolCatalogPolicy,
    RecursiveAgentController,
)
from app.clients.auth_client import AuthClient
from app.clients.embedding_client import EmbeddingClient
from app.clients.generation_client import GenerationClient
from app.clients.ingestion_client import IngestionClient
from app.clients.openai_planner_client import OpenAIPlannerClient
from app.clients.retrieval_client import RetrievalClient
from app.clients.security_client import SecurityClient
from app.clients.supabase_documents_client import SupabaseDocumentsClient
from app.config import Settings
from app.fast_path_service import FastPathPlanService
from app.legacy_plan_service import LegacyPlanService
from app.models import AdminRequestContext, PlanStep, PlannedAction
from app.operation_history import AdminOperationHistoryStore
from app.plan_router import SemanticPlanRouter
from app.planner.tool_selector import ToolSelector
from app.response_factory import AdminResponseFactory
from app.schemas import (
    AdminActivityItem,
    AdminChatResponse,
    AdminCitationResponse,
)
from app.tools.config_tools import (
    GetChunkingStrategyCatalogTool,
    GetChunkingConfigTool,
    GetEmbeddingCapabilityCatalogTool,
    GetEmbeddingConfigTool,
    GetPipelineStatusTool,
    GetEvaluationCapabilityCatalogTool,
    GetRerankerStrategyCatalogTool,
    GetRerankerConfigTool,
    UpdateChunkingConfigTool,
    UpdateEmbeddingModelTool,
    UpdateRerankerConfigTool,
)
from app.tools.evaluation_tools import (
    EvaluationReportSummarizer,
    GetEvaluationReportTool,
    RunRagEvaluationTool,
)
from app.tools.knowledge_tools import DeleteDocumentTool, DeleteDocumentsBatchTool, DeleteValidatedDocumentsTool, EmbedDocumentTool, EmbedValidatedDocumentsTool, ReindexCorpusTool
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
        explainer_client: OpenAIPlannerClient | None = None,
        retrieval_client: RetrievalClient | None = None,
        history_store: AdminOperationHistoryStore | None = None,
        supabase_documents_client: SupabaseDocumentsClient | None = None,
        agent_state_store: AgentRunStateStore | None = None,
        recursive_agent_controller: RecursiveAgentController | None = None,
    ) -> None:
        self._fast_read_only_bundles = {
            "system_overview": {
                "description": "Current system status and major active retrieval/indexing controls.",
                "tools": [
                    "get_pipeline_status",
                    "get_embedding_config",
                    "get_chunking_config",
                    "get_reranker_config",
                    "get_evaluation_capability_catalog",
                ],
            },
            "chunking_review": {
                "description": "Current chunking setup and available chunking strategies.",
                "tools": ["get_chunking_config", "get_chunking_strategy_catalog"],
            },
            "reranking_review": {
                "description": "Current reranker setup and available reranking strategies.",
                "tools": ["get_reranker_config", "get_reranker_strategy_catalog"],
            },
            "embedding_review": {
                "description": "Current embedding setup and embedding capabilities.",
                "tools": ["get_embedding_config", "get_embedding_capability_catalog"],
            },
            "evaluation_review": {
                "description": "Latest evaluation information and evaluation capabilities.",
                "tools": ["get_evaluation_report", "get_evaluation_capability_catalog"],
            },
        }
        self._settings = settings
        self._generation_client = generation_client or GenerationClient(settings)
        self._security_client = security_client or SecurityClient(settings)
        self._retrieval_client = retrieval_client or RetrievalClient(settings)
        self._history_store = history_store or AdminOperationHistoryStore()
        self._agent_state_store = agent_state_store or AgentRunStateStore()
        self._supabase_documents_client = supabase_documents_client or SupabaseDocumentsClient(settings)
        self._explainer_client = explainer_client or (
            OpenAIPlannerClient(
                api_key=settings.openai_key,
                model=settings.planner_model,
                temperature=0.1,
                timeout_seconds=settings.http_timeout_seconds,
                max_retries=settings.planner_http_max_retries,
                retry_base_seconds=settings.planner_retry_base_seconds,
            )
            if settings.openai_key
            else None
        )
        ingestion_client = IngestionClient(settings)
        embedding_client = EmbeddingClient(settings)
        summarizer = (
            EvaluationReportSummarizer(
                api_key=settings.openai_key,
                model=settings.planner_model,
                timeout_seconds=settings.http_timeout_seconds,
            )
            if settings.openai_key
            else None
        )
        self._registry = registry or ToolRegistry(
            tools=[
                GetPipelineStatusTool(
                    auth_client=AuthClient(settings),
                    embedding_client=embedding_client,
                    retrieval_client=RetrievalClient(settings),
                    generation_client=self._generation_client,
                    ingestion_client=ingestion_client,
                ),
                GetEmbeddingConfigTool(settings=settings),
                GetEmbeddingCapabilityCatalogTool(settings=settings),
                UpdateEmbeddingModelTool(),
                GetChunkingConfigTool(),
                GetChunkingStrategyCatalogTool(),
                UpdateChunkingConfigTool(),
                GetRerankerConfigTool(),
                GetRerankerStrategyCatalogTool(),
                UpdateRerankerConfigTool(),
                GetEvaluationCapabilityCatalogTool(settings=settings),
                DeleteDocumentTool(
                    ingestion_client=ingestion_client,
                    embedding_client=embedding_client,
                    supabase_documents_client=self._supabase_documents_client,
                ),
                DeleteDocumentsBatchTool(
                    ingestion_client=ingestion_client,
                    embedding_client=embedding_client,
                    supabase_documents_client=self._supabase_documents_client,
                ),
                DeleteValidatedDocumentsTool(
                    embedding_client=embedding_client,
                    supabase_documents_client=self._supabase_documents_client,
                ),
                EmbedDocumentTool(
                    embedding_client=embedding_client,
                    supabase_documents_client=self._supabase_documents_client,
                ),
                EmbedValidatedDocumentsTool(
                    embedding_client=embedding_client,
                    supabase_documents_client=self._supabase_documents_client,
                ),
                ReindexCorpusTool(
                    embedding_client=embedding_client,
                    supabase_documents_client=self._supabase_documents_client,
                ),
                RunRagEvaluationTool(summarizer=summarizer),
                GetEvaluationReportTool(summarizer=summarizer),
                RestartServicesTool(),
            ]
        )
        self._selector = selector or ToolSelector(settings, registry=self._registry)
        self._response_factory = AdminResponseFactory()
        self._legacy_plan_service = LegacyPlanService(
            settings=settings,
            selector=self._selector,
            registry=self._registry,
            security_client=self._security_client,
            retrieval_client=self._retrieval_client,
            history_store=self._history_store,
            supabase_documents_client=self._supabase_documents_client,
            explainer_client=self._explainer_client,
            response_factory=self._response_factory,
            emit=self._emit,
        )
        self._semantic_plan_router = SemanticPlanRouter(
            client=self._explainer_client,
            bundle_catalog=self._fast_read_only_bundles,
        )
        self._fast_path_plan_service = FastPathPlanService(
            registry=self._registry,
            explainer_client=self._explainer_client,
            response_factory=self._response_factory,
            bundle_catalog=self._fast_read_only_bundles,
            emit=self._emit,
        )
        recursive_tool_names = {
            "get_pipeline_status",
            "get_embedding_config",
            "get_embedding_capability_catalog",
            "update_embedding_model",
            "get_chunking_config",
            "get_chunking_strategy_catalog",
            "update_chunking_config",
            "get_reranker_config",
            "get_reranker_strategy_catalog",
            "update_reranker_config",
            "get_evaluation_capability_catalog",
            "get_evaluation_report",
            "run_rag_evaluation",
            "restart_services",
        }
        recursive_tool_catalog = [
            tool for tool in self._registry.planning_tools() if tool.name in recursive_tool_names
        ]
        recursive_policy = (
            LLMToolCatalogPolicy(
                client=self._explainer_client,
                tool_catalog=recursive_tool_catalog,
            )
            if self._explainer_client is not None
            else None
        )
        self._recursive_agent_controller = recursive_agent_controller or (
            RecursiveAgentController(
                policy=recursive_policy,
                tool_executor=self._execute_agent_tool,
            )
            if recursive_policy is not None
            else None
        )

    def handle(
        self,
        context: AdminRequestContext,
        progress_callback: Callable[[dict], None] | None = None,
    ) -> AdminChatResponse:
        if self._should_handle_recursive_confirmation(context):
            return self._handle_recursive_confirmation(context, progress_callback=progress_callback)
        if context.confirm and context.pending_action is not None:
            return self._legacy_plan_service.handle_confirmed(context, progress_callback=progress_callback)

        if context.selected_mode == "qa":
            return self._handle_selected_qa_mode(context, progress_callback=progress_callback)
        return self._handle_selected_plan_mode(context, progress_callback=progress_callback)

    def _handle_selected_qa_mode(
        self,
        context: AdminRequestContext,
        progress_callback: Callable[[dict], None] | None = None,
    ) -> AdminChatResponse:
        return self._handle_qa(context, progress_callback=progress_callback)

    def _handle_selected_plan_mode(
        self,
        context: AdminRequestContext,
        progress_callback: Callable[[dict], None] | None = None,
    ) -> AdminChatResponse:
        if self._should_continue_existing_recursive_run(context):
            return self._handle_recursive_plan(context, progress_callback=progress_callback)
        route = self._semantic_plan_router.route(context)
        if route.route == "fast_read_only" and route.bundle_id:
            return self._fast_path_plan_service.handle(
                context,
                bundle_id=route.bundle_id,
                subject=route.subject,
                reason=route.reason,
                progress_callback=progress_callback,
            )
        if route.route == "legacy_planner":
            return self._legacy_plan_service.handle(context, progress_callback=progress_callback)
        if route.route == "qa":
            return self._handle_qa(context, progress_callback=progress_callback)
        if self._should_handle_recursive_plan_request(context):
            return self._handle_recursive_plan(context, progress_callback=progress_callback)
        return self._legacy_plan_service.handle(context, progress_callback=progress_callback)

    def _handle_recursive_plan(
        self,
        context: AdminRequestContext,
        progress_callback: Callable[[dict], None] | None = None,
    ) -> AdminChatResponse:
        self._emit(
            progress_callback,
            {
                "type": "activity",
                "activity": [
                    {
                        "phase": "planning",
                        "status": "in_progress",
                        "title": "Running recursive plan agent",
                        "detail": "Inspecting system state, grounding tool choices, and preparing the next action.",
                    }
                ],
            },
        )
        state = self._load_or_initialize_agent_state(context)
        if self._recursive_agent_controller is None:
            return self._handle_legacy_plan_mode(context, progress_callback=progress_callback)
        updated_state = self._recursive_agent_controller.run(state, progress_callback=progress_callback)
        self._persist_agent_state(context, updated_state)
        if updated_state.stop_reason == "fallback_legacy_planner":
            if updated_state.observations:
                return self._handle_recursive_soft_fallback(context, updated_state)
            self._agent_state_store.delete(context.session_id or "")
            return self._handle_legacy_plan_mode(context, progress_callback=progress_callback)

        if updated_state.status == "paused_for_confirmation" and updated_state.pending_confirmation is not None:
            pending_steps = self._steps_from_agent_state(updated_state)
            activity = [
                AdminActivityItem(
                    phase="planning",
                    status="completed",
                    title="Prepared recursive plan",
                    detail="The agent grounded the next action and paused before changing system state.",
                ),
                AdminActivityItem(
                    phase="confirmation",
                    status="pending",
                    title="Awaiting confirmation",
                    detail=updated_state.pending_confirmation.reason,
                    tool=updated_state.pending_confirmation.tool_name,
                    arguments=updated_state.pending_confirmation.arguments,
                ),
            ]
            return self._build_response(
                status="needs_confirmation",
                mode="tool_call",
                selected_mode=context.selected_mode,
                session_id=context.session_id,
                message=context.message,
                answer=updated_state.final_answer,
                intent="recursive_plan_agent",
                tool=updated_state.pending_confirmation.tool_name,
                arguments=updated_state.pending_confirmation.arguments,
                requires_confirmation=True,
                executed=False,
                pending_action=self._response_factory.build_pending_action(
                    intent="recursive_plan_agent",
                    tool=updated_state.pending_confirmation.tool_name,
                    arguments=updated_state.pending_confirmation.arguments,
                    steps=pending_steps,
                ),
                citations=[],
                thinking_summary=(
                    "I used the recursive plan agent to inspect the current setup and paused before applying "
                    "the proposed change."
                ),
                activity=activity,
                result={
                    "proposed_steps": updated_state.proposed_steps,
                    "should_run_evaluation": any(
                        isinstance(step, dict) and step.get("tool") == "run_rag_evaluation"
                        for step in updated_state.proposed_steps
                    ),
                    "stop_reason": updated_state.stop_reason,
                },
                agent_run=asdict(updated_state),
            )

        response_mode = "advisory" if updated_state.status == "completed" else "tool_call"
        return self._build_response(
            status="ok" if updated_state.status in {"completed", "running"} else "error",
            mode=response_mode,
            selected_mode=context.selected_mode,
            session_id=context.session_id,
            message=context.message,
            answer=updated_state.final_answer or "The recursive plan agent did not produce an answer.",
            intent="recursive_plan_agent",
            tool=None,
            arguments={},
            requires_confirmation=False,
            executed=False,
            pending_action=None,
            citations=[],
            thinking_summary=(
                "I used the recursive plan agent to inspect grounded system state and prepare the next action."
            ),
            activity=[
                AdminActivityItem(
                    phase="planning",
                    status="completed" if updated_state.status == "completed" else "failed",
                    title="Recursive plan agent finished",
                    detail=updated_state.stop_reason or "Completed the current reranker reasoning pass.",
                )
            ],
            result={
                "proposed_steps": updated_state.proposed_steps,
                "facts": updated_state.facts,
                "should_run_evaluation": any(
                    isinstance(step, dict) and step.get("tool") == "run_rag_evaluation"
                    for step in updated_state.proposed_steps
                ),
                "stop_reason": updated_state.stop_reason,
            },
            agent_run=asdict(updated_state),
        )

    def _handle_recursive_soft_fallback(
        self,
        context: AdminRequestContext,
        state: AgentRunState,
    ) -> AdminChatResponse:
        answer = self._synthesize_recursive_fallback_answer(context.message, state)
        state.status = "completed"
        state.stop_reason = "soft_fallback_responded"
        state.final_answer = answer
        self._persist_agent_state(context, state)
        return self._build_response(
            status="ok",
            mode="advisory",
            selected_mode=context.selected_mode,
            session_id=context.session_id,
            message=context.message,
            answer=answer,
            intent="recursive_plan_agent",
            tool=None,
            arguments={},
            requires_confirmation=False,
            executed=False,
            pending_action=None,
            citations=[],
            thinking_summary=(
                "The recursive plan agent had already gathered grounded observations, so I answered from those "
                "instead of falling back to the legacy planner."
            ),
            activity=[
                AdminActivityItem(
                    phase="planning",
                    status="completed",
                    title="Answered from grounded observations",
                    detail="The recursive run produced enough evidence to answer without using the legacy fallback path.",
                )
            ],
            result={
                "proposed_steps": state.proposed_steps,
                "facts": state.facts,
                "stop_reason": state.stop_reason,
            },
            agent_run=asdict(state),
        )

    def _synthesize_recursive_fallback_answer(self, user_message: str, state: AgentRunState) -> str:
        observation_lines = []
        for item in state.observations[-6:]:
            observation_lines.append(f"- {item.source}: {item.content}")
        proposed_steps = json.dumps(state.proposed_steps, ensure_ascii=True)
        if self._explainer_client is not None:
            try:
                return self._explainer_client.complete_text(
                    system_prompt=(
                        "You are an admin agent explaining grounded system observations. "
                        "Answer the user's request directly using the gathered observations. "
                        "Do not tell the user to switch modes. "
                        "Be practical, concise, and keep the same language as the user when reasonable. "
                        "If proposed steps exist, mention them as recommendations rather than automatic actions."
                    ),
                    user_prompt=(
                        f"User request:\n{user_message.strip()}\n\n"
                        f"Grounded observations:\n" + "\n".join(observation_lines) + "\n\n"
                        f"Proposed steps:\n{proposed_steps}"
                    ),
                )
            except Exception:
                pass
        summary = "\n".join(observation_lines) if observation_lines else "No grounded observations were available."
        if state.proposed_steps:
            return (
                f"Here is the grounded result from the current admin run:\n{summary}\n\n"
                f"Recommended next steps: {proposed_steps}"
            )
        return f"Here is the grounded result from the current admin run:\n{summary}"

    def _handle_recursive_confirmation(
        self,
        context: AdminRequestContext,
        progress_callback: Callable[[dict], None] | None = None,
    ) -> AdminChatResponse:
        self._emit(
            progress_callback,
            {
                "type": "activity",
                "activity": [
                    {
                        "phase": "planning",
                        "status": "completed",
                        "title": "Confirmed recursive plan",
                        "detail": "Executing the previously prepared admin change.",
                    }
                ],
            },
        )
        state = self._agent_state_store.load(context.session_id or "")
        if state is None or state.pending_confirmation is None:
            return self._build_response(
                status="error",
                mode="tool_call",
                selected_mode=context.selected_mode,
                session_id=context.session_id,
                message=context.message,
                answer="I could not find a pending recursive agent action to confirm.",
                intent="recursive_plan_agent",
                tool=None,
                arguments={},
                requires_confirmation=False,
                executed=False,
                pending_action=None,
                citations=[],
                thinking_summary="The confirmation request did not match any stored recursive agent run.",
                activity=[
                    AdminActivityItem(
                        phase="execution",
                        status="failed",
                        title="Missing recursive agent state",
                        detail="No stored recursive plan was available for confirmation.",
                    )
                ],
                result={},
                agent_run=asdict(state) if state is not None else None,
            )

        steps = self._steps_from_pending_action(context, state)
        baseline_report = (
            self._legacy_plan_service.load_latest_evaluation_summary()
            if self._should_run_post_change_evaluation(state, steps)
            else None
        )
        execution_payload = self._legacy_plan_service.execute_steps(steps, progress_callback=progress_callback)
        state.pending_confirmation = None
        state.status = "completed" if execution_payload.get("status") == "ok" else "failed"
        state.stop_reason = "confirmed_and_executed" if state.status == "completed" else "execution_failed"
        state.final_answer = str(execution_payload.get("answer", ""))
        evaluation_comparison = self._legacy_plan_service.build_evaluation_comparison(execution_payload, baseline_report)
        if evaluation_comparison is not None:
            execution_payload["evaluation_comparison"] = evaluation_comparison
            state.facts["evaluation_comparison"] = evaluation_comparison
            state.final_answer = (
                f"{state.final_answer}\n\nEvaluation follow-up: {evaluation_comparison['summary_text']}"
            ).strip()
        state.observations.append(
            AgentObservation(
                source="execution",
                content=state.final_answer,
                data=execution_payload,
            )
        )
        self._persist_agent_state(context, state)
        self._legacy_plan_service.record_reversible_steps(context, execution_payload)
        return self._build_response(
            status=str(execution_payload.get("status", "ok")),
            mode="tool_call",
            selected_mode=context.selected_mode,
            session_id=context.session_id,
            message=context.message,
            answer=state.final_answer,
            intent="recursive_plan_agent",
            tool=steps[0].tool_name,
            arguments=steps[0].arguments,
            requires_confirmation=False,
            executed=bool(execution_payload.get("executed", True)),
            pending_action=None,
            citations=[],
            thinking_summary="I resumed the recursive agent run and executed the confirmed admin change.",
            activity=self._response_factory.build_execution_activity(steps, execution_payload),
            result=execution_payload,
            agent_run=asdict(state),
        )

    def stream(self, context: AdminRequestContext) -> Iterator[str]:
        event_queue: queue.Queue[dict] = queue.Queue()

        def _collector(event: dict) -> None:
            event_queue.put(event)

        def _runner() -> None:
            try:
                response = self.handle(context, progress_callback=_collector)
                event_queue.put(
                    {
                        "type": "final",
                        "response": response.model_dump(),
                    }
                )
            except Exception as exc:
                event_queue.put({"type": "error", "detail": str(exc)})
            finally:
                event_queue.put({"type": "__stream_done__", "sentinel": True})

        worker = threading.Thread(target=_runner, name="admin-orchestrator-stream", daemon=True)
        worker.start()

        while True:
            event = event_queue.get()
            if event.get("type") == "__stream_done__":
                break
            yield self._serialize_stream_event(event)

    def _resolve_action(self, context: AdminRequestContext) -> PlannedAction:
        return self._legacy_plan_service.resolve_action(context)

    def _should_handle_recursive_plan_request(self, context: AdminRequestContext) -> bool:
        stored_state = self._agent_state_store.load(context.session_id or "")
        if self._explainer_client is not None:
            lowered = context.message.lower()
            if any(token in lowered for token in ("revert", "rollback", "undo")):
                return False
            if stored_state is not None:
                return True
            return True
        lowered = context.message.lower()
        if any(token in lowered for token in ("revert", "rollback", "undo")):
            return False
        if stored_state is not None:
            return True
        return any(token in lowered for token in ("rerank", "reranker", "ranker", "cross_encoder", "llm_batch"))

    def _should_continue_existing_recursive_run(self, context: AdminRequestContext) -> bool:
        stored_state = self._agent_state_store.load(context.session_id or "")
        if stored_state is None:
            return False
        if stored_state.pending_confirmation is not None:
            return True
        return self._is_follow_up_agent_message(context.message)

    def _should_handle_recursive_confirmation(self, context: AdminRequestContext) -> bool:
        if not context.confirm or context.pending_action is None:
            return False
        state = self._agent_state_store.load(context.session_id or "")
        return bool(state and state.pending_confirmation is not None)

    def _load_or_initialize_agent_state(self, context: AdminRequestContext) -> AgentRunState:
        loaded_state = self._agent_state_store.load(context.session_id or "")
        if loaded_state is not None:
            if loaded_state.status in {"completed", "failed", "blocked"} and not self._is_follow_up_agent_message(context.message):
                return AgentRunState(
                    goal=AgentGoal(
                        message=context.message,
                        subject="",
                        desired_outcome="decide the next best admin planning action",
                        success_criteria=["ground the recommendation or action in supported admin tools"],
                    )
                )
            if loaded_state.goal is None:
                loaded_state.goal = AgentGoal(message=context.message, subject="")
            else:
                loaded_state.goal = AgentGoal(
                    message=context.message,
                    subject=loaded_state.goal.subject,
                    desired_outcome=loaded_state.goal.desired_outcome,
                    constraints=loaded_state.goal.constraints,
                    success_criteria=loaded_state.goal.success_criteria,
                )
            if loaded_state.status in {"completed", "failed", "blocked"}:
                loaded_state.status = "running"
                loaded_state.stop_reason = ""
                loaded_state.final_answer = ""
            return loaded_state
        return AgentRunState(
            goal=AgentGoal(
                message=context.message,
                subject="",
                desired_outcome="decide the next best admin planning action",
                success_criteria=["ground the recommendation or action in supported admin tools"],
            )
        )

    def _is_follow_up_agent_message(self, message: str) -> bool:
        lowered = message.strip().lower()
        if not lowered:
            return False
        follow_up_starts = (
            "apply",
            "use ",
            "go ahead",
            "continue",
            "why",
            "how",
            "explain",
            "clarify",
            "compare",
            "what about",
            "and ",
            "ok",
            "okay",
            "yes",
            "confirm",
            "do it",
        )
        return lowered.startswith(follow_up_starts)

    def _persist_agent_state(self, context: AdminRequestContext, state: AgentRunState) -> None:
        session_id = (context.session_id or "").strip()
        if not session_id:
            return
        self._agent_state_store.save(session_id, state)

    def _steps_from_agent_state(self, state: AgentRunState) -> list[PlanStep]:
        if state.proposed_steps:
            return [
                PlanStep(
                    tool_name=str(step.get("tool", "")).strip(),
                    arguments=step.get("arguments", {}) if isinstance(step.get("arguments"), dict) else {},
                )
                for step in state.proposed_steps
                if isinstance(step, dict) and str(step.get("tool", "")).strip()
            ]
        if state.pending_confirmation is None:
            return []
        return [
            PlanStep(
                tool_name=state.pending_confirmation.tool_name,
                arguments=state.pending_confirmation.arguments,
            )
        ]

    def _steps_from_pending_action(self, context: AdminRequestContext, state: AgentRunState) -> list[PlanStep]:
        if context.pending_action is not None and context.pending_action.steps:
            return context.pending_action.steps
        return self._steps_from_agent_state(state)

    def _should_run_post_change_evaluation(self, state: AgentRunState, steps: list[PlanStep]) -> bool:
        return any(step.tool_name == "run_rag_evaluation" for step in steps)

    def _load_latest_evaluation_summary(self) -> dict | None:
        return self._legacy_plan_service.load_latest_evaluation_summary()

    def _build_evaluation_comparison(self, execution_payload: dict, baseline_report: dict | None) -> dict | None:
        return self._legacy_plan_service.build_evaluation_comparison(execution_payload, baseline_report)

    def _execute_agent_tool(self, tool_name: str, arguments: dict) -> AgentObservation:
        tool = self._registry.get(tool_name)
        execution = tool.execute(arguments)
        return AgentObservation(
            source=tool_name,
            content=execution.answer,
            data=execution.result if isinstance(execution.result, dict) else {},
        )

    def _handle_legacy_plan_mode(
        self,
        context: AdminRequestContext,
        progress_callback: Callable[[dict], None] | None = None,
    ) -> AdminChatResponse:
        return self._legacy_plan_service.handle(context, progress_callback=progress_callback)

    def _enrich_document_reference(self, planned: PlannedAction) -> PlannedAction:
        return self._legacy_plan_service.enrich_document_reference(planned)

    def _enrich_supabase_delete_reference(self, planned: PlannedAction) -> PlannedAction:
        document_query = str(planned.arguments.get("document_query", "")).strip()
        try:
            documents = self._supabase_documents_client.list_documents()
        except Exception:
            documents = []

        resolution = resolve_supabase_document_reference(document_query, documents)
        if resolution["status"] == "ambiguous":
            candidates = [str(item) for item in resolution.get("candidates", [])]
            chosen = self._choose_document_candidate(document_query, candidates)
            if chosen:
                resolution = {"status": "resolved", "storage_path": chosen, "candidates": candidates}
        if resolution["status"] == "resolved":
            storage_path = str(resolution["storage_path"])
            arguments = dict(planned.arguments)
            arguments["target_relative_path"] = f"supabase/{storage_path}"
            answer = planned.answer.replace("UNKNOWN_DOCUMENT", f"supabase/{storage_path}")
            return PlannedAction(
                mode=planned.mode,
                intent=planned.intent,
                tool_name=planned.tool_name,
                arguments=arguments,
                answer=answer,
                requires_confirmation=planned.requires_confirmation,
                steps=planned.steps,
            )

        semantic_paths = self._resolve_documents_by_semantic_search(document_query)
        if len(semantic_paths) > 1:
            listed = "\n".join(f"- {path}" for path in semantic_paths)
            return PlannedAction(
                mode="tool_call",
                intent="delete_documents_batch",
                tool_name="delete_documents_batch",
                arguments={
                    "target_relative_paths": semantic_paths,
                    "document_query": document_query,
                    "cleanup_index": True,
                },
                answer=(
                    "I found multiple Supabase indexed files that match your request. "
                    "Deleting them will remove them from Supabase and clear their indexed Weaviate chunks. "
                    "This deletion is irreversible. Confirm to delete these files:\n"
                    f"{listed}"
                ),
                requires_confirmation=True,
                steps=[],
            )
        if len(semantic_paths) == 1:
            storage_path = semantic_paths[0].removeprefix("supabase/").lstrip("/")
            arguments = dict(planned.arguments)
            arguments["target_relative_path"] = f"supabase/{storage_path}"
            answer = planned.answer.replace("UNKNOWN_DOCUMENT", f"supabase/{storage_path}")
            return PlannedAction(
                mode=planned.mode,
                intent=planned.intent,
                tool_name=planned.tool_name,
                arguments=arguments,
                answer=answer,
                requires_confirmation=planned.requires_confirmation,
                steps=planned.steps,
            )
        mirror_resolution = resolve_synced_supabase_reference(
            document_query,
            raw_root=str(planned.arguments.get("raw_root", "shared/raw_data/supabase")),
            local_root=str(planned.arguments.get("local_root", "shared/raw_data")),
        )
        if mirror_resolution["status"] == "resolved":
            relative_path = str(mirror_resolution["target_relative_path"]).lstrip("/")
            arguments = dict(planned.arguments)
            arguments["target_relative_path"] = relative_path if relative_path.startswith("supabase/") else f"supabase/{relative_path}"
            answer = planned.answer.replace("UNKNOWN_DOCUMENT", arguments["target_relative_path"])
            return PlannedAction(
                mode=planned.mode,
                intent=planned.intent,
                tool_name=planned.tool_name,
                arguments=arguments,
                answer=answer,
                requires_confirmation=planned.requires_confirmation,
                steps=planned.steps,
            )
        return planned

    def _choose_document_candidate(self, query: str, candidates: list[str]) -> str | None:
        if not candidates or self._explainer_client is None:
            return None
        try:
            raw_choice = self._explainer_client.complete_text(
                system_prompt=(
                    "You choose the single best matching document path for an admin action. "
                    "Return exactly one candidate path from the provided list, or NONE if nothing clearly matches."
                ),
                user_prompt=(
                    f"User request: {query.strip()}\n\n"
                    f"Candidates:\n- " + "\n- ".join(candidates)
                ),
            ).strip()
        except Exception:
            return None

        normalized_choice = raw_choice.strip().strip("'\"")
        for candidate in candidates:
            if normalized_choice == candidate:
                return candidate
        return None

    def _should_use_semantic_document_resolution(self, query: str) -> bool:
        lowered = query.lower()
        semantic_markers = (
            "files ",
            "documents ",
            "contain",
            "contains",
            "information from",
            "from 19",
            "from 20",
            "year",
            "format",
            "pdf",
            "txt",
            "md",
            "docx",
        )
        return any(marker in lowered for marker in semantic_markers)

    def _resolve_documents_by_semantic_search(self, query: str) -> list[str]:
        if not query.strip():
            return []
        try:
            payload = self._retrieval_client.search(
                query=query,
                mode="hybrid",
                top_k_retrieve=16,
                top_k_return=16,
            )
        except Exception:
            return []

        chunks = payload.get("chunks", [])
        if not isinstance(chunks, list):
            return []

        resolved_paths: list[str] = []
        seen: set[str] = set()
        requested_format = self._extract_requested_format(query)
        requested_year = self._extract_requested_year(query)
        for item in chunks:
            if not isinstance(item, dict):
                continue
            metadata = item.get("metadata", {})
            if not isinstance(metadata, dict):
                metadata = {}
            relative_path = self._relative_path_from_metadata(metadata)
            if not relative_path or relative_path in seen:
                continue
            if not relative_path.startswith("supabase/"):
                continue
            filename = Path(relative_path).name.lower()
            if requested_format and not filename.endswith(f".{requested_format}"):
                continue
            if requested_year:
                path_years = self._extract_years(relative_path)
                if path_years:
                    if requested_year not in path_years:
                        continue
                else:
                    chunk_text = str(item.get("chunk_text", ""))
                    if requested_year not in chunk_text:
                        continue
            seen.add(relative_path)
            resolved_paths.append(relative_path)
        return resolved_paths[:8]

    def _relative_path_from_metadata(self, metadata: dict) -> str | None:
        source_uri = metadata.get("source_uri")
        if not isinstance(source_uri, str) or not source_uri.strip():
            return None
        raw = source_uri.strip().replace("\\", "/")
        marker = "/shared/raw_data/"
        if marker in raw:
            return raw.split(marker, 1)[1].strip("/")
        local_marker = "shared/raw_data/"
        if local_marker in raw:
            return raw.split(local_marker, 1)[1].strip("/")
        return None

    def _extract_requested_format(self, query: str) -> str | None:
        lowered = query.lower()
        for ext in ("pdf", "md", "txt", "docx"):
            if ext in lowered:
                return ext
        return None

    def _extract_requested_year(self, query: str) -> str | None:
        for token in query.split():
            stripped = token.strip(".,!?()[]{}")
            if len(stripped) == 4 and stripped.isdigit() and stripped.startswith(("19", "20")):
                return stripped
        return None

    def _extract_years(self, text: str) -> set[str]:
        return set(match.group(0) for match in re.finditer(r"(?:19|20)\d{2}", text))

    def _resolve_steps(self, planned: PlannedAction) -> list[PlanStep]:
        return self._legacy_plan_service.resolve_steps(planned)

    def _build_revert_plan(self, context: AdminRequestContext, planned: PlannedAction) -> PlannedAction:
        return self._legacy_plan_service.build_revert_plan(context, planned)

    def _requires_confirmation(self, planned: PlannedAction, steps: list[PlanStep]) -> bool:
        return self._legacy_plan_service.requires_confirmation(planned, steps)

    def _execute_steps(
        self,
        steps: list[PlanStep],
        progress_callback: Callable[[dict], None] | None = None,
    ) -> dict:
        return self._legacy_plan_service.execute_steps(steps, progress_callback=progress_callback)

    def _handle_qa(
        self,
        context: AdminRequestContext,
        progress_callback: Callable[[dict], None] | None = None,
    ) -> AdminChatResponse:
        self._emit(
            progress_callback,
            {
                "type": "activity",
                "activity": [
                    {
                        "phase": "qa",
                        "status": "in_progress",
                        "title": "Running retrieval and generation",
                        "detail": "Fetching relevant context and composing an answer.",
                    }
                ],
            },
        )
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
        return self._build_response(
            status="ok" if upstream_status in {"ok", "degraded"} else "error",
            mode="qa",
            selected_mode=context.selected_mode,
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
            thinking_summary="I treated this as an informational admin question and routed it through the RAG answer flow.",
            activity=[
                AdminActivityItem(
                    phase="planning",
                    status="completed",
                    title="Resolved request as admin Q&A",
                    detail="The request looked informational or ambiguous, so the agent used the retrieval and generation flow instead of running an operation.",
                ),
                AdminActivityItem(
                    phase="qa",
                    status="completed",
                    title="Retrieved and generated answer",
                    detail=(
                        f"Retrieved {result['retrieval_count']} candidate chunks and returned "
                        f"{result['returned_count']} cited results using {result['retrieval_mode'] or 'configured'} retrieval."
                    ),
                ),
            ],
            result=result,
        )

    def _handle_follow_up_explanation(
        self,
        context: AdminRequestContext,
        planned: PlannedAction,
        progress_callback: Callable[[dict], None] | None = None,
    ) -> AdminChatResponse:
        self._emit(
            progress_callback,
            {
                "type": "activity",
                "activity": [
                    {
                        "phase": "qa",
                        "status": "in_progress",
                        "title": "Explaining previous agent response",
                        "detail": "Interpreting the most recent assistant message in conversation context.",
                    }
                ],
            },
        )
        assistant_message = str(planned.arguments.get("assistant_message", "")).strip()
        answer = self._explain_last_agent_response(context.message, assistant_message)
        return self._build_response(
            status="ok",
            mode="qa",
            selected_mode=context.selected_mode,
            session_id=context.session_id,
            message=context.message,
            answer=answer,
            intent=planned.intent,
            tool=None,
            arguments=planned.arguments,
            requires_confirmation=False,
            executed=True,
            pending_action=None,
            citations=[],
            thinking_summary="I interpreted this as a follow-up about my previous admin response, not as a new knowledge-base query.",
            activity=[
                AdminActivityItem(
                    phase="planning",
                    status="completed",
                    title="Resolved contextual follow-up",
                    detail="Used the last assistant message as the thing to explain.",
                ),
                AdminActivityItem(
                    phase="qa",
                    status="completed",
                    title="Explained previous agent response",
                    detail="Returned a plain-language explanation of the last admin answer.",
                ),
            ],
            result={"referenced_message": assistant_message},
        )

    def _explain_last_agent_response(self, user_message: str, assistant_message: str) -> str:
        if self._explainer_client is not None:
            try:
                return self._explainer_client.complete_text(
                    system_prompt=(
                        "You explain prior admin-agent responses in plain language. "
                        "Do not answer from RAG documents. "
                        "Explain the operational meaning of the assistant's previous message, "
                        "what actually happened, and what did not happen yet. "
                        "Be concise and practical."
                    ),
                    user_prompt=(
                        f"Admin follow-up: {user_message.strip()}\n\n"
                        f"Previous assistant response to explain:\n{assistant_message}"
                    ),
                )
            except Exception:
                pass
        return (
            "You are asking about my previous admin response. "
            f"In plain language, it means: {assistant_message}"
        )

    def _emit(
        self,
        progress_callback: Callable[[dict], None] | None,
        event: dict,
    ) -> None:
        if progress_callback is None:
            return
        progress_callback(event)

    def _serialize_stream_event(self, payload: dict) -> str:
        return json.dumps(payload, ensure_ascii=True) + "\n"

    def _build_planning_summary(
        self,
        planned: PlannedAction,
        steps: list[PlanStep],
        requires_confirmation: bool,
    ) -> str:
        return self._response_factory.build_planning_summary(planned, steps, requires_confirmation)

    def _build_execution_summary(self, planned: PlannedAction, execution_payload: dict) -> str:
        return self._response_factory.build_execution_summary(planned, execution_payload)

    def _build_confirmation_activity(self, steps: list[PlanStep]) -> list[AdminActivityItem]:
        return self._response_factory.build_confirmation_activity(steps)

    def _build_response(self, **kwargs) -> AdminChatResponse:
        return self._response_factory.build_response(**kwargs)

    def _build_mode_switch_response(
        self,
        context: AdminRequestContext,
        response_mode: str,
        answer: str,
        thinking_summary: str,
        activity: list[AdminActivityItem],
        intent: str,
    ) -> AdminChatResponse:
        return self._response_factory.build_mode_switch_response(
            context=context,
            response_mode=response_mode,
            answer=answer,
            thinking_summary=thinking_summary,
            activity=activity,
            intent=intent,
        )

    def _build_execution_activity(
        self,
        planned_steps: list[PlanStep],
        execution_payload: dict,
    ) -> list[AdminActivityItem]:
        return self._response_factory.build_execution_activity(planned_steps, execution_payload)

    def _publish_event(
        self,
        event_type: str,
        context: AdminRequestContext,
        planned: PlannedAction,
        result: dict,
    ) -> None:
        self._legacy_plan_service.publish_event(event_type, context, planned, result)

    def _record_reversible_steps(self, context: AdminRequestContext, execution_payload: dict) -> None:
        self._legacy_plan_service.record_reversible_steps(context, execution_payload)
