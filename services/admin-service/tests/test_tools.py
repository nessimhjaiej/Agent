from pathlib import Path
import sys

import httpx

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.config import Settings  # noqa: E402
from app.tools import AdminToolbox  # noqa: E402


class _MockResponse:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = {"content-type": "application/json"}

    def json(self):
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("error", request=None, response=None)


class _MockClient:
    def __init__(self, responses):
        self._responses = responses

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, url, **kwargs):
        return self._responses.pop(0)

    def post(self, url, **kwargs):
        return self._responses.pop(0)


def _settings() -> Settings:
    return Settings(
        openai_key="",
        ingestion_base_url="http://ingestion",
        embedding_base_url="http://embedding",
        generation_base_url="http://generation",
        retrieval_base_url="http://retrieval",
    )


def test_get_ingestion_status_aggregates_counts(monkeypatch) -> None:  # noqa: ANN001
    responses = [
        _MockResponse(
            200,
            {
                "documents": [
                    {"status": "validated", "embedded": True},
                    {"status": "validated", "embedded": False},
                    {"status": "pending", "embedded": False},
                ]
            },
        )
    ]
    monkeypatch.setattr(AdminToolbox, "_client", lambda self: _MockClient(responses))
    result = AdminToolbox(_settings(), access_token="token").get_ingestion_status()
    assert result["total_documents"] == 3
    assert result["embedded_documents"] == 1
    assert result["status_counts"]["validated"] == 2


def test_run_evaluation_calls_generation_api(monkeypatch) -> None:  # noqa: ANN001
    responses = [_MockResponse(200, {"status": "ok", "report": {"report_id": "r1"}})]
    monkeypatch.setattr(AdminToolbox, "_client", lambda self: _MockClient(responses))
    result = AdminToolbox(_settings()).run_evaluation("evals/sample_eval_dataset.json")
    assert result["report"]["report_id"] == "r1"


def test_reindex_document_chains_remove_then_index(monkeypatch) -> None:  # noqa: ANN001
    responses = [
        _MockResponse(200, {"status": "ok", "deleted_count": 4}),
        _MockResponse(200, {"status": "indexed", "document_id": "doc-1"}),
    ]
    monkeypatch.setattr(AdminToolbox, "_client", lambda self: _MockClient(responses))
    result = AdminToolbox(_settings()).reindex_document("doc-1")
    assert result["remove_result"]["deleted_count"] == 4
    assert result["index_result"]["document_id"] == "doc-1"


def test_reindex_validated_documents_loops_over_candidates(monkeypatch) -> None:  # noqa: ANN001
    toolbox = AdminToolbox(_settings(), access_token="token")
    monkeypatch.setattr(
        toolbox,
        "list_loaded_documents",
        lambda: {
            "documents": [
                {"id": "doc-1", "status": "validated"},
                {"id": "doc-2", "status": "pending"},
                {"id": "doc-3", "status": "validated"},
            ]
        },
    )
    monkeypatch.setattr(toolbox, "reindex_document", lambda document_id: {"document_id": document_id})
    result = toolbox.reindex_validated_documents()
    assert result["validated_count"] == 2
    assert result["reindexed_count"] == 2


def test_get_repo_config_reads_env_local_override(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("PREPROCESSING_CHUNK_SIZE=800\nPREPROCESSING_CHUNK_STRATEGY=late\n", encoding="utf-8")
    (tmp_path / ".env.local").write_text("PREPROCESSING_CHUNK_SIZE=750\n", encoding="utf-8")
    settings = Settings(project_root=tmp_path, openai_key="")
    result = AdminToolbox(settings).get_repo_config("preprocessing")
    assert result["scope"] == "preprocessing"
    assert result["config"]["chunk_size"] == 750
    assert result["config"]["chunk_strategy"] == "late"


def test_update_repo_config_writes_env_local(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("PREPROCESSING_CHUNK_SIZE=800\n", encoding="utf-8")
    settings = Settings(project_root=tmp_path, openai_key="")
    result = AdminToolbox(settings).update_repo_config("preprocessing", {"chunk_size": 900, "chunk_overlap": 100})
    assert result["updated"]["chunk_size"] == 900
    env_local = (tmp_path / ".env.local").read_text(encoding="utf-8")
    assert "PREPROCESSING_CHUNK_SIZE=900" in env_local
    assert "PREPROCESSING_CHUNK_OVERLAP=100" in env_local
