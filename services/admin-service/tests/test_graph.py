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


def test_classifier_falls_back_to_workflow() -> None:
    classifier = IntentClassifier(_settings())
    result = classifier.classify("Please reindex all documents")
    assert result.category == "workflow"


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
