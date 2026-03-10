import httpx

from app.clients.base_client import BaseHttpClient
from app.config import Settings
from app.errors import AuthorizationError, UpstreamServiceError


class AuthClient(BaseHttpClient):
    def __init__(self, settings: Settings) -> None:
        super().__init__(base_url=settings.auth_base_url, timeout_seconds=settings.http_timeout_seconds)
        self._supabase_url = settings.auth_supabase_url.rstrip("/")
        self._supabase_key = settings.auth_supabase_key

    def health(self) -> dict:
        return self._get_json("/health")

    def require_admin(self, access_token: str) -> dict:
        if self._supabase_url and self._supabase_key:
            return self._require_admin_via_supabase(access_token)
        return self._require_admin_via_auth_service(access_token)

    def _require_admin_via_supabase(self, access_token: str) -> dict:
        try:
            response = httpx.get(
                f"{self._supabase_url}/auth/v1/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "apikey": self._supabase_key,
                },
                timeout=self._client.timeout,
                trust_env=False,
            )
        except httpx.HTTPError as exc:
            raise UpstreamServiceError(f"HTTP request failed for Supabase auth user lookup: {exc}") from exc

        if response.status_code == 401:
            raise AuthorizationError("Invalid or expired token")
        if response.status_code >= 400:
            raise UpstreamServiceError(
                f"Supabase auth user lookup failed {response.status_code}: {response.text}"
            )

        payload = response.json()
        if not isinstance(payload, dict):
            raise UpstreamServiceError("Supabase auth user lookup returned invalid JSON object")

        user_metadata = payload.get("user_metadata", {})
        if not isinstance(user_metadata, dict):
            user_metadata = {}
        role = str(user_metadata.get("role", "")).strip().lower()
        if role != "admin":
            raise AuthorizationError("Admin access required")
        return {
            "id": str(payload.get("id", "")),
            "email": str(payload.get("email", "")),
            "role": role,
        }

    def _require_admin_via_auth_service(self, access_token: str) -> dict:
        try:
            response = self._client.get(
                "/auth/me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        except httpx.HTTPError as exc:
            raise UpstreamServiceError(f"HTTP request failed for GET /auth/me: {exc}") from exc
        if response.status_code == 401:
            raise AuthorizationError("Invalid or expired token")
        if response.status_code == 403:
            raise AuthorizationError("Admin access required")
        if response.status_code >= 400:
            raise UpstreamServiceError(f"GET /auth/me failed {response.status_code}: {response.text}")
        payload = response.json()
        if not isinstance(payload, dict):
            raise UpstreamServiceError("GET /auth/me returned invalid JSON object")
        role = str(payload.get("role", "")).strip().lower()
        if role != "admin":
            raise AuthorizationError("Admin access required")
        return {
            "id": str(payload.get("id", "")),
            "email": str(payload.get("email", "")),
            "role": role,
        }
