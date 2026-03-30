from pathlib import Path
import sys
import json

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.config import Settings  # noqa: E402
from app.agent.memory import AgentRunStateStore  # noqa: E402
from app.models import AdminChatTurn, AdminRequestContext, PlanStep, PlannedAction, PendingAction  # noqa: E402
from app.operation_history import AdminOperationHistoryStore  # noqa: E402
from app.orchestrator import AdminOrchestrator  # noqa: E402
from app.tools.base import ToolMetadata  # noqa: E402


class _FakeTool:
    def __init__(self, result: dict) -> None:
        self._result = result

    def execute(self, arguments: dict):  # noqa: ANN001
        from app.models import ToolExecutionResult

        return ToolExecutionResult(
            status="ok",
            answer=self._result["answer"],
            result=self._result["result"],
        )


class _FailingTool:
    metadata = ToolMetadata(name="get_pipeline_status", description="Pipeline status", output_description="status")

    def execute(self, arguments: dict):  # noqa: ANN001
        raise RuntimeError("upstream unavailable")


class _FakeUpdateRerankerConfigTool:
    name = "update_reranker_config"
    metadata = ToolMetadata(
        name=name,
        description="Update reranker config",
        output_description="updated config",
        requires_confirmation=True,
    )

    def __init__(self, result: dict) -> None:
        self._result = result

    def execute(self, arguments: dict):  # noqa: ANN001
        from app.models import ToolExecutionResult

        return ToolExecutionResult(
            status="ok",
            answer=self._result["answer"],
            result=self._result["result"],
        )


class _FakeUpdateChunkingConfigTool:
    name = "update_chunking_config"
    metadata = ToolMetadata(
        name=name,
        description="Update chunking config",
        output_description="updated config",
        requires_confirmation=True,
    )

    def __init__(self, result: dict) -> None:
        self._result = result

    def execute(self, arguments: dict):  # noqa: ANN001
        from app.models import ToolExecutionResult

        return ToolExecutionResult(
            status="ok",
            answer=self._result["answer"],
            result=self._result["result"],
        )


class _FakeAgentCatalogTool:
    name = "get_reranker_strategy_catalog"
    metadata = ToolMetadata(name=name, description="Reranker catalog", output_description="catalog")

    def execute(self, arguments: dict):  # noqa: ANN001
        from app.models import ToolExecutionResult

        return ToolExecutionResult(
            status="ok",
            answer="Supported reranker strategies loaded.",
            result={
                "subject": "reranker",
                "current_config": {"default_ranker": "none", "rerank_top_n": 20},
                "options": [
                    {"name": "none", "description": "No reranking."},
                    {"name": "cross_encoder", "description": "Cross-encoder reranking."},
                    {"name": "llm_batch", "description": "LLM batch reranking."},
                ],
            },
        )


class _FakeEvaluationReportTool:
    name = "get_evaluation_report"
    metadata = ToolMetadata(name=name, description="Evaluation report", output_description="report")

    def execute(self, arguments: dict):  # noqa: ANN001
        from app.models import ToolExecutionResult

        return ToolExecutionResult(
            status="ok",
            answer="Loaded the latest evaluation report.",
            result={
                "report_path": "docs/evaluation_reports/baseline.json",
                "generated_at_utc": "2026-03-16T10:00:00+00:00",
                "summary": {"faithfulness": 0.7, "factual_correctness(mode=f1)": 0.6},
            },
        )


class _FakeRunEvaluationTool:
    name = "run_rag_evaluation"
    metadata = ToolMetadata(name=name, description="Run evaluation", output_description="evaluation", requires_confirmation=False)

    def execute(self, arguments: dict):  # noqa: ANN001
        from app.models import ToolExecutionResult

        return ToolExecutionResult(
            status="ok",
            answer="Evaluation rerun completed.",
            result={
                "report_path": "docs/evaluation_reports/latest.json",
                "dataset_path": arguments.get("dataset_path", "evals/sample_eval_dataset.json"),
                "sample_count": 4,
                "summary": {"faithfulness": 0.82, "factual_correctness(mode=f1)": 0.68},
            },
        )


class _FakeRegistry:
    def __init__(self, tools: dict) -> None:
        self._tools = tools

    def get(self, tool_name: str):  # noqa: ANN001
        return self._tools[tool_name]

    def planning_tools(self):  # noqa: ANN001
        result = []
        for name, tool in self._tools.items():
            result.append(getattr(tool, "metadata", ToolMetadata(name=name, description=name)))
        return result


class _FakeSelector:
    def __init__(self, planned_action) -> None:  # noqa: ANN001
        self._planned_action = planned_action

    def select(self, context):  # noqa: ANN001
        return self._planned_action


class _FakeSecurityClient:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def publish_event(self, event: dict) -> None:
        self.events.append(event)


class _FakeGenerationClient:
    def ask(self, query: str, chat_history: list[dict]) -> dict:
        assert query == "Explain the current setup."
        assert chat_history == [{"role": "user", "content": "Previous admin question"}]
        return {
            "status": "ok",
            "answer": "Here is the explanation.",
            "citations": [
                {
                    "chunk_id": "doc-1:0",
                    "document_id": "doc-1",
                    "document_name": "doc-1.pdf",
                    "chunk_text": "Evidence text",
                }
            ],
            "retrieval_count": 2,
            "returned_count": 1,
            "retrieval_mode": "hybrid",
            "fusion_type": "rrf",
            "rerank_type": "cross_encoder",
        }


class _FakeExplainerClient:
    def complete_text(self, system_prompt: str, user_prompt: str) -> str:
        assert "Previous assistant response to explain" in user_prompt
        return "It means the setting was written, but the rest of the operational follow-up did not run yet."


class _QueuedPlannerClient:
    def __init__(self, payloads: list[str], route_payload: str | None = None, text_response: str = "ok") -> None:
        self._payloads = payloads
        self._index = 0
        self._route_payload = route_payload or '{"route":"recursive_agent","subject":"","bundle_id":"","reason":"default test route"}'
        self._text_response = text_response

    def complete_json(self, system_prompt: str, user_prompt: str) -> str:
        if "route plan-mode admin requests semantically" in system_prompt:
            return self._route_payload
        payload = self._payloads[min(self._index, len(self._payloads) - 1)]
        self._index += 1
        return payload

    def complete_text(self, system_prompt: str, user_prompt: str) -> str:
        return self._text_response


class _FakeChunkingCatalogTool:
    name = "get_chunking_strategy_catalog"
    metadata = ToolMetadata(name=name, description="Chunking catalog", output_description="catalog")

    def execute(self, arguments: dict):  # noqa: ANN001
        from app.models import ToolExecutionResult

        return ToolExecutionResult(
            status="ok",
            answer="Supported chunking strategies loaded.",
            result={
                "subject": "chunking",
                "current_config": {"chunk_strategy": "late", "chunk_size": 800, "chunk_overlap": 120},
                "options": [
                    {"name": "overlap", "description": "Sliding overlap chunks."},
                    {"name": "semantic", "description": "Semantic chunks."},
                    {"name": "late", "description": "Late chunking."},
                    {"name": "sentence", "description": "Sentence chunks."},
                ],
            },
        )


class _FakeDeleteDocumentTool:
    name = "delete_document"
    metadata = ToolMetadata(name=name, description="Delete document", output_description="delete", requires_confirmation=True)

    def execute(self, arguments: dict):  # noqa: ANN001
        from app.models import ToolExecutionResult

        return ToolExecutionResult(status="ok", answer="Deleted.", result={})


class _FakeRetrievalClient:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def search(
        self,
        query: str,
        mode: str = "hybrid",
        top_k_retrieve: int = 12,
        top_k_return: int = 12,
        filters: dict | None = None,
    ) -> dict:
        assert query
        return self._payload


class _FakeSupabaseDocumentsClient:
    def __init__(self, documents: list[dict] | None = None) -> None:
        self._documents = documents or []

    def list_documents(self) -> list[dict]:
        return list(self._documents)


def test_orchestrator_requires_confirmation_for_delete_document() -> None:
    security_client = _FakeSecurityClient()
    orchestrator = AdminOrchestrator(
        settings=Settings(planner_enabled=False),
        selector=_FakeSelector(
            PlannedAction(
                mode="tool_call",
                intent="delete_document",
                tool_name="delete_document",
                arguments={"target_relative_path": "doc.pdf"},
                answer="Are you sure you want to delete doc.pdf?",
                requires_confirmation=True,
            )
        ),
        registry=_FakeRegistry(
            {"delete_document": _FakeTool({"answer": "done", "result": {}})}
        ),
        security_client=security_client,  # type: ignore[arg-type]
        generation_client=_FakeGenerationClient(),  # type: ignore[arg-type]
        supabase_documents_client=_FakeSupabaseDocumentsClient(),  # type: ignore[arg-type]
    )

    response = orchestrator.handle(AdminRequestContext(message="delete document doc.pdf", selected_mode="plan"))

    assert response.status == "needs_confirmation"
    assert response.mode == "tool_call"
    assert response.executed is False
    assert response.pending_action is not None
    assert response.pending_action.tool == "delete_document"
    assert response.thinking_summary
    assert response.activity[0].phase == "planning"


def test_orchestrator_executes_confirmed_pending_action() -> None:
    security_client = _FakeSecurityClient()
    orchestrator = AdminOrchestrator(
        settings=Settings(planner_enabled=False),
        selector=_FakeSelector(
            PlannedAction(mode="qa", intent="qa", tool_name=None)
        ),
        registry=_FakeRegistry(
            {
                "delete_document": _FakeTool(
                    {
                        "answer": "Document deleted.",
                        "result": {"deleted_count": 1},
                    }
                )
            }
        ),
        security_client=security_client,  # type: ignore[arg-type]
        generation_client=_FakeGenerationClient(),  # type: ignore[arg-type]
        supabase_documents_client=_FakeSupabaseDocumentsClient(),  # type: ignore[arg-type]
    )

    response = orchestrator.handle(
        AdminRequestContext(
            message="Confirm deletion",
            selected_mode="plan",
            confirm=True,
            pending_action=PendingAction(
                intent="delete_document",
                tool_name="delete_document",
                arguments={"target_relative_path": "doc.pdf"},
            ),
        )
    )

    assert response.status == "ok"
    assert response.mode == "tool_call"
    assert response.executed is True
    assert response.answer == "Document deleted."
    assert response.activity[1].tool == "delete_document"


def test_orchestrator_routes_qa_requests_to_generation_service() -> None:
    orchestrator = AdminOrchestrator(
        settings=Settings(planner_enabled=False),
        selector=_FakeSelector(
            PlannedAction(mode="qa", intent="qa", tool_name=None, arguments={})
        ),
        registry=_FakeRegistry({}),
        security_client=_FakeSecurityClient(),  # type: ignore[arg-type]
        generation_client=_FakeGenerationClient(),  # type: ignore[arg-type]
        supabase_documents_client=_FakeSupabaseDocumentsClient(),  # type: ignore[arg-type]
    )

    response = orchestrator.handle(
        AdminRequestContext(
            message="Explain the current setup.",
            selected_mode="qa",
            chat_history=[AdminChatTurn(role="user", content="Previous admin question")],
        )
    )

    assert response.status == "ok"
    assert response.mode == "qa"
    assert response.answer == "Here is the explanation."
    assert response.citations[0].document_name == "doc-1.pdf"
    assert response.activity[0].phase == "planning"


def test_orchestrator_executes_multi_step_plan_after_confirmation() -> None:
    orchestrator = AdminOrchestrator(
        settings=Settings(planner_enabled=False),
        selector=_FakeSelector(PlannedAction(mode="qa", intent="qa", tool_name=None)),
        registry=_FakeRegistry(
            {
                "update_chunking_config": _FakeTool(
                    {
                        "answer": "Chunking config updated.",
                        "result": {"chunk_size": 400},
                    }
                ),
                "delete_validated_documents": _FakeTool(
                    {
                        "answer": "Deleted old indexed chunks.",
                        "result": {"deleted_count": 12},
                    }
                ),
                "embed_validated_documents": _FakeTool(
                    {
                        "answer": "Reindexed validated corpus.",
                        "result": {"documents_processed": 3},
                    }
                ),
            }
        ),
        security_client=_FakeSecurityClient(),  # type: ignore[arg-type]
        generation_client=_FakeGenerationClient(),  # type: ignore[arg-type]
        supabase_documents_client=_FakeSupabaseDocumentsClient(),  # type: ignore[arg-type]
    )

    response = orchestrator.handle(
        AdminRequestContext(
            message="Confirm chunking change",
            selected_mode="plan",
            confirm=True,
            pending_action=PendingAction(
                intent="apply_chunking_change",
                tool_name="apply_chunking_change",
                arguments={"chunk_size": 400},
                steps=[
                    PlanStep(tool_name="update_chunking_config", arguments={"chunk_size": 400}),
                    PlanStep(tool_name="delete_validated_documents", arguments={}),
                    PlanStep(tool_name="embed_validated_documents", arguments={}),
                ],
            ),
        )
    )

    assert response.status == "ok"
    assert response.mode == "tool_call"
    assert response.executed is True
    assert response.result["step_count"] == 3
    assert response.result["steps"][0]["tool"] == "update_chunking_config"
    assert response.activity[1].tool == "update_chunking_config"


def test_orchestrator_in_qa_mode_uses_generation_flow_for_follow_up_text() -> None:
    orchestrator = AdminOrchestrator(
        settings=Settings(planner_enabled=False),
        selector=_FakeSelector(
            PlannedAction(
                mode="qa",
                intent="explain_last_agent_response",
                tool_name=None,
                arguments={"assistant_message": "Updated chunking configuration in '.env.local'."},
            )
        ),
        registry=_FakeRegistry({}),
        security_client=_FakeSecurityClient(),  # type: ignore[arg-type]
        generation_client=_FakeGenerationClient(),  # type: ignore[arg-type]
        explainer_client=_FakeExplainerClient(),  # type: ignore[arg-type]
        supabase_documents_client=_FakeSupabaseDocumentsClient(),  # type: ignore[arg-type]
    )

    response = orchestrator.handle(
        AdminRequestContext(
            message="Explain the current setup.",
            selected_mode="qa",
            chat_history=[AdminChatTurn(role="user", content="Previous admin question")],
        )
    )

    assert response.status == "ok"
    assert response.intent == "qa"
    assert response.answer == "Here is the explanation."


def test_orchestrator_uses_semantic_search_to_prepare_batch_delete() -> None:
    orchestrator = AdminOrchestrator(
        settings=Settings(planner_enabled=False),
        selector=_FakeSelector(
            PlannedAction(
                mode="tool_call",
                intent="delete_document",
                tool_name="delete_document",
                arguments={
                    "target_relative_path": "UNKNOWN_DOCUMENT",
                    "document_query": "delete files that contain information from 2023 and are pdf",
                },
                answer="Deleting document 'UNKNOWN_DOCUMENT' will remove its indexed chunks. Confirm to proceed.",
                requires_confirmation=True,
            )
        ),
        registry=_FakeRegistry({}),
        security_client=_FakeSecurityClient(),  # type: ignore[arg-type]
        generation_client=_FakeGenerationClient(),  # type: ignore[arg-type]
        retrieval_client=_FakeRetrievalClient(
            {
                "chunks": [
                    {
                        "chunk_id": "a:0",
                        "document_id": "a",
                        "chunk_text": "This 2023 cybersecurity brief covers resilience.",
                        "metadata": {
                            "source_uri": "/shared/raw_data/supabase/validated/user/2023-icc-annex-icc-cybersecurity-issue-brief-2.pdf"
                        },
                    },
                    {
                        "chunk_id": "b:0",
                        "document_id": "b",
                        "chunk_text": "The 2023 paper discusses non-cyber topics.",
                        "metadata": {
                            "source_uri": "/shared/raw_data/supabase/validated/user/2023_ICC-Paper-on-Digitalisation-for-People-Planet-and-Prosperity.pdf"
                        },
                    },
                ]
            }
        ),  # type: ignore[arg-type]
        supabase_documents_client=_FakeSupabaseDocumentsClient(),  # type: ignore[arg-type]
    )

    response = orchestrator.handle(
        AdminRequestContext(message="delete files that contain information from 2023 and are pdf", selected_mode="plan")
    )

    assert response.status == "needs_confirmation"
    assert response.pending_action is not None
    assert response.pending_action.tool == "delete_documents_batch"
    assert len(response.pending_action.arguments["target_relative_paths"]) == 2
    assert "2023-icc-annex-icc-cybersecurity-issue-brief-2.pdf" in response.answer


def test_orchestrator_year_filter_prefers_document_title_over_chunk_mentions() -> None:
    orchestrator = AdminOrchestrator(
        settings=Settings(planner_enabled=False),
        selector=_FakeSelector(
            PlannedAction(
                mode="tool_call",
                intent="delete_document",
                tool_name="delete_document",
                arguments={
                    "target_relative_path": "UNKNOWN_DOCUMENT",
                    "document_query": "delete only the document from 2021",
                },
                answer="Deleting document 'UNKNOWN_DOCUMENT' will remove its indexed chunks. Confirm to proceed.",
                requires_confirmation=True,
            )
        ),
        registry=_FakeRegistry({}),
        security_client=_FakeSecurityClient(),  # type: ignore[arg-type]
        generation_client=_FakeGenerationClient(),  # type: ignore[arg-type]
        retrieval_client=_FakeRetrievalClient(
            {
                "chunks": [
                    {
                        "chunk_id": "a:0",
                        "document_id": "a",
                        "chunk_text": "This 2023 file references 2021 in passing.",
                        "metadata": {
                            "source_uri": "/shared/raw_data/supabase/validated/user/ICC_PolicyPrimer_NonPersonalData_October2023.pdf"
                        },
                    },
                    {
                        "chunk_id": "b:0",
                        "document_id": "b",
                        "chunk_text": "This issue brief is from 2021.",
                        "metadata": {
                            "source_uri": "/shared/raw_data/supabase/validated/user/2021_Cybersecurity_IssueBrief1_Call-for-Govt-Action.pdf"
                        },
                    },
                ]
            }
        ),  # type: ignore[arg-type]
        supabase_documents_client=_FakeSupabaseDocumentsClient(),  # type: ignore[arg-type]
    )

    response = orchestrator.handle(
        AdminRequestContext(message="delete only the document from 2021", selected_mode="plan")
    )

    assert response.status == "needs_confirmation"
    assert response.pending_action is not None
    assert response.pending_action.tool == "delete_document"
    assert response.pending_action.arguments["target_relative_path"] == "supabase/validated/user/2021_Cybersecurity_IssueBrief1_Call-for-Govt-Action.pdf"


def test_orchestrator_builds_revert_plan_from_session_history(tmp_path: Path) -> None:
    history_store = AdminOperationHistoryStore(history_path=tmp_path / "history.json")
    history_store.append(
        {
            "session_id": "admin-1",
            "tool_name": "update_reranker_config",
            "arguments": {"default_ranker": "cross_encoder", "restart_services": ["retrieval-service"]},
            "rollback": {
                "tool": "update_reranker_config",
                "arguments": {"default_ranker": "none", "rerank_top_n": 20},
            },
            "reversible": True,
            "restart_services": ["retrieval-service", "generation-service", "admin-service"],
        }
    )
    orchestrator = AdminOrchestrator(
        settings=Settings(planner_enabled=False),
        selector=_FakeSelector(
            PlannedAction(
                mode="tool_call",
                intent="revert_changes",
                tool_name="revert_changes",
                arguments={"count": 1, "tool_names": ["update_reranker_config"]},
                requires_confirmation=True,
            )
        ),
        registry=_FakeRegistry({}),
        security_client=_FakeSecurityClient(),  # type: ignore[arg-type]
        generation_client=_FakeGenerationClient(),  # type: ignore[arg-type]
        history_store=history_store,
        supabase_documents_client=_FakeSupabaseDocumentsClient(),  # type: ignore[arg-type]
    )

    response = orchestrator.handle(
        AdminRequestContext(
            message="revert the last reranker change",
            selected_mode="plan",
            session_id="admin-1",
        )
    )

    assert response.status == "needs_confirmation"
    assert response.pending_action is not None
    assert response.pending_action.steps[0].tool == "update_reranker_config"
    assert response.pending_action.steps[-1].tool == "restart_services"


def test_orchestrator_in_qa_mode_routes_directly_to_generation_service() -> None:
    orchestrator = AdminOrchestrator(
        settings=Settings(planner_enabled=False),
        selector=_FakeSelector(PlannedAction(mode="tool_call", intent="get_pipeline_status", tool_name="get_pipeline_status")),
        registry=_FakeRegistry({}),
        security_client=_FakeSecurityClient(),  # type: ignore[arg-type]
        generation_client=_FakeGenerationClient(),  # type: ignore[arg-type]
        supabase_documents_client=_FakeSupabaseDocumentsClient(),  # type: ignore[arg-type]
    )

    response = orchestrator.handle(
        AdminRequestContext(message="Explain the current setup.", selected_mode="qa", chat_history=[AdminChatTurn(role="user", content="Previous admin question")])
    )

    assert response.status == "ok"
    assert response.mode == "qa"
    assert response.executed is True
    assert response.answer == "Here is the explanation."


def test_orchestrator_in_plan_mode_instructs_switch_for_informational_request() -> None:
    orchestrator = AdminOrchestrator(
        settings=Settings(planner_enabled=False),
        selector=_FakeSelector(
            PlannedAction(mode="qa", intent="qa", tool_name=None, arguments={})
        ),
        registry=_FakeRegistry({}),
        security_client=_FakeSecurityClient(),  # type: ignore[arg-type]
        generation_client=_FakeGenerationClient(),  # type: ignore[arg-type]
        supabase_documents_client=_FakeSupabaseDocumentsClient(),  # type: ignore[arg-type]
    )

    response = orchestrator.handle(
        AdminRequestContext(message="Explain the current setup.", selected_mode="plan")
    )

    assert response.status == "ok"
    assert response.mode == "qa"
    assert response.executed is False
    assert response.result["suggested_mode"] == "qa"
    assert "Switch to Q&A mode" in response.answer


def test_orchestrator_uses_recursive_reranker_agent_for_plan_recommendation(tmp_path: Path) -> None:
    state_store = AgentRunStateStore(state_path=tmp_path / "agent_run_states.json")
    planner_client = _QueuedPlannerClient(
        payloads=[
            """
            {
              "action_type": "call_tool",
              "message": "Inspect the available reranker strategies first.",
              "tool_name": "get_reranker_strategy_catalog",
              "arguments": {},
              "reason": "Need grounded reranker options before recommending one.",
              "expected_observation": "Current reranker config and available strategies.",
              "goal_subject": "reranking",
              "proposed_steps": []
            }
            """,
            """
            {
              "action_type": "respond",
              "message": "Cross-encoder reranking is the best balanced option here because it improves ranking quality without the heavier cost profile of llm_batch.",
              "tool_name": null,
              "arguments": {},
              "reason": "Grounded recommendation from the reranker catalog.",
              "expected_observation": "",
              "goal_subject": "reranking",
              "proposed_steps": [
                {
                  "tool": "update_reranker_config",
                  "arguments": {
                    "default_ranker": "cross_encoder",
                    "rerank_top_n": 10
                  }
                }
              ]
            }
            """,
        ]
    )
    orchestrator = AdminOrchestrator(
        settings=Settings(planner_enabled=False),
        selector=_FakeSelector(PlannedAction(mode="qa", intent="qa", tool_name=None)),
        registry=_FakeRegistry(
            {
                "get_reranker_strategy_catalog": _FakeAgentCatalogTool(),
                "update_reranker_config": _FakeUpdateRerankerConfigTool(
                    {
                        "answer": "Updated reranker configuration.",
                        "result": {"default_ranker": "cross_encoder", "rerank_top_n": 10},
                    }
                ),
            }
        ),
        security_client=_FakeSecurityClient(),  # type: ignore[arg-type]
        generation_client=_FakeGenerationClient(),  # type: ignore[arg-type]
        explainer_client=planner_client,  # type: ignore[arg-type]
        agent_state_store=state_store,
        supabase_documents_client=_FakeSupabaseDocumentsClient(),  # type: ignore[arg-type]
    )

    response = orchestrator.handle(
        AdminRequestContext(
            message="I want good reranking without wasting too many resources.",
            selected_mode="plan",
            session_id="admin-1",
        )
    )

    assert response.status == "ok"
    assert response.mode == "advisory"
    assert response.intent == "recursive_plan_agent"
    assert "Cross-encoder" in response.answer
    assert response.agent_run is not None
    assert response.agent_run.goal is not None
    assert response.agent_run.goal.subject == "reranking"
    assert response.result["proposed_steps"][0]["tool"] == "update_reranker_config"


def test_orchestrator_resumes_recursive_reranker_run_after_confirmation(tmp_path: Path) -> None:
    state_store = AgentRunStateStore(state_path=tmp_path / "agent_run_states.json")
    planner_client = _QueuedPlannerClient(
        payloads=[
            """
            {
              "action_type": "call_tool",
              "message": "Inspect the reranker strategies first.",
              "tool_name": "get_reranker_strategy_catalog",
              "arguments": {},
              "reason": "Need the grounded options before choosing a mutation.",
              "expected_observation": "Current config and supported reranker strategies.",
              "goal_subject": "reranking",
              "proposed_steps": []
            }
            """,
            """
            {
              "action_type": "request_confirmation",
              "message": "LLM batch reranking is the strongest quality-first option. Confirm to apply it.",
              "tool_name": "update_reranker_config",
              "arguments": {
                "default_ranker": "llm_batch",
                "rerank_top_n": 10
              },
              "reason": "This applies the quality-first reranker choice.",
              "expected_observation": "Updated reranker config.",
              "goal_subject": "reranking",
              "proposed_steps": [
                {
                  "tool": "update_reranker_config",
                  "arguments": {
                    "default_ranker": "llm_batch",
                    "rerank_top_n": 10
                  }
                }
              ]
            }
            """,
        ]
    )
    registry = _FakeRegistry(
        {
            "get_reranker_strategy_catalog": _FakeAgentCatalogTool(),
            "update_reranker_config": _FakeUpdateRerankerConfigTool(
                {
                    "answer": "Updated reranker configuration.",
                    "result": {"default_ranker": "llm_batch", "rerank_top_n": 10},
                }
            ),
        }
    )
    orchestrator = AdminOrchestrator(
        settings=Settings(planner_enabled=False),
        selector=_FakeSelector(PlannedAction(mode="qa", intent="qa", tool_name=None)),
        registry=registry,
        security_client=_FakeSecurityClient(),  # type: ignore[arg-type]
        generation_client=_FakeGenerationClient(),  # type: ignore[arg-type]
        explainer_client=planner_client,  # type: ignore[arg-type]
        agent_state_store=state_store,
        supabase_documents_client=_FakeSupabaseDocumentsClient(),  # type: ignore[arg-type]
    )

    first_response = orchestrator.handle(
        AdminRequestContext(
            message="Apply the best quality reranker even if it costs more.",
            selected_mode="plan",
            session_id="admin-1",
        )
    )

    assert first_response.status == "needs_confirmation"
    assert first_response.pending_action is not None
    assert first_response.pending_action.tool == "update_reranker_config"

    confirmed_response = orchestrator.handle(
        AdminRequestContext(
            message="Confirm the reranker change.",
            selected_mode="plan",
            session_id="admin-1",
            confirm=True,
            pending_action=PendingAction(
                intent=first_response.pending_action.intent,
                tool_name=first_response.pending_action.tool,
                arguments=first_response.pending_action.arguments,
                steps=[
                    PlanStep(tool_name=step.tool, arguments=step.arguments)
                    for step in first_response.pending_action.steps
                ],
            ),
        )
    )

    assert confirmed_response.status == "ok"
    assert confirmed_response.mode == "tool_call"
    assert confirmed_response.executed is True
    assert confirmed_response.answer == "Updated reranker configuration."
    assert confirmed_response.agent_run is not None
    assert confirmed_response.agent_run.stop_reason == "confirmed_and_executed"


def test_orchestrator_routes_generic_apply_follow_up_back_into_recursive_reranker_run(tmp_path: Path) -> None:
    state_store = AgentRunStateStore(state_path=tmp_path / "agent_run_states.json")
    planner_client = _QueuedPlannerClient(
        payloads=[
            """
            {
              "action_type": "call_tool",
              "message": "Inspect the reranker strategies first.",
              "tool_name": "get_reranker_strategy_catalog",
              "arguments": {},
              "reason": "Need grounded reranker options before recommending one.",
              "expected_observation": "Current reranker config and available strategies.",
              "goal_subject": "reranking",
              "proposed_steps": []
            }
            """,
            """
            {
              "action_type": "respond",
              "message": "Cross-encoder reranking is the best balanced choice. I can apply it if you want.",
              "tool_name": null,
              "arguments": {},
              "reason": "Grounded recommendation from the reranker catalog.",
              "expected_observation": "",
              "goal_subject": "reranking",
              "proposed_steps": [
                {
                  "tool": "update_reranker_config",
                  "arguments": {
                    "default_ranker": "cross_encoder",
                    "rerank_top_n": 10
                  }
                }
              ]
            }
            """,
            """
            {
              "action_type": "request_confirmation",
              "message": "Confirm and I will apply the stored cross-encoder recommendation.",
              "tool_name": "update_reranker_config",
              "arguments": {
                "default_ranker": "cross_encoder",
                "rerank_top_n": 10
              },
              "reason": "This applies the existing grounded recommendation.",
              "expected_observation": "Updated reranker config.",
              "goal_subject": "reranking",
              "proposed_steps": [
                {
                  "tool": "update_reranker_config",
                  "arguments": {
                    "default_ranker": "cross_encoder",
                    "rerank_top_n": 10
                  }
                }
              ]
            }
            """,
        ]
    )
    registry = _FakeRegistry(
        {
            "get_reranker_strategy_catalog": _FakeAgentCatalogTool(),
            "update_reranker_config": _FakeUpdateRerankerConfigTool(
                {
                    "answer": "Updated reranker configuration.",
                    "result": {"default_ranker": "cross_encoder", "rerank_top_n": 10},
                }
            ),
        }
    )
    orchestrator = AdminOrchestrator(
        settings=Settings(planner_enabled=False),
        selector=_FakeSelector(PlannedAction(mode="qa", intent="qa", tool_name=None)),
        registry=registry,
        security_client=_FakeSecurityClient(),  # type: ignore[arg-type]
        generation_client=_FakeGenerationClient(),  # type: ignore[arg-type]
        explainer_client=planner_client,  # type: ignore[arg-type]
        agent_state_store=state_store,
        supabase_documents_client=_FakeSupabaseDocumentsClient(),  # type: ignore[arg-type]
    )

    first_response = orchestrator.handle(
        AdminRequestContext(
            message="I want good reranking without wasting too many resources.",
            selected_mode="plan",
            session_id="admin-1",
        )
    )

    assert first_response.status == "ok"
    assert first_response.intent == "recursive_plan_agent"

    follow_up_response = orchestrator.handle(
        AdminRequestContext(
            message="Apply your recommendation",
            selected_mode="plan",
            session_id="admin-1",
        )
    )

    assert follow_up_response.status == "needs_confirmation"
    assert follow_up_response.intent == "recursive_plan_agent"
    assert follow_up_response.pending_action is not None
    assert follow_up_response.pending_action.tool == "update_reranker_config"


def test_orchestrator_runs_evaluation_after_confirmed_reranker_change_when_requested(tmp_path: Path) -> None:
    state_store = AgentRunStateStore(state_path=tmp_path / "agent_run_states.json")
    planner_client = _QueuedPlannerClient(
        payloads=[
            """
            {
              "action_type": "call_tool",
              "message": "Inspect the reranker strategies first.",
              "tool_name": "get_reranker_strategy_catalog",
              "arguments": {},
              "reason": "Need grounded reranker options before choosing a change.",
              "expected_observation": "Current reranker config and supported strategies.",
              "goal_subject": "reranking",
              "proposed_steps": []
            }
            """,
            """
            {
              "action_type": "request_confirmation",
              "message": "Cross-encoder reranking is the best balanced improvement here. Confirm to apply it and run evaluation afterward.",
              "tool_name": "update_reranker_config",
              "arguments": {
                "default_ranker": "cross_encoder",
                "rerank_top_n": 10
              },
              "reason": "This applies the reranker change and then evaluates the result.",
              "expected_observation": "Updated reranker config and a fresh evaluation report.",
              "goal_subject": "reranking",
              "proposed_steps": [
                {
                  "tool": "update_reranker_config",
                  "arguments": {
                    "default_ranker": "cross_encoder",
                    "rerank_top_n": 10
                  }
                },
                {
                  "tool": "run_rag_evaluation",
                  "arguments": {
                    "dataset_path": "evals/sample_eval_dataset.json"
                  }
                }
              ]
            }
            """,
        ]
    )
    registry = _FakeRegistry(
        {
            "get_reranker_strategy_catalog": _FakeAgentCatalogTool(),
            "update_reranker_config": _FakeUpdateRerankerConfigTool(
                {
                    "answer": "Updated reranker configuration.",
                    "result": {"default_ranker": "cross_encoder", "rerank_top_n": 10},
                }
            ),
            "get_evaluation_report": _FakeEvaluationReportTool(),
            "run_rag_evaluation": _FakeRunEvaluationTool(),
        }
    )
    orchestrator = AdminOrchestrator(
        settings=Settings(planner_enabled=False),
        selector=_FakeSelector(PlannedAction(mode="qa", intent="qa", tool_name=None)),
        registry=registry,
        security_client=_FakeSecurityClient(),  # type: ignore[arg-type]
        generation_client=_FakeGenerationClient(),  # type: ignore[arg-type]
        explainer_client=planner_client,  # type: ignore[arg-type]
        agent_state_store=state_store,
        supabase_documents_client=_FakeSupabaseDocumentsClient(),  # type: ignore[arg-type]
    )

    first_response = orchestrator.handle(
        AdminRequestContext(
            message="Apply a better reranker and evaluate the result with metrics.",
            selected_mode="plan",
            session_id="admin-1",
        )
    )

    assert first_response.status == "needs_confirmation"
    assert first_response.result["should_run_evaluation"] is True
    assert len(first_response.pending_action.steps) == 2
    assert first_response.pending_action.steps[1].tool == "run_rag_evaluation"

    confirmed_response = orchestrator.handle(
        AdminRequestContext(
            message="Confirm the reranker change and evaluation.",
            selected_mode="plan",
            session_id="admin-1",
            confirm=True,
            pending_action=PendingAction(
                intent=first_response.pending_action.intent,
                tool_name=first_response.pending_action.tool,
                arguments=first_response.pending_action.arguments,
                steps=[
                    PlanStep(tool_name=step.tool, arguments=step.arguments)
                    for step in first_response.pending_action.steps
                ],
            ),
        )
    )

    assert confirmed_response.status == "ok"
    assert confirmed_response.result["step_count"] == 2
    assert confirmed_response.result["steps"][1]["tool"] == "run_rag_evaluation"
    assert "evaluation_comparison" in confirmed_response.result
    assert confirmed_response.result["evaluation_comparison"]["deltas"]["faithfulness"] == 0.12


def test_orchestrator_executes_run_evaluation_without_soft_fallback(tmp_path: Path) -> None:
    state_store = AgentRunStateStore(state_path=tmp_path / "agent_run_states.json")
    planner_client = _QueuedPlannerClient(
        payloads=[
            """
            {
              "action_type": "request_confirmation",
              "message": "Run the evaluation now.",
              "tool_name": "run_rag_evaluation",
              "arguments": {
                "dataset_path": "evals/sample_eval_dataset.json"
              },
              "reason": "Evaluation does not require confirmation and should run directly.",
              "expected_observation": "A completed evaluation report with metrics.",
              "goal_subject": "evaluation",
              "proposed_steps": [
                {
                  "tool": "run_rag_evaluation",
                  "arguments": {
                    "dataset_path": "evals/sample_eval_dataset.json"
                  }
                }
              ]
            }
            """,
            """
            {
              "action_type": "respond",
              "message": "The RAG evaluation completed successfully and produced fresh metrics.",
              "tool_name": null,
              "arguments": {},
              "reason": "The evaluation result is now available.",
              "expected_observation": "",
              "goal_subject": "evaluation",
              "proposed_steps": []
            }
            """,
        ]
    )
    registry = _FakeRegistry(
        {
            "run_rag_evaluation": _FakeRunEvaluationTool(),
        }
    )
    orchestrator = AdminOrchestrator(
        settings=Settings(planner_enabled=False),
        selector=_FakeSelector(PlannedAction(mode="qa", intent="qa", tool_name=None)),
        registry=registry,
        security_client=_FakeSecurityClient(),  # type: ignore[arg-type]
        generation_client=_FakeGenerationClient(),  # type: ignore[arg-type]
        explainer_client=planner_client,  # type: ignore[arg-type]
        agent_state_store=state_store,
        supabase_documents_client=_FakeSupabaseDocumentsClient(),  # type: ignore[arg-type]
    )

    response = orchestrator.handle(
        AdminRequestContext(
            message="run RAG evaluation",
            selected_mode="plan",
            session_id="eval-direct",
        )
    )

    assert response.status == "ok"
    assert response.intent == "recursive_plan_agent"
    assert response.agent_run is not None
    assert response.agent_run.stop_reason == "responded"
    assert response.agent_run.tool_call_count == 1
    assert response.result["stop_reason"] == "responded"
    assert response.result["facts"]["latest_user_language"] == "unknown"
    assert "completed successfully" in response.answer


def test_orchestrator_uses_recursive_agent_for_multilingual_chunking_request(tmp_path: Path) -> None:
    state_store = AgentRunStateStore(state_path=tmp_path / "agent_run_states.json")
    registry = _FakeRegistry({"get_chunking_strategy_catalog": _FakeChunkingCatalogTool()})
    registry = _FakeRegistry(
        {
            "get_chunking_strategy_catalog": _FakeChunkingCatalogTool(),
            "update_chunking_config": _FakeUpdateChunkingConfigTool(
                {
                    "answer": "Updated chunking configuration.",
                    "result": {"chunk_strategy": "late", "chunk_size": 800, "chunk_overlap": 120},
                }
            ),
        }
    )
    planner_client = _QueuedPlannerClient(
        payloads=[
            """
            {
              "action_type": "call_tool",
              "message": "Je vais d'abord inspecter les strategies de chunking disponibles.",
              "tool_name": "get_chunking_strategy_catalog",
              "arguments": {},
              "reason": "Il faut connaitre les options de chunking supportees avant de recommander une strategie.",
              "expected_observation": "Configuration actuelle et options de chunking.",
              "goal_subject": "chunking",
              "proposed_steps": []
            }
            """,
            """
            {
              "action_type": "respond",
              "message": "Pour reduire le cout tout en gardant une bonne structure, la strategie 'late' reste un bon point de depart. Je peux aussi proposer un changement explicite si vous voulez l'appliquer.",
              "tool_name": null,
              "arguments": {},
              "reason": "Recommendation grounded in the chunking catalog.",
              "expected_observation": "",
              "goal_subject": "chunking",
              "proposed_steps": [
                {
                  "tool": "update_chunking_config",
                  "arguments": {
                    "chunk_strategy": "late",
                    "chunk_size": 800,
                    "chunk_overlap": 120
                  }
                }
              ]
            }
            """,
        ]
    )
    orchestrator = AdminOrchestrator(
        settings=Settings(planner_enabled=False),
        selector=_FakeSelector(PlannedAction(mode="qa", intent="qa", tool_name=None)),
        registry=registry,
        security_client=_FakeSecurityClient(),  # type: ignore[arg-type]
        generation_client=_FakeGenerationClient(),  # type: ignore[arg-type]
        explainer_client=planner_client,  # type: ignore[arg-type]
        agent_state_store=state_store,
        supabase_documents_client=_FakeSupabaseDocumentsClient(),  # type: ignore[arg-type]
    )

    response = orchestrator.handle(
        AdminRequestContext(
            message="Quelle strategie de chunking dois-je choisir pour reduire le cout ?",
            selected_mode="plan",
            session_id="admin-1",
        )
    )

    assert response.status == "ok"
    assert response.intent == "recursive_plan_agent"
    assert "late" in response.answer
    assert response.agent_run is not None
    assert response.agent_run.goal is not None
    assert response.agent_run.goal.subject == "chunking"


def test_orchestrator_falls_back_to_legacy_planner_for_delete_document_requests(tmp_path: Path) -> None:
    state_store = AgentRunStateStore(state_path=tmp_path / "agent_run_states.json")
    registry = _FakeRegistry({"delete_document": _FakeDeleteDocumentTool()})
    planner_client = _QueuedPlannerClient(
        payloads=[
            """
            {
              "action_type": "stop",
              "message": "",
              "tool_name": null,
              "arguments": {},
              "reason": "fallback_legacy_planner",
              "expected_observation": "",
              "goal_subject": "documents",
              "proposed_steps": []
            }
            """
        ]
    )
    orchestrator = AdminOrchestrator(
        settings=Settings(planner_enabled=False),
        selector=_FakeSelector(
            PlannedAction(
                mode="tool_call",
                intent="delete_document",
                tool_name="delete_document",
                arguments={"target_relative_path": "doc.pdf"},
                answer="Are you sure you want to delete doc.pdf?",
                requires_confirmation=True,
            )
        ),
        registry=registry,
        security_client=_FakeSecurityClient(),  # type: ignore[arg-type]
        generation_client=_FakeGenerationClient(),  # type: ignore[arg-type]
        explainer_client=planner_client,  # type: ignore[arg-type]
        agent_state_store=state_store,
        supabase_documents_client=_FakeSupabaseDocumentsClient(),  # type: ignore[arg-type]
    )

    response = orchestrator.handle(
        AdminRequestContext(
            message="Delete document doc.pdf",
            selected_mode="plan",
            session_id="admin-1",
        )
    )

    assert response.status == "needs_confirmation"
    assert response.pending_action is not None
    assert response.pending_action.tool == "delete_document"


def test_orchestrator_uses_fast_read_only_path_for_multilingual_chunking_question(tmp_path: Path) -> None:
    state_store = AgentRunStateStore(state_path=tmp_path / "agent_run_states.json")
    planner_client = _QueuedPlannerClient(
        payloads=[],
        route_payload="""
        {
          "route": "fast_read_only",
          "subject": "chunking",
          "bundle_id": "chunking_review",
          "reason": "The user is asking for an explanation and recommendation about chunking in French."
        }
        """,
        text_response="",
    )
    registry = _FakeRegistry(
        {
            "get_chunking_config": _FakeTool(
                {
                    "answer": "Current chunking strategy is 'late' with chunk size 800 and overlap 120.",
                    "result": {"chunk_strategy": "late", "chunk_size": 800, "chunk_overlap": 120},
                }
            ),
            "get_chunking_strategy_catalog": _FakeChunkingCatalogTool(),
        }
    )
    orchestrator = AdminOrchestrator(
        settings=Settings(planner_enabled=False),
        selector=_FakeSelector(PlannedAction(mode="qa", intent="qa", tool_name=None)),
        registry=registry,
        security_client=_FakeSecurityClient(),  # type: ignore[arg-type]
        generation_client=_FakeGenerationClient(),  # type: ignore[arg-type]
        explainer_client=planner_client,  # type: ignore[arg-type]
        agent_state_store=state_store,
        supabase_documents_client=_FakeSupabaseDocumentsClient(),  # type: ignore[arg-type]
    )

    response = orchestrator.handle(
        AdminRequestContext(
            message="Quel choix de decoupage faire pour reduire les couts sans perdre beaucoup de performance ?",
            selected_mode="plan",
            session_id="fast-chunking",
        )
    )

    assert response.status == "ok"
    assert response.intent == "fast_read_only_plan"
    assert response.result["route"] == "fast_read_only"
    assert response.result["bundle_id"] == "chunking_review"
    assert "Comparaison directe des strategies disponibles" in response.answer
    assert "late" in response.answer
    assert "semantic" in response.answer
    assert "overlap" in response.answer
    assert "For performance/retrieval quality" in response.answer
    assert "reranker" not in response.answer.lower()
    assert "evaluation" not in response.answer.lower()
    assert "rag" not in response.answer.lower()


def test_orchestrator_uses_fast_read_only_path_for_performance_question(tmp_path: Path) -> None:
    state_store = AgentRunStateStore(state_path=tmp_path / "agent_run_states.json")
    planner_client = _QueuedPlannerClient(
        payloads=[],
        route_payload="""
        {
          "route": "fast_read_only",
          "subject": "evaluation",
          "bundle_id": "evaluation_review",
          "reason": "The user is asking about performance and evaluation, which maps to a read-only evaluation bundle."
        }
        """,
        text_response="Current performance should be judged from the latest evaluation report. Faithfulness is 0.7 and factual correctness is 0.6, and the next step would be to compare those metrics before changing configuration.",
    )
    registry = _FakeRegistry(
        {
            "get_evaluation_report": _FakeEvaluationReportTool(),
            "get_evaluation_capability_catalog": _FakeTool(
                {
                    "answer": "Evaluation capabilities are available through the local report directory and evaluation endpoint.",
                    "result": {"subject": "evaluation", "capabilities": {"supported_operations": ["run", "read_report"]}},
                }
            ),
        }
    )
    orchestrator = AdminOrchestrator(
        settings=Settings(planner_enabled=False),
        selector=_FakeSelector(PlannedAction(mode="qa", intent="qa", tool_name=None)),
        registry=registry,
        security_client=_FakeSecurityClient(),  # type: ignore[arg-type]
        generation_client=_FakeGenerationClient(),  # type: ignore[arg-type]
        explainer_client=planner_client,  # type: ignore[arg-type]
        agent_state_store=state_store,
        supabase_documents_client=_FakeSupabaseDocumentsClient(),  # type: ignore[arg-type]
    )

    response = orchestrator.handle(
        AdminRequestContext(
            message="How is the system performing right now and what should I watch before changing config?",
            selected_mode="plan",
            session_id="fast-eval",
        )
    )

    assert response.status == "ok"
    assert response.intent == "fast_read_only_plan"
    assert response.result["bundle_id"] == "evaluation_review"
    assert "Faithfulness" in response.answer


def test_fast_read_only_path_degrades_gracefully_when_one_tool_fails(tmp_path: Path) -> None:
    state_store = AgentRunStateStore(state_path=tmp_path / "agent_run_states.json")
    planner_client = _QueuedPlannerClient(
        payloads=[],
        route_payload="""
        {
          "route": "fast_read_only",
          "subject": "system_information",
          "bundle_id": "system_overview",
          "reason": "The user wants current system information."
        }
        """,
        text_response="Some system information is available, but one service health check failed.",
    )
    registry = _FakeRegistry(
        {
            "get_pipeline_status": _FailingTool(),
            "get_embedding_config": _FakeTool(
                {
                    "answer": "The current embedding model is text-embedding-3-small.",
                    "result": {"embedding_model": "text-embedding-3-small"},
                }
            ),
            "get_chunking_config": _FakeTool(
                {
                    "answer": "Current chunking strategy is late.",
                    "result": {"chunk_strategy": "late"},
                }
            ),
            "get_reranker_config": _FakeTool(
                {
                    "answer": "Current reranker is cross_encoder.",
                    "result": {"default_ranker": "cross_encoder"},
                }
            ),
            "get_evaluation_capability_catalog": _FakeTool(
                {
                    "answer": "Evaluation capabilities are available.",
                    "result": {"subject": "evaluation"},
                }
            ),
        }
    )
    orchestrator = AdminOrchestrator(
        settings=Settings(planner_enabled=False),
        selector=_FakeSelector(PlannedAction(mode="qa", intent="qa", tool_name=None)),
        registry=registry,
        security_client=_FakeSecurityClient(),  # type: ignore[arg-type]
        generation_client=_FakeGenerationClient(),  # type: ignore[arg-type]
        explainer_client=planner_client,  # type: ignore[arg-type]
        agent_state_store=state_store,
        supabase_documents_client=_FakeSupabaseDocumentsClient(),  # type: ignore[arg-type]
    )

    response = orchestrator.handle(
        AdminRequestContext(
            message="what are the current system informations",
            selected_mode="plan",
            session_id="fast-failure",
        )
    )

    assert response.status == "ok"
    assert response.intent == "fast_read_only_plan"
    assert response.activity[1].status == "failed"
    assert "failed" in response.result["observations"][0]["status"]


def test_orchestrator_stream_emits_progress_events_before_final(tmp_path: Path) -> None:
    state_store = AgentRunStateStore(state_path=tmp_path / "agent_run_states.json")
    planner_client = _QueuedPlannerClient(
        payloads=[
            """
            {
              "action_type": "call_tool",
              "message": "Inspect the chunking catalog first.",
              "tool_name": "get_chunking_strategy_catalog",
              "arguments": {},
              "reason": "Need a grounded read-only inspection.",
              "expected_observation": "Current chunking config and supported strategies.",
              "goal_subject": "chunking",
              "proposed_steps": []
            }
            """,
            """
            {
              "action_type": "respond",
              "message": "The current chunking setup was inspected successfully.",
              "tool_name": null,
              "arguments": {},
              "reason": "We have enough grounded information for a first response.",
              "expected_observation": "",
              "goal_subject": "chunking",
              "proposed_steps": []
            }
            """,
        ]
    )
    registry = _FakeRegistry({"get_chunking_strategy_catalog": _FakeChunkingCatalogTool()})
    orchestrator = AdminOrchestrator(
        settings=Settings(planner_enabled=False),
        selector=_FakeSelector(PlannedAction(mode="qa", intent="qa", tool_name=None)),
        registry=registry,
        security_client=_FakeSecurityClient(),  # type: ignore[arg-type]
        generation_client=_FakeGenerationClient(),  # type: ignore[arg-type]
        explainer_client=planner_client,  # type: ignore[arg-type]
        agent_state_store=state_store,
        supabase_documents_client=_FakeSupabaseDocumentsClient(),  # type: ignore[arg-type]
    )

    events = [
        json.loads(line)
        for line in orchestrator.stream(
            AdminRequestContext(
                message="show current chunking information",
                selected_mode="plan",
                session_id="stream-1",
            )
        )
    ]

    assert len(events) >= 2
    assert events[-1]["type"] == "final"
    assert any(event["type"] == "agent_decision" for event in events[:-1])
    assert any(event["type"] == "agent_observation" for event in events[:-1])


def test_orchestrator_soft_fallback_uses_grounded_observations_instead_of_mode_switch(tmp_path: Path) -> None:
    state_store = AgentRunStateStore(state_path=tmp_path / "agent_run_states.json")
    planner_client = _QueuedPlannerClient(
        payloads=[
            """
            {
              "action_type": "call_tool",
              "message": "Inspect the chunking catalog first.",
              "tool_name": "get_chunking_strategy_catalog",
              "arguments": {},
              "reason": "Ground the answer with a real tool output first.",
              "expected_observation": "Current chunking config and options.",
              "goal_subject": "chunking",
              "proposed_steps": []
            }
            """,
            """
            {
              "action_type": "stop",
              "message": "",
              "tool_name": null,
              "arguments": {},
              "reason": "fallback_legacy_planner",
              "expected_observation": "",
              "goal_subject": "chunking",
              "proposed_steps": [
                {
                  "tool": "update_chunking_config",
                  "arguments": {
                    "chunk_strategy": "late",
                    "chunk_size": 800,
                    "chunk_overlap": 120
                  }
                }
              ]
            }
            """,
        ]
    )
    registry = _FakeRegistry(
        {
            "get_chunking_strategy_catalog": _FakeChunkingCatalogTool(),
            "update_chunking_config": _FakeUpdateChunkingConfigTool(
                {
                    "answer": "Updated chunking configuration.",
                    "result": {"chunk_strategy": "late", "chunk_size": 800, "chunk_overlap": 120},
                }
            ),
        }
    )
    orchestrator = AdminOrchestrator(
        settings=Settings(planner_enabled=False),
        selector=_FakeSelector(PlannedAction(mode="qa", intent="qa", tool_name=None)),
        registry=registry,
        security_client=_FakeSecurityClient(),  # type: ignore[arg-type]
        generation_client=_FakeGenerationClient(),  # type: ignore[arg-type]
        explainer_client=planner_client,  # type: ignore[arg-type]
        agent_state_store=state_store,
        supabase_documents_client=_FakeSupabaseDocumentsClient(),  # type: ignore[arg-type]
    )

    response = orchestrator.handle(
        AdminRequestContext(
            message="quelle strategie de chunking est active ?",
            selected_mode="plan",
            session_id="soft-fallback",
        )
    )

    assert response.status == "ok"
    assert response.mode == "advisory"
    assert "Switch to Q&A mode" not in response.answer
    assert response.agent_run is not None
    assert response.agent_run.stop_reason == "soft_fallback_responded"


def test_orchestrator_starts_fresh_run_for_new_non_follow_up_message(tmp_path: Path) -> None:
    state_store = AgentRunStateStore(state_path=tmp_path / "agent_run_states.json")
    planner_client = _QueuedPlannerClient(
        payloads=[
            """
            {
              "action_type": "respond",
              "message": "First answer with a proposed reranker change.",
              "tool_name": null,
              "arguments": {},
              "reason": "Initial answer.",
              "expected_observation": "",
              "goal_subject": "reranking",
              "proposed_steps": [
                {
                  "tool": "update_reranker_config",
                  "arguments": {
                    "default_ranker": "cross_encoder",
                    "rerank_top_n": 10
                  }
                }
              ]
            }
            """,
            """
            {
              "action_type": "respond",
              "message": "Fresh answer for a different question.",
              "tool_name": null,
              "arguments": {},
              "reason": "New top-level request.",
              "expected_observation": "",
              "goal_subject": "system_information",
              "proposed_steps": []
            }
            """,
        ]
    )
    registry = _FakeRegistry(
        {
            "update_reranker_config": _FakeUpdateRerankerConfigTool(
                {
                    "answer": "Updated reranker configuration.",
                    "result": {"default_ranker": "cross_encoder", "rerank_top_n": 10},
                }
            )
        }
    )
    orchestrator = AdminOrchestrator(
        settings=Settings(planner_enabled=False),
        selector=_FakeSelector(PlannedAction(mode="qa", intent="qa", tool_name=None)),
        registry=registry,
        security_client=_FakeSecurityClient(),  # type: ignore[arg-type]
        generation_client=_FakeGenerationClient(),  # type: ignore[arg-type]
        explainer_client=planner_client,  # type: ignore[arg-type]
        agent_state_store=state_store,
        supabase_documents_client=_FakeSupabaseDocumentsClient(),  # type: ignore[arg-type]
    )

    first_response = orchestrator.handle(
        AdminRequestContext(
            message="Recommend a reranker",
            selected_mode="plan",
            session_id="same-session",
        )
    )
    second_response = orchestrator.handle(
        AdminRequestContext(
            message="what are the current system informations",
            selected_mode="plan",
            session_id="same-session",
        )
    )

    assert first_response.result["proposed_steps"]
    assert second_response.answer == "Fresh answer for a different question."
    assert second_response.result["proposed_steps"] == []
