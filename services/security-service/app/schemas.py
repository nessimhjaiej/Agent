from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


Severity = Literal["info", "warning", "critical"]
AlertStatus = Literal["active", "resolved"]


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str


class SecurityEventCreate(BaseModel):
    event_type: str = Field(min_length=1)
    source_service: str = Field(min_length=1)
    severity: Severity
    title: str = Field(min_length=1)
    message: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    fingerprint: str | None = None


class SecurityAlertResponse(BaseModel):
    id: str
    event_type: str
    source_service: str
    severity: Severity
    status: AlertStatus
    title: str
    message: str
    count: int
    metadata: dict[str, Any]
    created_at: str
    last_seen_at: str


class SecurityAlertsResponse(BaseModel):
    alerts: list[SecurityAlertResponse]
    active_count: int


class SecuritySummaryResponse(BaseModel):
    active_alerts: int
    critical_alerts: int
    warning_alerts: int
    info_alerts: int


class LoginAttemptItemResponse(BaseModel):
    email: str
    success: bool
    timestamp: str


class LoginAttemptTargetResponse(BaseModel):
    email: str
    failed_attempts: int


class LoginAttemptSummaryResponse(BaseModel):
    enabled: bool
    window_hours: int
    total_attempts: int
    failed_attempts: int
    successful_attempts: int
    unique_emails: int
    recent_failed_attempts: list[LoginAttemptItemResponse]
    top_targeted_accounts: list[LoginAttemptTargetResponse]
