from pathlib import Path
import sys

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.config import Settings  # noqa: E402
from app.graph import IntentClassifier, run_graph  # noqa: E402
from app.schemas import AdminChatRequest, IntentClassification  # noqa: E402
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
            raise RuntimeError("unexpected error")


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
    return Settings(openai_key="", max_iterations=8, max_tool_calls=8)


def test_classifier_falls_back_to_advisory() -> None:
    classifier = IntentClassifier(_settings())
    result = classifier.classify("Which reranking strategy is better for cost?")
    assert result.category == "advisory"


def test_classifier_falls_back_to_mutate_for_reindex() -> None:
    classifier = IntentClassifier(_settings())
    result = classifier.classify("Please reindex all documents")
    assert result.category == "mutate"


def test_run_graph_routes_to_mutation_confirmation(monkeypatch) -> None:  # noqa: ANN001
    classifier = IntentClassification(category="mutate", intent="mutate", reasoning="test")
    monkeypatch.setattr(IntentClassifier, "classify", lambda self, message: classifier)
    responses = [_MockResponse(200, {"documents": [{"id": "doc-1", "original_name": "doc-1.pdf"}]})]
    monkeypatch.setattr(AdminToolbox, "_client", lambda self: _MockClient(responses))

    response = run_graph(AdminChatRequest(message="delete document doc-1", access_token="token"), _settings())

    assert response.status == "needs_confirmation"
    assert response.mode == "mutate"
    assert response.requires_confirmation is True
    assert response.pending_action is not None


def test_run_graph_routes_to_inspect(monkeypatch) -> None:  # noqa: ANN001
    from langchain_core.tools import tool  # noqa: PLC0415
    import app.graph as graph_module  # noqa: PLC0415

    @tool
    def get_ingestion_status() -> dict:
        """Return mocked ingestion status."""
        return {"status": "ok", "total_documents": 0}

    monkeypatch.setattr(graph_module, "build_tools", lambda toolbox: [get_ingestion_status])
    response = run_graph(AdminChatRequest(message="show ingestion status"), _settings())

    assert response.status == "ok"
    assert response.mode == "inspect"


def test_run_graph_downgrades_unsupported_mutation(monkeypatch) -> None:  # noqa: ANN001
    classifier = IntentClassification(category="mutate", intent="mutate", reasoning="test")
    monkeypatch.setattr(IntentClassifier, "classify", lambda self, message: classifier)

    response = run_graph(AdminChatRequest(message="do the best procedure for current documents"), _settings())

    assert response.mode != "mutate"
    assert response.status == "ok"


def test_run_graph_builds_compound_plan(tmp_path: Path) -> None:
    settings = Settings(project_root=tmp_path, openai_key="", max_iterations=8, max_tool_calls=8)
    (tmp_path / ".env").write_text(
        "RETRIEVAL_DEFAULT_RANKER=none\nPREPROCESSING_CHUNK_OVERLAP=120\n",
        encoding="utf-8",
    )

    response = run_graph(
        AdminChatRequest(message="change chunk overlap to 115 and also check the current reranking options"),
        settings,
    )

    assert response.status == "needs_confirmation"
    assert response.pending_action is not None
    assert response.pending_action.tool == "compound_action"
    assert len(response.pending_action.steps) == 2
    assert response.pending_action.steps[0].tool == "update_repo_config"
    assert response.pending_action.steps[1].tool == "get_repo_config"


def test_run_graph_builds_mixed_compound_plan_for_embedding_and_mutation(tmp_path: Path) -> None:
    settings = Settings(project_root=tmp_path, openai_key="", max_iterations=8, max_tool_calls=8)
    (tmp_path / ".env").write_text(
        "EMBEDDING_EMBEDDING_MODEL=text-embedding-3-small\nRETRIEVAL_DEFAULT_RANKER=cross_encoder\n",
        encoding="utf-8",
    )

    response = run_graph(
        AdminChatRequest(message="tell me all embeddings configurations then change reranking strategy to none"),
        settings,
    )

    assert response.status == "needs_confirmation"
    assert response.pending_action is not None
    assert response.pending_action.tool == "compound_action"
    assert len(response.pending_action.steps) == 2
    assert response.pending_action.steps[0].tool == "get_repo_config"
    assert response.pending_action.steps[0].arguments["service_name"] == "embedding"
    assert response.pending_action.steps[1].tool == "update_repo_config"


def test_run_graph_answers_available_chunking_methods(tmp_path: Path) -> None:
    settings = Settings(
        project_root=tmp_path,
        openai_key="",
        max_iterations=8,
        max_tool_calls=8,
    )
    (tmp_path / ".env").write_text(
        "PREPROCESSING_CHUNK_SIZE=800\nPREPROCESSING_CHUNK_OVERLAP=120\nPREPROCESSING_CHUNK_STRATEGY=late\n",
        encoding="utf-8",
    )

    response = run_graph(AdminChatRequest(message="what are the available chunking methods"), settings)

    assert response.status == "ok"
    assert response.mode == "inspect"
    assert "late" in response.answer
    assert "overlap" in response.answer
    assert "semantic" in response.answer
