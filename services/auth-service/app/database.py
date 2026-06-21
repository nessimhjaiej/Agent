"""Supabase client wrapper — uses Supabase built-in Auth + custom audit tables."""

from datetime import datetime, timezone
from typing import Any

from supabase import create_client

from app.config import Settings


class SupabaseClient:
    """Wrapper for Supabase operations — Auth + audit logging."""

    def __init__(self, settings: Settings) -> None:
        self._client = create_client(settings.supabase_url, settings.supabase_key)

    @property
    def auth(self):
        """Direct access to Supabase Auth client."""
        return self._client.auth

    # ── Audit & rate-limiting ─────────────────────────────────────────

    def log_audit(self, user_id: str, action: str, details: dict[str, Any]) -> bool:
        """Log audit trail entry."""
        response = (
            self._client.table("audit_logs")
            .insert(
                {
                    "user_id": user_id,
                    "action": action,
                    "details": details,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
            .execute()
        )
        return len(response.data) > 0

    def record_login_attempt(self, email: str, success: bool) -> None:
        """Record login attempt for rate-limiting.

        Best-effort: this is rate-limit telemetry, so a write failure (e.g. an
        RLS rejection while a rotated service-role key propagates) must never
        bubble up and turn a valid login into a 500. Mirrors log_audit below.
        """
        try:
            self._client.table("login_attempts").insert(
                {
                    "email": email,
                    "success": success,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ).execute()
        except Exception as exc:  # noqa: BLE001 - telemetry must not break auth
            print(f"[auth] record_login_attempt failed (non-fatal): {exc}")

    def get_failed_login_count(self, email: str, minutes: int = 15) -> int:
        """Get failed login attempts within the last N minutes."""
        from datetime import timedelta

        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()
        response = (
            self._client.table("login_attempts")
            .select("*")
            .eq("email", email)
            .eq("success", False)
            .gte("timestamp", cutoff)
            .execute()
        )
        return len(response.data) if response.data else 0
