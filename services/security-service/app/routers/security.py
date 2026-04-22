from fastapi import APIRouter, HTTPException, Request

from app.schemas import (
    LoginAttemptSummaryResponse,
    SecurityAlertResponse,
    SecurityAlertsResponse,
    SecurityEventCreate,
    SecuritySummaryResponse,
)
from app.service import SecurityService


router = APIRouter(prefix="/security", tags=["security"])


def _get_service(request: Request) -> SecurityService:
    return request.app.state.security_service


@router.get("/alerts", response_model=SecurityAlertsResponse)
def list_alerts(
    request: Request,
    include_resolved: bool = False,
) -> SecurityAlertsResponse:
    service = _get_service(request)
    alerts = service.list_alerts(include_resolved=include_resolved)
    summary = service.summary()
    return SecurityAlertsResponse(alerts=alerts, active_count=summary.active_alerts)


@router.get("/alerts/summary", response_model=SecuritySummaryResponse)
def alert_summary(request: Request) -> SecuritySummaryResponse:
    service = _get_service(request)
    return service.summary()


@router.get("/login-attempts/summary", response_model=LoginAttemptSummaryResponse)
def login_attempt_summary(request: Request) -> LoginAttemptSummaryResponse:
    service = _get_service(request)
    return service.get_login_attempt_summary()


@router.post("/events", response_model=SecurityAlertResponse, status_code=201)
def create_event(payload: SecurityEventCreate, request: Request) -> SecurityAlertResponse:
    service = _get_service(request)
    return service.record_event(payload)


@router.post("/alerts/{alert_id}/resolve", response_model=SecurityAlertResponse)
def resolve_alert(alert_id: str, request: Request) -> SecurityAlertResponse:
    service = _get_service(request)
    resolved = service.resolve_alert(alert_id)
    if resolved is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return resolved
