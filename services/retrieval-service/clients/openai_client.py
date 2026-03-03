import httpx

from app.errors import RetrievalProviderError


class OpenAIClient:
    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        dimensions: int | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        self._model = model
        self._dimensions = dimensions
        self._client = httpx.Client(
            base_url="https://api.openai.com/v1",
            timeout=timeout_seconds,
            trust_env=False,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

    def embed_query(self, query: str) -> list[float]:
        body: dict[str, object] = {"model": self._model, "input": query}
        if self._dimensions is not None:
            body["dimensions"] = self._dimensions

        try:
            response = self._client.post("/embeddings", json=body)
        except httpx.HTTPError as exc:
            raise RetrievalProviderError(f"OpenAI embedding request failed: {exc}") from exc

        if response.status_code >= 400:
            raise RetrievalProviderError(
                f"OpenAI embedding request failed {response.status_code}: {response.text}"
            )

        payload = response.json()
        data = payload.get("data")
        if not isinstance(data, list) or not data:
            raise RetrievalProviderError("OpenAI embedding response missing data")
        first = data[0]
        if not isinstance(first, dict):
            raise RetrievalProviderError("OpenAI embedding response item format invalid")

        embedding = first.get("embedding")
        if not isinstance(embedding, list) or not embedding:
            raise RetrievalProviderError("OpenAI embedding vector missing or empty")
        return embedding
