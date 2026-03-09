import httpx
from time import sleep

from app.errors import GenerationProviderError


class OpenAIAudioClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        timeout_seconds: float,
        max_retries: int = 2,
        retry_base_seconds: float = 0.5,
    ) -> None:
        self._model = model
        self._max_retries = max_retries
        self._retry_base_seconds = retry_base_seconds
        self._client = httpx.Client(
            base_url="https://api.openai.com/v1",
            timeout=timeout_seconds,
            trust_env=False,
            headers={"Authorization": f"Bearer {api_key}"},
        )

    def transcribe(
        self,
        filename: str,
        content: bytes,
        content_type: str = "application/octet-stream",
        language: str | None = None,
        prompt: str | None = None,
    ) -> str:
        data = {
            "model": self._model,
            "response_format": "json",
        }
        if language:
            data["language"] = language
        if prompt:
            data["prompt"] = prompt

        retryable_statuses = {429, 500, 502, 503, 504}
        last_error: Exception | None = None
        response: httpx.Response | None = None
        files = {"file": (filename, content, content_type)}

        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.post("/audio/transcriptions", data=data, files=files)
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt < self._max_retries:
                    sleep(self._retry_base_seconds * (2**attempt))
                    continue
                raise GenerationProviderError(f"OpenAI transcription request failed: {exc}") from exc

            if response.status_code < 400:
                break
            if response.status_code in retryable_statuses and attempt < self._max_retries:
                sleep(self._retry_base_seconds * (2**attempt))
                continue
            raise GenerationProviderError(
                f"OpenAI transcription request failed {response.status_code}: {response.text}"
            )

        if response is None:
            raise GenerationProviderError(f"OpenAI transcription request failed: {last_error}")

        payload = response.json()
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            raise GenerationProviderError("OpenAI transcription response missing text")
        return text.strip()
