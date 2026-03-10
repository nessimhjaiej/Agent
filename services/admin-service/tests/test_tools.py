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
from app.tools.config_tools import UpdateChunkingConfigTool, UpdateEmbeddingModelTool  # noqa: E402
from app.tools.env_store import EnvConfigStore  # noqa: E402
from app.tools.evaluation_tools import EvaluationReportStore, GetEvaluationReportTool  # noqa: E402
from app.tools.knowledge_tools import DeleteValidatedDocumentsTool, EmbedDocumentTool  # noqa: E402
from app.tools.restart_tools import RestartServicesTool  # noqa: E402


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


def test_embed_document_tool_indexes_target_path() -> None:
    client = _FakeIngestionClient()
    tool = EmbedDocumentTool(ingestion_client=client)  # type: ignore[arg-type]

    response = tool.execute({"target_relative_path": "supabase/validated/u/doc.pdf"})

    assert response.status == "ok"
    assert client.index_calls[0]["target_relative_path"] == "supabase/validated/u/doc.pdf"
    assert response.result["indexed_count"] == 4


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


def test_intent_parser_routes_composite_requests_and_leaves_ambiguous_to_qa() -> None:
    parser = IntentParser()

    planned = parser.parse("change chunk size to 400 and restart preprocessing")
    qa = parser.parse("Should we reindex the corpus or just explain the risks?")

    assert planned.tool_name == "update_chunking_config"
    assert planned.arguments["chunk_size"] == 400
    assert planned.arguments["restart_services"] == ["preprocessing-service", "ingestion-service"]
    assert needs_confirmation(planned.tool_name or "", True) is True
    assert qa.mode == "qa"
