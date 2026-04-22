from pathlib import Path
import sys
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


def test_health_endpoint() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "security-service"


@patch("app.database.create_client", return_value=MagicMock())
def test_security_alert_lifecycle(mock_create) -> None:  # noqa: ANN001
    mock_client = mock_create.return_value
    table_mock = mock_client.table.return_value
    table_mock.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.side_effect = [
        MagicMock(data=[]),
        MagicMock(
            data=[
                {
                    "id": "alert-1",
                    "fingerprint": "rate-limit",
                    "event_type": "RATE_LIMIT_EXCEEDED",
                    "source_service": "preprocessing-service",
                    "severity": "warning",
                    "status": "active",
                    "title": "Rate limit exceeded",
                    "message": "Client exceeded request threshold.",
                    "count": 1,
                    "metadata": {"client_ip": "127.0.0.1"},
                    "created_at": "2026-04-21T08:00:00+00:00",
                    "last_seen_at": "2026-04-21T08:00:00+00:00",
                }
            ]
        ),
    ]
    table_mock.insert.return_value.execute.return_value = MagicMock(
        data=[
            {
                "id": "alert-1",
                "fingerprint": "rate-limit",
                "event_type": "RATE_LIMIT_EXCEEDED",
                "source_service": "preprocessing-service",
                "severity": "warning",
                "status": "active",
                "title": "Rate limit exceeded",
                "message": "Client exceeded request threshold.",
                "count": 1,
                "metadata": {"client_ip": "127.0.0.1"},
                "created_at": "2026-04-21T08:00:00+00:00",
                "last_seen_at": "2026-04-21T08:00:00+00:00",
            }
        ]
    )
    table_mock.update.return_value.eq.return_value.execute.side_effect = [
        MagicMock(
            data=[
                {
                    "id": "alert-1",
                    "fingerprint": "rate-limit",
                    "event_type": "RATE_LIMIT_EXCEEDED",
                    "source_service": "preprocessing-service",
                    "severity": "warning",
                    "status": "active",
                    "title": "Rate limit exceeded",
                    "message": "Client exceeded request threshold again.",
                    "count": 2,
                    "metadata": {"client_ip": "127.0.0.1"},
                    "created_at": "2026-04-21T08:00:00+00:00",
                    "last_seen_at": "2026-04-21T08:01:00+00:00",
                }
            ]
        ),
        MagicMock(
            data=[
                {
                    "id": "alert-1",
                    "fingerprint": "rate-limit",
                    "event_type": "RATE_LIMIT_EXCEEDED",
                    "source_service": "preprocessing-service",
                    "severity": "warning",
                    "status": "resolved",
                    "title": "Rate limit exceeded",
                    "message": "Client exceeded request threshold again.",
                    "count": 2,
                    "metadata": {"client_ip": "127.0.0.1"},
                    "created_at": "2026-04-21T08:00:00+00:00",
                    "last_seen_at": "2026-04-21T08:02:00+00:00",
                }
            ]
        ),
    ]
    table_mock.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[
            {
                "severity": "warning",
            }
        ]
    )
    table_mock.select.return_value.eq.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
        data=[
            {
                "id": "alert-1",
                "fingerprint": "rate-limit",
                "event_type": "RATE_LIMIT_EXCEEDED",
                "source_service": "preprocessing-service",
                "severity": "warning",
                "status": "active",
                "title": "Rate limit exceeded",
                "message": "Client exceeded request threshold again.",
                "count": 2,
                "metadata": {"client_ip": "127.0.0.1"},
                "created_at": "2026-04-21T08:00:00+00:00",
                "last_seen_at": "2026-04-21T08:01:00+00:00",
            }
        ]
    )
    client = TestClient(
        create_app(
            Settings(
                supabase_url="https://example.supabase.co",
                supabase_key="service-key",
            )
        )
    )

    create_response = client.post(
        "/security/events",
        json={
            "event_type": "RATE_LIMIT_EXCEEDED",
            "source_service": "preprocessing-service",
            "severity": "warning",
            "title": "Rate limit exceeded",
            "message": "Client exceeded request threshold.",
            "metadata": {"client_ip": "127.0.0.1"},
        },
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["count"] == 1

    duplicate_response = client.post(
        "/security/events",
        json={
            "event_type": "RATE_LIMIT_EXCEEDED",
            "source_service": "preprocessing-service",
            "severity": "warning",
            "title": "Rate limit exceeded",
            "message": "Client exceeded request threshold again.",
            "metadata": {"client_ip": "127.0.0.1"},
        },
    )

    assert duplicate_response.status_code == 201
    duplicated = duplicate_response.json()
    assert duplicated["count"] == 2

    list_response = client.get("/security/alerts")
    assert list_response.status_code == 200
    listed = list_response.json()
    assert listed["active_count"] == 1
    assert listed["alerts"][0]["title"] == "Rate limit exceeded"

    summary_response = client.get("/security/alerts/summary")
    assert summary_response.status_code == 200
    summary = summary_response.json()
    assert summary["warning_alerts"] == 1

    resolve_response = client.post(f"/security/alerts/{created['id']}/resolve")
    assert resolve_response.status_code == 200
    resolved = resolve_response.json()
    assert resolved["status"] == "resolved"


@patch("app.database.create_client", return_value=MagicMock())
def test_login_attempt_summary_from_supabase(mock_create) -> None:  # noqa: ANN001
    mock_client = mock_create.return_value
    rows = [
        {"email": "alice@example.com", "success": False, "timestamp": "2026-04-21T08:00:00+00:00"},
        {"email": "alice@example.com", "success": False, "timestamp": "2026-04-21T07:59:00+00:00"},
        {"email": "bob@example.com", "success": True, "timestamp": "2026-04-21T07:58:00+00:00"},
    ]
    mock_client.table.return_value.select.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
        data=rows
    )
    app = create_app(
        Settings(
            supabase_url="https://example.supabase.co",
            supabase_key="service-key",
        )
    )
    client = TestClient(app)

    response = client.get("/security/login-attempts/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["enabled"] is True
    assert payload["total_attempts"] == 3
    assert payload["failed_attempts"] == 2
    assert payload["successful_attempts"] == 1
    assert payload["top_targeted_accounts"][0]["email"] == "alice@example.com"
    assert payload["top_targeted_accounts"][0]["failed_attempts"] == 2
