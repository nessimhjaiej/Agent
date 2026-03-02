from time import sleep

import httpx

from app.config import Settings
from app.errors import EmbeddingProviderError, EmbeddingProviderRateLimitError
from embeddings.base import BaseEmbedder


class OpenAIEmbedder(BaseEmbedder):
    def __init__(self, settings: Settings) -> None:
        self._api_key = settings.openai_key
        self._model = settings.embedding_model
        self._dimensions = settings.embedding_dimensions
        self._batch_size = settings.embedding_batch_size
        self._timeout_seconds = settings.embedding_timeout_seconds
        self._max_retries = settings.openai_max_retries
        self._retry_base_seconds = settings.openai_retry_base_seconds
        self._client = httpx.Client(
            base_url="https://api.openai.com/v1",
            timeout=self._timeout_seconds,
            trust_env=False,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )

    @property
    def name(self) -> str:
        return "openai"

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        embeddings: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            batch = texts[start : start + self._batch_size]
            embeddings.extend(self._embed_batch(batch))
        return embeddings

    def _embed_batch(self, batch: list[str]) -> list[list[float]]:
        body: dict[str, object] = {
            "model": self._model,
            "input": batch,
        }
        if self._dimensions is not None:
            body["dimensions"] = self._dimensions

        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.post("/embeddings", json=body)
                if response.status_code == 429:
                    if attempt == self._max_retries:
                        raise EmbeddingProviderRateLimitError(
                            "OpenAI rate limit exceeded after retries"
                        )
                    self._sleep_backoff(attempt)
                    continue

                if response.status_code >= 500:
                    if attempt == self._max_retries:
                        raise EmbeddingProviderError(
                            f"OpenAI server error {response.status_code}: {response.text}"
                        )
                    self._sleep_backoff(attempt)
                    continue

                if response.status_code >= 400:
                    raise EmbeddingProviderError(
                        f"OpenAI request failed {response.status_code}: {response.text}"
                    )

                payload = response.json()
                data = payload.get("data")
                if not isinstance(data, list):
                    raise EmbeddingProviderError("Invalid embeddings response: missing data list")

                vectors = []
                for item in data:
                    embedding = item.get("embedding") if isinstance(item, dict) else None
                    if not isinstance(embedding, list) or not embedding:
                        raise EmbeddingProviderError(
                            "Invalid embeddings response: empty or missing embedding"
                        )
                    vectors.append(embedding)

                if len(vectors) != len(batch):
                    raise EmbeddingProviderError(
                        "OpenAI embeddings count mismatch with input batch size"
                    )
                return vectors
            except httpx.HTTPError as exc:
                if attempt == self._max_retries:
                    raise EmbeddingProviderError(
                        f"OpenAI connection error after retries: {exc}"
                    ) from exc
                self._sleep_backoff(attempt)
        raise EmbeddingProviderError("OpenAI embedding request failed unexpectedly")

    def _sleep_backoff(self, attempt: int) -> None:
        delay = self._retry_base_seconds * (2**attempt)
        sleep(delay)
