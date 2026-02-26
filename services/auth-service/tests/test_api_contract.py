"""API contract tests for the auth-service endpoints.

Uses FastAPI TestClient. The Supabase Auth layer is mocked since these
are contract tests — they validate HTTP shape, status codes, and error
handling without requiring a live Supabase instance.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import sys
from types import SimpleNamespace

from fastapi.testclient import TestClient

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.main import create_app  # noqa: E402

# Patch Supabase create_client for all tests
_MOCK_DB = "app.database.create_client"


def _make_mock_supabase_user(**overrides):
    defaults = dict(
        id="test-uuid",
        email="new@example.com",
        email_confirmed_at="2026-01-01T00:00:00+00:00",
        user_metadata={"role": "user"},
        created_at="2026-01-01T00:00:00+00:00",
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_mock_session(**overrides):
    defaults = dict(
        access_token="mock-access-token",
        refresh_token="mock-refresh-token",
        token_type="bearer",
        expires_in=3600,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


# ── Health ────────────────────────────────────────────────────────────


def test_health_endpoint() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert "service" in payload
    assert "version" in payload


# ── Signup ────────────────────────────────────────────────────────────


@patch(_MOCK_DB, return_value=MagicMock())
def test_signup_success(mock_create: MagicMock) -> None:
    mock_client = mock_create.return_value
    mock_user = _make_mock_supabase_user()
    mock_session = _make_mock_session()

    mock_client.auth.sign_up.return_value = SimpleNamespace(
        user=mock_user,
        session=mock_session,
    )
    # Mock audit log (non-fatal)
    mock_client.table.return_value.insert.return_value.execute.return_value = MagicMock(
        data=[]
    )

    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/auth/signup",
        json={"email": "new@example.com", "password": "SecurePass1!", "role": "user"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "new@example.com"


@patch(_MOCK_DB, return_value=MagicMock())
def test_signup_email_confirmation(mock_create: MagicMock) -> None:
    """When email confirmation is enabled, session is None."""
    mock_client = mock_create.return_value
    mock_user = _make_mock_supabase_user(email_confirmed_at=None)

    mock_client.auth.sign_up.return_value = SimpleNamespace(
        user=mock_user,
        session=None,  # No session = needs email confirmation
    )
    mock_client.table.return_value.insert.return_value.execute.return_value = MagicMock(
        data=[]
    )

    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/auth/signup",
        json={"email": "new@example.com", "password": "SecurePass1!"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["access_token"] == ""  # No token until confirmed
    assert data["user"]["email_confirmed"] is False


# ── Login ─────────────────────────────────────────────────────────────


@patch(_MOCK_DB, return_value=MagicMock())
def test_login_success(mock_create: MagicMock) -> None:
    mock_client = mock_create.return_value
    mock_user = _make_mock_supabase_user()
    mock_session = _make_mock_session()

    mock_client.auth.sign_in_with_password.return_value = SimpleNamespace(
        user=mock_user,
        session=mock_session,
    )
    # Rate limiting: no failed attempts
    mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
        data=[]
    )
    # Audit log + login attempt recording
    mock_client.table.return_value.insert.return_value.execute.return_value = MagicMock(
        data=[]
    )

    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/auth/login",
        json={"email": "new@example.com", "password": "SecurePass1!"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["access_token"] == "mock-access-token"
    assert data["refresh_token"] == "mock-refresh-token"


def test_login_missing_fields() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.post("/auth/login", json={})
    assert response.status_code == 422  # Pydantic validation error


# ── Protected endpoints ───────────────────────────────────────────────


def test_me_endpoint_requires_auth() -> None:
    app = create_app()
    client = TestClient(app)

    response = client.get("/auth/me")
    assert response.status_code == 401


@patch(_MOCK_DB, return_value=MagicMock())
def test_me_returns_user(mock_create: MagicMock) -> None:
    mock_client = mock_create.return_value
    mock_user = _make_mock_supabase_user()
    mock_client.auth.get_user.return_value = SimpleNamespace(user=mock_user)

    app = create_app()
    client = TestClient(app)

    response = client.get(
        "/auth/me",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "new@example.com"
    assert data["email_confirmed"] is True


# ── Password reset ────────────────────────────────────────────────────


@patch(_MOCK_DB, return_value=MagicMock())
def test_password_reset_request(mock_create: MagicMock) -> None:
    mock_client = mock_create.return_value
    mock_client.auth.reset_password_email.return_value = None

    app = create_app()
    client = TestClient(app)

    response = client.post(
        "/auth/password-reset",
        json={"email": "user@example.com"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert "reset link" in data["message"].lower()
