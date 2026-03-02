from pathlib import Path
import sys

import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.config import Settings  # noqa: E402
from app.errors import EmbeddingProviderRateLimitError  # noqa: E402
from embeddings.openai_embedder import OpenAIEmbedder  # noqa: E402


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict[str, object] | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self) -> dict[str, object]:
        return self._payload


class _FakeClient:
    def __init__(self, responses: list[_FakeResponse]) -> None:
        self._responses = responses
        self.calls: list[dict[str, object]] = []

    def post(self, url: str, json: dict[str, object]) -> _FakeResponse:
        self.calls.append({"url": url, "json": json})
        if not self._responses:
            raise AssertionError("No more fake responses configured")
        return self._responses.pop(0)


def test_embedder_batches_requests() -> None:
    settings = Settings(openai_key="test-key", embedding_batch_size=2, openai_max_retries=0)
    embedder = OpenAIEmbedder(settings)
    embedder._client = _FakeClient(
        responses=[
            _FakeResponse(200, {"data": [{"embedding": [0.1]}, {"embedding": [0.2]}]}),
            _FakeResponse(200, {"data": [{"embedding": [0.3]}, {"embedding": [0.4]}]}),
            _FakeResponse(200, {"data": [{"embedding": [0.5]}]}),
        ]
    )

    vectors = embedder.embed_texts(["a", "b", "c", "d", "e"])

    assert len(vectors) == 5
    assert [call["json"]["input"] for call in embedder._client.calls] == [
        ["a", "b"],
        ["c", "d"],
        ["e"],
    ]


def test_embedder_retries_rate_limit_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        openai_key="test-key",
        embedding_batch_size=10,
        openai_max_retries=3,
        openai_retry_base_seconds=0.01,
    )
    embedder = OpenAIEmbedder(settings)
    embedder._client = _FakeClient(
        responses=[
            _FakeResponse(429, text="rate limited"),
            _FakeResponse(429, text="rate limited"),
            _FakeResponse(200, {"data": [{"embedding": [0.11, 0.22]}]}),
        ]
    )

    sleeps: list[float] = []
    monkeypatch.setattr("embeddings.openai_embedder.sleep", lambda value: sleeps.append(value))

    vectors = embedder.embed_texts(["hello"])

    assert vectors == [[0.11, 0.22]]
    assert len(embedder._client.calls) == 3
    assert sleeps == [0.01, 0.02]


def test_embedder_raises_after_rate_limit_exhausted() -> None:
    settings = Settings(openai_key="test-key", openai_max_retries=1, openai_retry_base_seconds=0.0)
    embedder = OpenAIEmbedder(settings)
    embedder._client = _FakeClient(
        responses=[
            _FakeResponse(429, text="rate limited"),
            _FakeResponse(429, text="rate limited"),
        ]
    )

    with pytest.raises(EmbeddingProviderRateLimitError):
        embedder.embed_texts(["hello"])
