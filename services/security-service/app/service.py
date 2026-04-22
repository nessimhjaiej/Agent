from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4

from app.database import SecurityDatabase
from app.schemas import SecurityAlertResponse, SecurityEventCreate, SecuritySummaryResponse


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class AlertRecord:
    id: str
    fingerprint: str
    event_type: str
    source_service: str
    severity: str
    status: str
    title: str
    message: str
    count: int
    metadata: dict
    created_at: str
    last_seen_at: str


@dataclass(slots=True)
class SecurityService:
    recent_alert_limit: int = 25
    database: SecurityDatabase | None = None
    _alerts: list[AlertRecord] = field(default_factory=list)
    _lock: Lock = field(default_factory=Lock)

    def record_event(self, payload: SecurityEventCreate) -> SecurityAlertResponse:
        fingerprint = payload.fingerprint or self._build_fingerprint(payload)
        if self.database is not None and self.database.enabled:
            existing = self.database.get_active_alert_by_fingerprint(fingerprint)
            if existing is not None:
                return self.database.increment_security_alert(existing, payload)
            return self.database.create_security_alert(payload, fingerprint)

        with self._lock:
            existing = next(
                (
                    alert
                    for alert in self._alerts
                    if alert.fingerprint == fingerprint and alert.status == "active"
                ),
                None,
            )
            now = _utc_now()
            if existing:
                existing.count += 1
                existing.last_seen_at = now
                existing.severity = payload.severity
                existing.message = payload.message
                existing.metadata = payload.metadata
                return self._to_response(existing)

            alert = AlertRecord(
                id=str(uuid4()),
                fingerprint=fingerprint,
                event_type=payload.event_type,
                source_service=payload.source_service,
                severity=payload.severity,
                status="active",
                title=payload.title,
                message=payload.message,
                count=1,
                metadata=payload.metadata,
                created_at=now,
                last_seen_at=now,
            )
            self._alerts.insert(0, alert)
            return self._to_response(alert)

    def list_alerts(self, include_resolved: bool = False) -> list[SecurityAlertResponse]:
        if self.database is not None and self.database.enabled:
            return self.database.list_security_alerts(
                include_resolved=include_resolved,
                limit=self.recent_alert_limit,
            )

        with self._lock:
            alerts = self._alerts
            if not include_resolved:
                alerts = [alert for alert in alerts if alert.status == "active"]
            return [self._to_response(alert) for alert in alerts[: self.recent_alert_limit]]

    def resolve_alert(self, alert_id: str) -> SecurityAlertResponse | None:
        if self.database is not None and self.database.enabled:
            return self.database.resolve_security_alert(alert_id)

        with self._lock:
            alert = next((item for item in self._alerts if item.id == alert_id), None)
            if alert is None:
                return None
            alert.status = "resolved"
            alert.last_seen_at = _utc_now()
            return self._to_response(alert)

    def summary(self) -> SecuritySummaryResponse:
        if self.database is not None and self.database.enabled:
            return self.database.get_security_alert_summary()

        with self._lock:
            active = [alert for alert in self._alerts if alert.status == "active"]
            return SecuritySummaryResponse(
                active_alerts=len(active),
                critical_alerts=sum(1 for alert in active if alert.severity == "critical"),
                warning_alerts=sum(1 for alert in active if alert.severity == "warning"),
                info_alerts=sum(1 for alert in active if alert.severity == "info"),
            )

    def get_login_attempt_summary(self):
        if self.database is None:
            raise RuntimeError("Security database is not configured")
        return self.database.get_login_attempt_summary()

    def _build_fingerprint(self, payload: SecurityEventCreate) -> str:
        return "|".join(
            [
                payload.event_type.strip().lower(),
                payload.source_service.strip().lower(),
                payload.title.strip().lower(),
            ]
        )

    def _to_response(self, alert: AlertRecord) -> SecurityAlertResponse:
        return SecurityAlertResponse(
            id=alert.id,
            event_type=alert.event_type,
            source_service=alert.source_service,
            severity=alert.severity,
            status=alert.status,
            title=alert.title,
            message=alert.message,
            count=alert.count,
            metadata=alert.metadata,
            created_at=alert.created_at,
            last_seen_at=alert.last_seen_at,
        )
