import httpx
from time import sleep

from app.errors import GenerationProviderError


class OpenAIChatClient:
    def __init__(
        self,
        api_key: str,
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
            base_url="https://api.openai.com/v1",
            timeout=timeout_seconds,
            trust_env=False,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )

    def complete_json(self, system_prompt: str, user_prompt: str) -> str:
        body = {
            "model": self._model,
            "temperature": self._temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        retryable_statuses = {429, 500, 502, 503, 504}
        last_error: Exception | None = None
        response: httpx.Response | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.post("/chat/completions", json=body)
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt < self._max_retries:
                    sleep(self._retry_base_seconds * (2**attempt))
                    continue
                raise GenerationProviderError(f"OpenAI chat request failed: {exc}") from exc

            if response.status_code < 400:
                break
            if response.status_code in retryable_statuses and attempt < self._max_retries:
                sleep(self._retry_base_seconds * (2**attempt))
                continue
            raise GenerationProviderError(
                f"OpenAI chat request failed {response.status_code}: {response.text}"
            )

        if response is None:
            raise GenerationProviderError(f"OpenAI chat request failed: {last_error}")

        payload = response.json()
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise GenerationProviderError("OpenAI chat response missing choices")

        first = choices[0]
        if not isinstance(first, dict):
            raise GenerationProviderError("OpenAI chat choice format invalid")

        message = first.get("message")
        if not isinstance(message, dict):
            raise GenerationProviderError("OpenAI chat message format invalid")

        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise GenerationProviderError("OpenAI chat content missing or empty")
        return content
