import httpx
from time import sleep

from app.errors import GenerationProviderError


class RetrievalClient:
    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
        max_retries: int = 2,
        retry_base_seconds: float = 0.5,
    ) -> None:
        self._max_retries = max_retries
        self._retry_base_seconds = retry_base_seconds
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            trust_env=False,
        )

    def search(self, payload: dict) -> dict:
        retryable_statuses = {429, 500, 502, 503, 504}
        response: httpx.Response | None = None
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.post("/retrieval/search", json=payload)
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt < self._max_retries:
                    sleep(self._retry_base_seconds * (2**attempt))
                    continue
                raise GenerationProviderError(f"Retrieval request failed: {exc}") from exc

            if response.status_code < 400:
                break
            if response.status_code in retryable_statuses and attempt < self._max_retries:
                sleep(self._retry_base_seconds * (2**attempt))
                continue
            raise GenerationProviderError(
                f"Retrieval request failed {response.status_code}: {response.text}"
            )

        if response is None:
            raise GenerationProviderError(f"Retrieval request failed: {last_error}")

        body = response.json()
        if not isinstance(body, dict):
            raise GenerationProviderError("Retrieval response format invalid")
        return body
