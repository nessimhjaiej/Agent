import httpx

from app.errors import UpstreamServiceError


class BaseHttpClient:
    def __init__(self, base_url: str, timeout_seconds: float) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            trust_env=False,
        )

    def _get_json(self, path: str, headers: dict | None = None) -> dict:
        try:
            response = self._client.get(path, headers=headers)
        except httpx.HTTPError as exc:
            raise UpstreamServiceError(f"HTTP request failed for GET {path}: {exc}") from exc
        if response.status_code >= 400:
            raise UpstreamServiceError(f"GET {path} failed {response.status_code}: {response.text}")
        payload = response.json()
        if not isinstance(payload, dict):
            raise UpstreamServiceError(f"GET {path} returned invalid JSON object")
        return payload

    def _post_json(self, path: str, body: dict, headers: dict | None = None) -> dict:
        try:
            response = self._client.post(path, json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise UpstreamServiceError(f"HTTP request failed for POST {path}: {exc}") from exc
        if response.status_code >= 400:
            raise UpstreamServiceError(f"POST {path} failed {response.status_code}: {response.text}")
        payload = response.json()
        if not isinstance(payload, dict):
            raise UpstreamServiceError(f"POST {path} returned invalid JSON object")
        return payload
