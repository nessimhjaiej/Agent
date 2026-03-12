from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.planner.confirmation import needs_confirmation  # noqa: E402
from app.planner.intent_parser import IntentParser  # noqa: E402
from app.planner.tool_selector import ToolSelector  # noqa: E402
from app.models import AdminRequestContext, PlanStep, PlannedAction  # noqa: E402
from app.tools.config_tools import UpdateChunkingConfigTool, UpdateEmbeddingModelTool, UpdateRerankerConfigTool  # noqa: E402
from app.tools.base import ToolMetadata  # noqa: E402
from app.tools.env_store import EnvConfigStore  # noqa: E402
from app.tools.evaluation_tools import EvaluationReportStore, GetEvaluationReportTool  # noqa: E402
from app.tools.knowledge_tools import (
    DeleteDocumentTool,
    DeleteValidatedDocumentsTool,
    EmbedDocumentTool,
    resolve_synced_supabase_reference,
    resolve_supabase_document_reference,
)  # noqa: E402
from app.tools.registry import ToolRegistry  # noqa: E402
from app.tools.restart_tools import RestartServicesTool  # noqa: E402
from app.config import Settings  # noqa: E402


class _FakeIngestionClient:
    def __init__(self) -> None:
        self.index_calls: list[dict] = []
        self.delete_calls: list[list[str]] = []

    def index_document(self, target_relative_path: str, skip_if_exists: bool = True) -> dict:
        self.index_calls.append(
            {
                "target_relative_path": target_relative_path,
                "skip_if_exists": skip_if_exists,
            }
        )
        return {
            "status": "indexed",
            "source_path": f"/shared/raw_data/{target_relative_path}",
            "exists_in_weaviate": False,
            "indexed": True,
            "chunks_count": 4,
            "indexed_count": 4,
        }

    def remove_document_chunks(self, target_relative_paths: list[str]) -> dict:
        self.delete_calls.append(target_relative_paths)
        return {
            "status": "ok",
            "requested_count": len(target_relative_paths),
            "matched_objects_count": len(target_relative_paths),
            "deleted_count": len(target_relative_paths) * 3,
        }


class _FakeSupabaseDocumentsClient:
    def __init__(self, documents: list[dict] | None = None) -> None:
        self._documents = documents or []
        self.deleted_storage_paths: list[str] = []

    def list_documents(self) -> list[dict]:
        return list(self._documents)

    def delete_document(self, storage_path: str) -> dict:
        self.deleted_storage_paths.append(storage_path)
        return {
            "storage_path": storage_path,
            "documents_deleted": 1,
            "document": next(
                (item for item in self._documents if item.get("storage_path") == storage_path),
                {"storage_path": storage_path},
            ),
        }


class _PlannerOnlyTool:
    def __init__(self, name: str) -> None:
        self.name = name
        self.metadata = ToolMetadata(
            name=name,
            description=f"Tool {name}",
            arguments_schema={"value": {"type": "string", "required": False}},
            output_description="returns a status payload",
            requires_confirmation=name.startswith("update"),
        )

    def execute(self, arguments: dict):  # noqa: ANN001
        raise AssertionError("Not used in these tests")


class _FakeLLMPlanner:
    def __init__(self, planned_action: PlannedAction | None) -> None:
        self._planned_action = planned_action

    def plan(self, context: AdminRequestContext) -> PlannedAction | None:
        return self._planned_action


def test_embed_document_tool_indexes_target_path() -> None:
    client = _FakeIngestionClient()
    tool = EmbedDocumentTool(ingestion_client=client)  # type: ignore[arg-type]

    response = tool.execute({"target_relative_path": "supabase/validated/u/doc.pdf"})

    assert response.status == "ok"
    assert client.index_calls[0]["target_relative_path"] == "supabase/validated/u/doc.pdf"
    assert response.result["indexed_count"] == 4


def test_resolve_supabase_document_reference_matches_documents_table_rows() -> None:
    resolution = resolve_supabase_document_reference(
        "delete the cybersecurity document",
        documents=[
            {
                "original_name": "cybersecurity-policy.pdf",
                "storage_path": "validated/user/cybersecurity-policy.pdf",
            }
        ],
    )

    assert resolution["status"] == "resolved"
    assert resolution["storage_path"] == "validated/user/cybersecurity-policy.pdf"


def test_resolve_synced_supabase_reference_matches_local_mirror(tmp_path: Path) -> None:
    mirrored = tmp_path / "shared" / "raw_data" / "supabase" / "validated" / "user"
    mirrored.mkdir(parents=True)
    (mirrored / "2023-cybersecurity-policy.pdf").write_text("x", encoding="utf-8")

    resolution = resolve_synced_supabase_reference(
        "delete the 2023 cybersecurity document",
        raw_root=str(tmp_path / "shared" / "raw_data" / "supabase"),
        local_root=str(tmp_path / "shared" / "raw_data"),
    )

    assert resolution["status"] == "resolved"
    assert resolution["target_relative_path"] == "supabase/validated/user/2023-cybersecurity-policy.pdf"


def test_delete_document_tool_deletes_supabase_document_and_chunks() -> None:
    client = _FakeIngestionClient()
    supabase_client = _FakeSupabaseDocumentsClient(
        documents=[
            {
                "original_name": "cybersecurity-policy.pdf",
                "storage_path": "validated/user/cybersecurity-policy.pdf",
            }
        ]
    )
    tool = DeleteDocumentTool(  # type: ignore[arg-type]
        ingestion_client=client,
        supabase_documents_client=supabase_client,
    )

    response = tool.execute(
        {
            "target_relative_path": "supabase/validated/user/cybersecurity-policy.pdf",
            "cleanup_index": True,
        }
    )

    assert response.status == "ok"
    assert client.delete_calls[0] == ["supabase/validated/user/cybersecurity-policy.pdf"]
    assert supabase_client.deleted_storage_paths == ["validated/user/cybersecurity-policy.pdf"]


def test_delete_validated_documents_tool_discovers_and_deletes_paths(tmp_path: Path) -> None:
    raw_dir = tmp_path / "shared" / "raw_data" / "supabase" / "validated" / "user"
    raw_dir.mkdir(parents=True)
    (raw_dir / "doc-a.pdf").write_text("a", encoding="utf-8")
    (raw_dir / "doc-b.md").write_text("b", encoding="utf-8")

    client = _FakeIngestionClient()
    tool = DeleteValidatedDocumentsTool(ingestion_client=client)  # type: ignore[arg-type]

    response = tool.execute(
        {
            "raw_dir": str(tmp_path / "shared" / "raw_data" / "supabase" / "validated"),
            "local_root": str(tmp_path / "shared" / "raw_data"),
        }
    )

    assert response.status == "ok"
    assert client.delete_calls[0] == [
        "supabase/validated/user/doc-a.pdf",
        "supabase/validated/user/doc-b.md",
    ]


def test_update_embedding_model_tool_writes_env_local(tmp_path: Path) -> None:
    store = EnvConfigStore(
        project_root=tmp_path,
        env_path=tmp_path / ".env",
        env_local_path=tmp_path / ".env.local",
    )
    tool = UpdateEmbeddingModelTool(store=store)

    response = tool.execute({"embedding_model": "text-embedding-3-large"})

    assert response.status == "ok"
    assert "text-embedding-3-large" in (tmp_path / ".env.local").read_text(encoding="utf-8")
    assert response.result["rollback"]["tool"] == "update_embedding_model"


def test_update_chunking_config_validates_overlap_less_than_size(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "PREPROCESSING_CHUNK_STRATEGY=late\nPREPROCESSING_CHUNK_SIZE=800\nPREPROCESSING_CHUNK_OVERLAP=120\n",
        encoding="utf-8",
    )
    store = EnvConfigStore(
        project_root=tmp_path,
        env_path=env_path,
        env_local_path=tmp_path / ".env.local",
    )
    tool = UpdateChunkingConfigTool(store=store)

    try:
        tool.execute({"chunk_overlap": 900})
    except ValueError as exc:
        assert "chunk_overlap must be smaller than chunk_size" in str(exc)
    else:
        raise AssertionError("Expected ValueError for invalid chunking config")


def test_update_reranker_config_returns_previous_values_for_rollback(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "RETRIEVAL_DEFAULT_RANKER=none\nRETRIEVAL_DEFAULT_RERANK_TOP_N=20\n",
        encoding="utf-8",
    )
    store = EnvConfigStore(
        project_root=tmp_path,
        env_path=env_path,
        env_local_path=tmp_path / ".env.local",
    )
    tool = UpdateRerankerConfigTool(store=store)

    response = tool.execute({"default_ranker": "cross_encoder", "rerank_top_n": 10})

    assert response.status == "ok"
    assert response.result["rollback"]["tool"] == "update_reranker_config"
    assert response.result["rollback"]["arguments"]["default_ranker"] == "none"


def test_get_evaluation_report_tool_loads_latest_report(tmp_path: Path) -> None:
    generation_dir = tmp_path / "services" / "generation-service"
    reports_dir = generation_dir / "evaluation_reports"
    reports_dir.mkdir(parents=True)
    report_path = reports_dir / "ragas_report_20260310_120000.json"
    report_path.write_text(
        json.dumps(
            {
                "generated_at_utc": "2026-03-10T12:00:00+00:00",
                "dataset_path": "evals/sample_eval_dataset.json",
                "sample_count": 3,
                "summary": {"faithfulness": 0.8},
                "records": [{"user_input": "q"}],
            }
        ),
        encoding="utf-8",
    )

    tool = GetEvaluationReportTool(report_store=EvaluationReportStore(project_root=tmp_path))
    response = tool.execute({})

    assert response.status == "ok"
    assert response.result["sample_count"] == 3
    assert response.result["summary"]["faithfulness"] == 0.8
    assert "Overall" in response.answer
    assert "Metrics" in response.answer


def test_get_evaluation_report_tool_falls_back_to_any_json_report(tmp_path: Path) -> None:
    generation_dir = tmp_path / "services" / "generation-service"
    reports_dir = generation_dir / "evaluation_reports"
    reports_dir.mkdir(parents=True)
    report_path = reports_dir / "ragas report sample.json"
    report_path.write_text(
        json.dumps(
            {
                "generated_at_utc": "2026-03-10T12:00:00+00:00",
                "dataset_path": "evals/sample_eval_dataset.json",
                "sample_count": 1,
                "summary": {"faithfulness": 0.7},
                "records": [],
            }
        ),
        encoding="utf-8",
    )

    tool = GetEvaluationReportTool(report_store=EvaluationReportStore(project_root=tmp_path))
    response = tool.execute({})

    assert response.status == "ok"
    assert response.result["sample_count"] == 1
    assert "Faithfulness" in response.answer


def test_restart_services_tool_schedules_script(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    captured: dict = {}

    def _fake_popen(command, cwd, creationflags):  # noqa: ANN001
        captured["command"] = command
        captured["cwd"] = cwd
        captured["creationflags"] = creationflags

        class _Proc:
            pass

        return _Proc()

    monkeypatch.setattr(subprocess, "Popen", _fake_popen)
    monkeypatch.setattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0, raising=False)

    tool = RestartServicesTool(project_root=tmp_path)
    response = tool.execute({"services": ["retrieval-service", "generation-service"], "delay_seconds": 5})

    assert response.status == "ok"
    assert "-Services" in captured["command"]
    assert "retrieval-service" in captured["command"]
    assert captured["cwd"] == tmp_path


def test_restart_services_tool_supports_docker_compose_runtime(monkeypatch, tmp_path: Path) -> None:  # noqa: ANN001
    captured: dict = {}

    def _fake_popen(command, cwd, creationflags=0):  # noqa: ANN001
        captured["command"] = command
        captured["cwd"] = cwd
        captured["creationflags"] = creationflags

        class _Proc:
            pass

        return _Proc()

    monkeypatch.setattr(subprocess, "Popen", _fake_popen)

    tool = RestartServicesTool(project_root=tmp_path)
    response = tool.execute(
        {
            "services": ["retrieval-service", "generation-service"],
            "runtime": "docker_compose",
        }
    )

    assert response.status == "ok"
    assert captured["command"][:5] == [
        "docker",
        "compose",
        "-f",
        str(tmp_path / "docker-compose.yml"),
        "restart",
    ]
    assert captured["cwd"] == tmp_path
    assert response.result["runtime"] == "docker_compose"


def test_intent_parser_is_conservative_fallback() -> None:
    parser = IntentParser()

    planned = parser.parse("change chunk size to 400 and restart preprocessing")
    status = parser.parse("show pipeline status")
    qa = parser.parse("Should we reindex the corpus or just explain the risks?")
    revert = parser.parse("revert the last two reranker changes")

    assert planned.mode == "qa"
    assert status.tool_name == "get_pipeline_status"
    assert qa.mode == "qa"
    assert revert.intent == "revert_changes"
    assert revert.arguments["count"] == 2
    assert revert.arguments["tool_names"] == ["update_reranker_config"]
    assert needs_confirmation(status.tool_name or "", True) is False


def test_tool_registry_exposes_structured_planning_metadata() -> None:
    registry = ToolRegistry(
        [
            _PlannerOnlyTool("get_pipeline_status"),
            _PlannerOnlyTool("update_chunking_config"),
        ]
    )

    planning_tools = registry.planning_tools()

    assert [tool.name for tool in planning_tools] == [
        "get_pipeline_status",
        "update_chunking_config",
    ]
    assert planning_tools[1].requires_confirmation is True
    assert planning_tools[1].arguments_schema["value"]["type"] == "string"


def test_tool_selector_prefers_llm_plan_and_filters_unknown_tools() -> None:
    registry = ToolRegistry([_PlannerOnlyTool("update_chunking_config")])
    selector = ToolSelector(
        settings=Settings(planner_enabled=False),
        registry=registry,
        llm_planner=_FakeLLMPlanner(
            PlannedAction(
                mode="tool_call",
                intent="apply_chunking_change",
                tool_name="apply_chunking_change",
                arguments={"chunk_size": 400},
                steps=[
                    PlanStep(tool_name="update_chunking_config", arguments={"chunk_size": 400}),
                    PlanStep(tool_name="unknown_tool", arguments={}),
                ],
            )
        ),  # type: ignore[arg-type]
    )

    planned = selector.select(AdminRequestContext(message="change chunk size to 400"))

    assert planned.tool_name == "apply_chunking_change"
    assert planned.steps[0].tool_name == "update_chunking_config"
    assert len(planned.steps) == 1
