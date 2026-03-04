import httpx
from time import sleep

from app.errors import GenerationProviderError


class OllamaChatClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        temperature: float,
        timeout_seconds: float,
        max_retries: int = 2,
        retry_base_seconds: float = 0.5,
    ) -> None:
        self._model = model
        self._temperature = temperature
        self._max_retries = max_retries
        self._retry_base_seconds = retry_base_seconds
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            trust_env=False,
        )

    def complete_json(self, system_prompt: str, user_prompt: str) -> str:
        body = {
            "model": self._model,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "options": {"temperature": self._temperature},
        }
        retryable_statuses = {429, 500, 502, 503, 504}
        last_error: Exception | None = None
        response: httpx.Response | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.post("/api/chat", json=body)
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt < self._max_retries:
                    sleep(self._retry_base_seconds * (2**attempt))
                    continue
                raise GenerationProviderError(f"Ollama chat request failed: {exc}") from exc

            if response.status_code < 400:
                break
            if response.status_code in retryable_statuses and attempt < self._max_retries:
                sleep(self._retry_base_seconds * (2**attempt))
                continue
            raise GenerationProviderError(
                f"Ollama chat request failed {response.status_code}: {response.text}"
            )

        if response is None:
            raise GenerationProviderError(f"Ollama chat request failed: {last_error}")

        payload = response.json()
        message = payload.get("message")
        if not isinstance(message, dict):
            raise GenerationProviderError("Ollama chat response missing message")

        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise GenerationProviderError("Ollama chat content missing or empty")
        return content
