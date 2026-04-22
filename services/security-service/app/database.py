from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from supabase import create_client

from app.config import Settings
from app.schemas import (
    LoginAttemptItemResponse,
    LoginAttemptSummaryResponse,
    LoginAttemptTargetResponse,
    SecurityAlertResponse,
    SecurityEventCreate,
    SecuritySummaryResponse,
)


class SecurityDatabase:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = None
        if settings.supabase_url and settings.supabase_key:
            self._client = create_client(settings.supabase_url, settings.supabase_key)

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def get_active_alert_by_fingerprint(
        self,
        fingerprint: str,
    ) -> SecurityAlertResponse | None:
        if not self.enabled:
            return None

        response = (
            self._client.table("security_alerts")
            .select("*")
            .eq("fingerprint", fingerprint)
            .eq("status", "active")
            .limit(1)
            .execute()
        )
        rows = list(response.data or [])
        if not rows:
            return None
        return self._to_alert_response(rows[0])

    def create_security_alert(
        self,
        payload: SecurityEventCreate,
        fingerprint: str,
    ) -> SecurityAlertResponse:
        if not self.enabled:
            raise RuntimeError("Security database is not configured")

        now = datetime.now(timezone.utc).isoformat()
        response = (
            self._client.table("security_alerts")
            .insert(
                {
                    "fingerprint": fingerprint,
                    "event_type": payload.event_type,
                    "source_service": payload.source_service,
                    "severity": payload.severity,
                    "status": "active",
                    "title": payload.title,
                    "message": payload.message,
                    "count": 1,
                    "metadata": payload.metadata,
                    "created_at": now,
                    "last_seen_at": now,
                }
            )
            .execute()
        )
        rows = list(response.data or [])
        if not rows:
            raise RuntimeError("Security alert insert returned no rows")
        return self._to_alert_response(rows[0])

    def increment_security_alert(
        self,
        alert: SecurityAlertResponse,
        payload: SecurityEventCreate,
    ) -> SecurityAlertResponse:
        if not self.enabled:
            raise RuntimeError("Security database is not configured")

        response = (
            self._client.table("security_alerts")
            .update(
                {
                    "severity": payload.severity,
                    "message": payload.message,
                    "metadata": payload.metadata,
                    "count": int(alert.count) + 1,
                    "last_seen_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            .eq("id", alert.id)
            .execute()
        )
        rows = list(response.data or [])
        if not rows:
            raise RuntimeError("Security alert update returned no rows")
        return self._to_alert_response(rows[0])

    def list_security_alerts(
        self,
        *,
        include_resolved: bool,
        limit: int,
    ) -> list[SecurityAlertResponse]:
        if not self.enabled:
            return []

        query = self._client.table("security_alerts").select("*")
        if not include_resolved:
            query = query.eq("status", "active")
        response = query.order("last_seen_at", desc=True).limit(limit).execute()
        return [self._to_alert_response(row) for row in list(response.data or [])]

    def resolve_security_alert(self, alert_id: str) -> SecurityAlertResponse | None:
        if not self.enabled:
            return None

        response = (
            self._client.table("security_alerts")
            .update(
                {
                    "status": "resolved",
                    "last_seen_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            .eq("id", alert_id)
            .execute()
        )
        rows = list(response.data or [])
        if not rows:
            return None
        return self._to_alert_response(rows[0])

    def get_security_alert_summary(self) -> SecuritySummaryResponse:
        if not self.enabled:
            return SecuritySummaryResponse(
                active_alerts=0,
                critical_alerts=0,
                warning_alerts=0,
                info_alerts=0,
            )

        response = (
            self._client.table("security_alerts")
            .select("severity")
            .eq("status", "active")
            .limit(max(self._settings.recent_alert_limit * 10, 1000))
            .execute()
        )
        rows = list(response.data or [])
        return SecuritySummaryResponse(
            active_alerts=len(rows),
            critical_alerts=sum(1 for row in rows if row.get("severity") == "critical"),
            warning_alerts=sum(1 for row in rows if row.get("severity") == "warning"),
            info_alerts=sum(1 for row in rows if row.get("severity") == "info"),
        )

    def get_login_attempt_summary(self) -> LoginAttemptSummaryResponse:
        if not self.enabled:
            return LoginAttemptSummaryResponse(
                enabled=False,
                window_hours=self._settings.login_attempts_window_hours,
                total_attempts=0,
                failed_attempts=0,
                successful_attempts=0,
                unique_emails=0,
                recent_failed_attempts=[],
                top_targeted_accounts=[],
            )

        cutoff = (
            datetime.now(timezone.utc)
            - timedelta(hours=self._settings.login_attempts_window_hours)
        ).isoformat()
        response = (
            self._client.table("login_attempts")
            .select("email,success,timestamp")
            .gte("timestamp", cutoff)
            .order("timestamp", desc=True)
            .limit(self._settings.login_attempts_max_rows)
            .execute()
        )
        rows = list(response.data or [])
        failed_rows = [row for row in rows if row.get("success") is False]
        targeted_accounts = Counter(
            (str(row.get("email") or "").strip().lower() for row in failed_rows)
        )
        top_targeted_accounts = [
            LoginAttemptTargetResponse(email=email, failed_attempts=count)
            for email, count in targeted_accounts.most_common(5)
            if email
        ]
        recent_failed_attempts = [
            LoginAttemptItemResponse(
                email=str(row.get("email") or ""),
                success=bool(row.get("success")),
                timestamp=str(row.get("timestamp") or ""),
            )
            for row in failed_rows[:10]
        ]
        unique_emails = len(
            {
                str(row.get("email") or "").strip().lower()
                for row in rows
                if str(row.get("email") or "").strip()
            }
        )
        return LoginAttemptSummaryResponse(
            enabled=True,
            window_hours=self._settings.login_attempts_window_hours,
            total_attempts=len(rows),
            failed_attempts=len(failed_rows),
            successful_attempts=sum(1 for row in rows if row.get("success") is True),
            unique_emails=unique_emails,
            recent_failed_attempts=recent_failed_attempts,
            top_targeted_accounts=top_targeted_accounts,
        )

    def _to_alert_response(self, row: dict[str, Any]) -> SecurityAlertResponse:
        return SecurityAlertResponse(
            id=str(row.get("id") or ""),
            event_type=str(row.get("event_type") or ""),
            source_service=str(row.get("source_service") or ""),
            severity=str(row.get("severity") or "info"),
            status=str(row.get("status") or "active"),
            title=str(row.get("title") or ""),
            message=str(row.get("message") or ""),
            count=int(row.get("count") or 0),
            metadata=row.get("metadata") if isinstance(row.get("metadata"), dict) else {},
            created_at=str(row.get("created_at") or ""),
            last_seen_at=str(row.get("last_seen_at") or ""),
        )
