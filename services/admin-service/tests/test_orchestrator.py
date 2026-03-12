from pathlib import Path
import sys

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.config import Settings  # noqa: E402
from app.models import AdminChatTurn, AdminRequestContext, PlanStep, PlannedAction, PendingAction  # noqa: E402
from app.operation_history import AdminOperationHistoryStore  # noqa: E402
from app.orchestrator import AdminOrchestrator  # noqa: E402


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


class _FakeRegistry:
    def __init__(self, tools: dict) -> None:
        self._tools = tools

    def get(self, tool_name: str):  # noqa: ANN001
        return self._tools[tool_name]


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
