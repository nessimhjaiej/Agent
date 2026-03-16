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
from app.tools.config_tools import (  # noqa: E402
    GetChunkingStrategyCatalogTool,
    GetEmbeddingCapabilityCatalogTool,
    GetRerankerStrategyCatalogTool,
    UpdateChunkingConfigTool,
    UpdateEmbeddingModelTool,
    UpdateRerankerConfigTool,
)
from app.tools.base import ToolMetadata  # noqa: E402
from app.tools.env_store import EnvConfigStore  # noqa: E402
from app.tools.evaluation_tools import EvaluationReportStore, GetEvaluationReportTool  # noqa: E402
from app.tools.knowledge_tools import (
    DeleteDocumentTool,
    DeleteValidatedDocumentsTool,
    EmbedDocumentTool,
    EmbedValidatedDocumentsTool,
    ReindexCorpusTool,
    resolve_synced_supabase_reference,
    resolve_supabase_document_reference,
)  # noqa: E402
from app.tools.registry import ToolRegistry  # noqa: E402
from app.tools.restart_tools import RestartServicesTool  # noqa: E402
from app.config import Settings  # noqa: E402


class _FakeIngestionClient:
    def __init__(self) -> None:
        self.delete_calls: list[str] = []

    def delete_document(self, document_id: str) -> dict:
        self.delete_calls.append(document_id)
        return {
            "status": "ok",
            "document_id": document_id,
            "storage_path": f"validated/user/{document_id}.pdf",
        }


class _FakeSupabaseDocumentsClient:
    def __init__(self, documents: list[dict] | None = None) -> None:
        self._documents = documents or []
    def list_documents(self) -> list[dict]:
        return list(self._documents)


class _FakeEmbeddingClient:
    def __init__(self) -> None:
        self.index_calls: list[dict] = []
        self.remove_calls: list[str] = []

    def index_document(self, document_id: str, skip_if_embedded: bool = True) -> dict:
        self.index_calls.append(
            {
                "document_id": document_id,
                "skip_if_embedded": skip_if_embedded,
            }
        )
        return {
            "status": "indexed",
            "document_id": document_id,
            "storage_path": f"validated/user/{document_id}.pdf",
            "chunks_count": 4,
            "indexed_count": 4,
            "embedded": True,
        }

    def remove_document(self, document_id: str) -> dict:
        self.remove_calls.append(document_id)
        return {
            "status": "ok",
            "document_id": document_id,
            "storage_path": f"validated/user/{document_id}.pdf",
            "matched_objects_count": 1,
            "deleted_count": 3,
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
    embedding_client = _FakeEmbeddingClient()
    supabase_client = _FakeSupabaseDocumentsClient(
        documents=[
            {
                "id": "doc-1",
                "original_name": "doc.pdf",
                "storage_path": "validated/u/doc.pdf",
                "status": "validated",
                "embedded": False,
            }
        ]
    )
    tool = EmbedDocumentTool(  # type: ignore[arg-type]
        embedding_client=embedding_client,
        supabase_documents_client=supabase_client,
    )

    response = tool.execute({"target_relative_path": "supabase/validated/u/doc.pdf"})

    assert response.status == "ok"
    assert embedding_client.index_calls[0]["document_id"] == "doc-1"
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
    ingestion_client = _FakeIngestionClient()
    embedding_client = _FakeEmbeddingClient()
    supabase_client = _FakeSupabaseDocumentsClient(
        documents=[
            {
                "id": "doc-1",
                "original_name": "cybersecurity-policy.pdf",
                "storage_path": "validated/user/cybersecurity-policy.pdf",
                "status": "validated",
                "embedded": True,
            }
        ]
    )
    tool = DeleteDocumentTool(  # type: ignore[arg-type]
        ingestion_client=ingestion_client,
        embedding_client=embedding_client,
        supabase_documents_client=supabase_client,
    )

    response = tool.execute(
        {
            "target_relative_path": "supabase/validated/user/cybersecurity-policy.pdf",
            "cleanup_index": True,
        }
    )

    assert response.status == "ok"
    assert embedding_client.remove_calls == ["doc-1"]
    assert ingestion_client.delete_calls == ["doc-1"]


def test_delete_validated_documents_tool_removes_indexed_vectors_for_validated_docs() -> None:
    embedding_client = _FakeEmbeddingClient()
    supabase_client = _FakeSupabaseDocumentsClient(
        documents=[
            {"id": "a", "storage_path": "validated/user/doc-a.pdf", "status": "validated", "embedded": True},
            {"id": "b", "storage_path": "validated/user/doc-b.md", "status": "validated", "embedded": False},
            {"id": "c", "storage_path": "pending/user/doc-c.pdf", "status": "pending", "embedded": False},
        ]
    )
    tool = DeleteValidatedDocumentsTool(  # type: ignore[arg-type]
        embedding_client=embedding_client,
        supabase_documents_client=supabase_client,
    )

    response = tool.execute({})

    assert response.status == "ok"
    assert embedding_client.remove_calls == ["a", "b"]


def test_embed_validated_documents_tool_indexes_validated_documents() -> None:
    embedding_client = _FakeEmbeddingClient()
    supabase_client = _FakeSupabaseDocumentsClient(
        documents=[
            {"id": "a", "storage_path": "validated/user/doc-a.pdf", "status": "validated", "embedded": False},
            {"id": "b", "storage_path": "validated/user/doc-b.md", "status": "validated", "embedded": True},
        ]
    )
    tool = EmbedValidatedDocumentsTool(  # type: ignore[arg-type]
        embedding_client=embedding_client,
        supabase_documents_client=supabase_client,
    )

    response = tool.execute({})

    assert response.status == "ok"
    assert embedding_client.index_calls == [
        {"document_id": "a", "skip_if_embedded": True},
        {"document_id": "b", "skip_if_embedded": True},
    ]
    assert response.result["documents_processed"] == 2


def test_reindex_corpus_tool_removes_then_indexes_validated_documents() -> None:
    embedding_client = _FakeEmbeddingClient()
    supabase_client = _FakeSupabaseDocumentsClient(
        documents=[
            {"id": "a", "storage_path": "validated/user/doc-a.pdf", "status": "validated", "embedded": True},
            {"id": "b", "storage_path": "validated/user/doc-b.md", "status": "validated", "embedded": False},
        ]
    )
    tool = ReindexCorpusTool(  # type: ignore[arg-type]
        embedding_client=embedding_client,
        supabase_documents_client=supabase_client,
    )

    response = tool.execute({})

    assert response.status == "ok"
    assert embedding_client.remove_calls == ["a", "b"]
    assert embedding_client.index_calls == [
        {"document_id": "a", "skip_if_embedded": False},
        {"document_id": "b", "skip_if_embedded": False},
    ]
    assert response.result["deleted_count"] == 6


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


def test_get_reranker_strategy_catalog_returns_supported_options(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "RETRIEVAL_DEFAULT_RANKER=cross_encoder\nRETRIEVAL_DEFAULT_RERANK_TOP_N=12\n",
        encoding="utf-8",
    )
    store = EnvConfigStore(
        project_root=tmp_path,
        env_path=env_path,
        env_local_path=tmp_path / ".env.local",
    )
    tool = GetRerankerStrategyCatalogTool(store=store)

    response = tool.execute({})

    assert response.status == "ok"
    assert response.result["subject"] == "reranker"
    assert response.result["current_config"]["default_ranker"] == "cross_encoder"
    assert [item["name"] for item in response.result["options"]] == ["none", "cross_encoder", "llm_batch"]


def test_get_chunking_strategy_catalog_returns_supported_options(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "PREPROCESSING_CHUNK_STRATEGY=semantic\nPREPROCESSING_CHUNK_SIZE=900\nPREPROCESSING_CHUNK_OVERLAP=100\n",
        encoding="utf-8",
    )
    store = EnvConfigStore(
        project_root=tmp_path,
        env_path=env_path,
        env_local_path=tmp_path / ".env.local",
    )
    tool = GetChunkingStrategyCatalogTool(store=store)

    response = tool.execute({})

    assert response.status == "ok"
    assert response.result["subject"] == "chunking"
    assert response.result["current_config"]["chunk_strategy"] == "semantic"
    assert [item["name"] for item in response.result["options"]] == [
        "overlap",
        "semantic",
        "late",
        "sentence",
    ]


def test_get_embedding_capability_catalog_returns_current_settings(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "EMBEDDING_MODEL=text-embedding-3-large\nEMBEDDING_BATCH_SIZE=32\n",
        encoding="utf-8",
    )
    store = EnvConfigStore(
        project_root=tmp_path,
        env_path=env_path,
        env_local_path=tmp_path / ".env.local",
    )
    tool = GetEmbeddingCapabilityCatalogTool(
        settings=Settings(embedding_base_url="http://localhost:8002"),
        store=store,
    )

    response = tool.execute({})

    assert response.status == "ok"
    assert response.result["subject"] == "embedding"
    assert response.result["current_config"]["embedding_model"] == "text-embedding-3-large"
    assert "embedding_model" in response.result["capabilities"]["supported_controls"]


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
