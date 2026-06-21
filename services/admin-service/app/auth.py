from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from time import time
from urllib import error, request

from app.config import Settings


class AdminAccessDenied(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(slots=True)
class AdminIdentity:
    user_id: str
    email: str
    role: str


# Process-wide cache of validated admin tokens. Every admin chat call previously
# re-validated the token against auth-service (which round-trips to Supabase); a
# slow round-trip inside the timeout budget surfaced as a 502. Caching successful
# validations for a short TTL removes that per-request dependency.
_VALIDATION_CACHE: dict[str, tuple[float, AdminIdentity]] = {}
_VALIDATION_CACHE_LOCK = threading.Lock()


class AdminAccessChecker:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _cache_get(self, token: str) -> AdminIdentity | None:
        ttl = float(getattr(self._settings, "auth_cache_ttl_seconds", 0.0) or 0.0)
        if ttl <= 0:
            return None
        with _VALIDATION_CACHE_LOCK:
            entry = _VALIDATION_CACHE.get(token)
            if entry is None:
                return None
            cached_at, identity = entry
            if time() - cached_at > ttl:
                _VALIDATION_CACHE.pop(token, None)
                return None
            return identity

    def _cache_put(self, token: str, identity: AdminIdentity) -> None:
        ttl = float(getattr(self._settings, "auth_cache_ttl_seconds", 0.0) or 0.0)
        if ttl <= 0:
            return
        with _VALIDATION_CACHE_LOCK:
            _VALIDATION_CACHE[token] = (time(), identity)

    def _fetch_identity(self, token: str) -> AdminIdentity:
        endpoint = f"{self._settings.auth_base_url.rstrip('/')}/auth/me"
        req = request.Request(
            endpoint,
            headers={"Authorization": f"Bearer {token}"},
            method="GET",
        )
        # Retry once on a transient network/timeout failure before giving up, so a
        # single slow auth round-trip does not fail the whole admin request.
        attempts = 2
        last_exc: Exception | None = None
        for attempt in range(attempts):
            try:
                with request.urlopen(
                    req, timeout=self._settings.auth_validation_timeout_seconds
                ) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                break
            except error.HTTPError as exc:
                # An auth decision (e.g. 401) is definitive; do not retry it.
                if exc.code == 401:
                    raise AdminAccessDenied(401, "Invalid or expired token") from exc
                last_exc = exc
            except (error.URLError, TimeoutError, ValueError) as exc:
                last_exc = exc
        else:
            raise AdminAccessDenied(502, "Unable to validate admin access") from last_exc

        role = str(payload.get("role") or "")
        identity = AdminIdentity(
            user_id=str(payload.get("id") or ""),
            email=str(payload.get("email") or ""),
            role=role,
        )
        if role != "admin":
            raise AdminAccessDenied(403, "Admin access required")
        return identity

    def require_admin(
        self,
        *,
        token: str | None,
        path: str,
        method: str,
        client_ip: str,
    ) -> AdminIdentity:
        if not token:
            raise AdminAccessDenied(401, "Missing admin access token")
        if not self._settings.auth_base_url:
            raise AdminAccessDenied(500, "Admin auth backend is not configured")

        cached = self._cache_get(token)
        if cached is not None:
            return cached

        identity = self._fetch_identity(token)
        self._cache_put(token, identity)
        return identity
