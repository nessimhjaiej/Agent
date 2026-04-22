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
            request = httpx.Request("GET", "http://testserver")
            response = httpx.Response(self.status_code, request=request, json=self._payload)
            raise httpx.HTTPStatusError("error", request=request, response=response)


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

    def put(self, url, **kwargs):
        return self._responses.pop(0)


def _settings() -> Settings:
    return Settings(
        openai_key="",
        ingestion_base_url="http://ingestion",
        preprocessing_base_url="http://preprocessing",
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


def test_get_capabilities_exposes_supported_services_and_subjects() -> None:
    capabilities = AdminToolbox(_settings()).get_capabilities()

    assert "retrieval" in capabilities["services"]
    assert "top_k_retrieve" in capabilities["services"]["retrieval"]["config_keys"]
    assert capabilities["services"]["retrieval"]["update_tool"] == "update_repo_config"
    assert capabilities["subjects"]["reranking"]["read_tool"] == "get_reranking_methods"
    assert "llm_batch" in capabilities["subjects"]["reranking"]["enum_values"]


def test_run_evaluation_calls_generation_api(monkeypatch) -> None:  # noqa: ANN001
    responses = [_MockResponse(200, {"status": "ok", "report": {"report_id": "r1"}})]
    monkeypatch.setattr(AdminToolbox, "_client", lambda self: _MockClient(responses))
    result = AdminToolbox(_settings()).run_evaluation("evals/sample_eval_dataset.json")
    assert result["report"]["report_id"] == "r1"


def test_run_evaluation_404_raises_actionable_message(monkeypatch) -> None:  # noqa: ANN001
    responses = [_MockResponse(404, {"detail": "Not Found"})]
    monkeypatch.setattr(AdminToolbox, "_client", lambda self: _MockClient(responses))

    try:
        AdminToolbox(_settings()).run_evaluation("evals/sample_eval_dataset.json")
    except ValueError as exc:
        message = str(exc)
    else:
        raise AssertionError("Expected ValueError for missing evaluation endpoint")

    assert "generation-service returned 404" in message
    assert "/generation/evaluations/run" in message


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


def test_get_repo_config_reads_preprocessing_service(monkeypatch) -> None:  # noqa: ANN001
    responses = [
        _MockResponse(
            200,
            {
                "status": "ok",
                "scope": "preprocessing",
                "config": {"chunk_size": 800, "chunk_strategy": "late", "chunk_overlap": 120, "pipeline_version": "v1"},
                "sources": {"chunk_size": "preprocessing-service runtime"},
            },
        )
    ]
    monkeypatch.setattr(AdminToolbox, "_client", lambda self: _MockClient(responses))
    result = AdminToolbox(_settings()).get_repo_config("preprocessing")
    assert result["scope"] == "preprocessing"
    assert result["config"]["chunk_size"] == 800
    assert result["config"]["chunk_strategy"] == "late"


def test_update_repo_config_calls_preprocessing_service(monkeypatch) -> None:  # noqa: ANN001
    responses = [
        _MockResponse(
            200,
            {
                "status": "ok",
                "scope": "preprocessing",
                "updated": {"chunk_size": 900, "chunk_overlap": 100},
                "applied_via": "preprocessing-service",
                "restart_required": False,
            },
        )
    ]
    monkeypatch.setattr(AdminToolbox, "_client", lambda self: _MockClient(responses))
    result = AdminToolbox(_settings()).update_repo_config("preprocessing", {"chunk_size": 900, "chunk_overlap": 100})
    assert result["updated"]["chunk_size"] == 900
    assert result["updated"]["chunk_overlap"] == 100
    assert result["applied_via"] == "preprocessing-service"


def test_get_chunking_methods_reads_current_preprocessing_settings(monkeypatch) -> None:  # noqa: ANN001
    responses = [
        _MockResponse(
            200,
            {
                "status": "ok",
                "scope": "preprocessing",
                "current_strategy": "late",
                "current_chunk_size": 800,
                "current_chunk_overlap": 120,
                "methods": [
                    {"name": "late", "exists": True, "implemented": True},
                    {"name": "overlap", "exists": True, "implemented": True},
                    {"name": "semantic", "exists": True, "implemented": True},
                    {"name": "sentence", "exists": True, "implemented": False},
                ],
            },
        )
    ]
    monkeypatch.setattr(AdminToolbox, "_client", lambda self: _MockClient(responses))
    result = AdminToolbox(_settings()).get_chunking_methods()
    assert result["current_strategy"] == "late"
    assert result["current_chunk_size"] == 800
    assert result["current_chunk_overlap"] == 120
    names = {item["name"] for item in result["methods"]}
    assert {"late", "overlap", "semantic", "sentence"} <= names


def test_get_repo_config_reads_retrieval_service(monkeypatch) -> None:  # noqa: ANN001
    responses = [
        _MockResponse(
            200,
            {
                "status": "ok",
                "scope": "retrieval",
                "config": {"default_ranker_type": "cross_encoder", "top_k_retrieve": 9, "top_k_return": 4},
                "sources": {
                    "default_ranker_type": "services/retrieval-service/app/config.py",
                    "top_k_retrieve": "services/retrieval-service/app/config.py",
                    "top_k_return": "services/retrieval-service/app/config.py",
                },
            },
        )
    ]
    monkeypatch.setattr(AdminToolbox, "_client", lambda self: _MockClient(responses))
    result = AdminToolbox(_settings()).get_repo_config("retrieval")
    assert result["scope"] == "retrieval"
    assert result["config"]["default_ranker_type"] == "cross_encoder"
    assert result["config"]["top_k_retrieve"] == 9
    assert result["config"]["top_k_return"] == 4


def test_get_reranking_methods_reads_current_retrieval_settings(monkeypatch) -> None:  # noqa: ANN001
    responses = [
        _MockResponse(
            200,
            {
                "status": "ok",
                "scope": "retrieval",
                "current_default_ranker_type": "llm_batch",
                "methods": [
                    {"name": "none", "exists": True, "implemented": True},
                    {"name": "cross_encoder", "exists": True, "implemented": True},
                    {"name": "llm_batch", "exists": True, "implemented": True},
                ],
            },
        )
    ]
    monkeypatch.setattr(AdminToolbox, "_client", lambda self: _MockClient(responses))
    result = AdminToolbox(_settings()).get_reranking_methods()
    assert result["current_default_ranker_type"] == "llm_batch"
    names = {item["name"] for item in result["methods"]}
    assert {"none", "cross_encoder", "llm_batch"} <= names


def test_update_repo_config_calls_retrieval_service(monkeypatch) -> None:  # noqa: ANN001
    responses = [
        _MockResponse(
            200,
            {
                "status": "ok",
                "scope": "retrieval",
                "updated": {"default_ranker_type": "cross_encoder", "top_k_retrieve": 11, "top_k_return": 6},
                "applied_via": "retrieval-service",
                "restart_required": False,
            },
        )
    ]
    monkeypatch.setattr(AdminToolbox, "_client", lambda self: _MockClient(responses))
    result = AdminToolbox(_settings()).update_repo_config(
        "retrieval",
        {"ranker": "cross_encoder", "top_k_retrieve": 11, "top_k_return": 6},
    )
    assert result["updated"]["default_ranker_type"] == "cross_encoder"
    assert result["updated"]["top_k_retrieve"] == 11
    assert result["updated"]["top_k_return"] == 6
    assert result["applied_via"] == "retrieval-service"
