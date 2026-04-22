from __future__ import annotations

import json
from dataclasses import dataclass
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


class AdminAccessChecker:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

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

        endpoint = f"{self._settings.auth_base_url.rstrip('/')}/auth/me"
        req = request.Request(
            endpoint,
            headers={"Authorization": f"Bearer {token}"},
            method="GET",
        )
        try:
            with request.urlopen(req, timeout=1.5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            if exc.code == 401:
                raise AdminAccessDenied(401, "Invalid or expired token") from exc
            raise AdminAccessDenied(502, "Unable to validate admin access") from exc
        except (error.URLError, TimeoutError, ValueError) as exc:
            raise AdminAccessDenied(502, "Unable to validate admin access") from exc

        role = str(payload.get("role") or "")
        identity = AdminIdentity(
            user_id=str(payload.get("id") or ""),
            email=str(payload.get("email") or ""),
            role=role,
        )
        if role != "admin":
            raise AdminAccessDenied(403, "Admin access required")
        return identity
