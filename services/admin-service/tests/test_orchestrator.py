from pathlib import Path
import sys

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.config import Settings  # noqa: E402
from app.models import AdminChatTurn, AdminRequestContext, PlanStep, PlannedAction, PendingAction  # noqa: E402
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
    )

    response = orchestrator.handle(AdminRequestContext(message="delete document doc.pdf"))

    assert response.status == "needs_confirmation"
    assert response.mode == "tool_call"
    assert response.executed is False
    assert response.pending_action is not None
    assert response.pending_action.tool == "delete_document"


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
    )

    response = orchestrator.handle(
        AdminRequestContext(
            message="Confirm deletion",
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


def test_orchestrator_routes_qa_requests_to_generation_service() -> None:
    orchestrator = AdminOrchestrator(
        settings=Settings(planner_enabled=False),
        selector=_FakeSelector(
            PlannedAction(mode="qa", intent="qa", tool_name=None, arguments={})
        ),
        registry=_FakeRegistry({}),
        security_client=_FakeSecurityClient(),  # type: ignore[arg-type]
        generation_client=_FakeGenerationClient(),  # type: ignore[arg-type]
    )

    response = orchestrator.handle(
        AdminRequestContext(
            message="Explain the current setup.",
            chat_history=[AdminChatTurn(role="user", content="Previous admin question")],
        )
    )

    assert response.status == "ok"
    assert response.mode == "qa"
    assert response.answer == "Here is the explanation."
    assert response.citations[0].document_name == "doc-1.pdf"


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
    )

    response = orchestrator.handle(
        AdminRequestContext(
            message="Confirm chunking change",
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
