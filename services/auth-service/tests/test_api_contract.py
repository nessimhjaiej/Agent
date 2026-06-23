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
import app.database as database_module  # noqa: E402


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


@patch.object(database_module, "create_client", return_value=MagicMock())
def test_signup_success(mock_create: MagicMock) -> None:
    mock_client = mock_create.return_value
    mock_user = _make_mock_supabase_user(app_metadata={})

    # Signup uses the admin API (no confirmation email), which returns no session.
    mock_client.auth.admin.create_user.return_value = SimpleNamespace(user=mock_user)
    mock_client.auth.admin.update_user_by_id.return_value = SimpleNamespace(user=mock_user)
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
    assert data["access_token"] == ""
    assert data["refresh_token"] == ""
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "new@example.com"
    assert data["user"]["role"] == "user"


@patch.object(database_module, "create_client", return_value=MagicMock())
def test_signup_returns_no_session(mock_create: MagicMock) -> None:
    """Admin-created signups are pending admin validation and carry no session."""
    mock_client = mock_create.return_value
    mock_user = _make_mock_supabase_user(email_confirmed_at=None, app_metadata={})

    mock_client.auth.admin.create_user.return_value = SimpleNamespace(user=mock_user)
    mock_client.auth.admin.update_user_by_id.return_value = SimpleNamespace(user=mock_user)
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
    assert data["access_token"] == ""  # no session until an admin validates
    assert data["user"]["email_confirmed"] is False


# ── Login ─────────────────────────────────────────────────────────────


@patch.object(database_module, "create_client", return_value=MagicMock())
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


@patch.object(database_module, "create_client", return_value=MagicMock())
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


@patch.object(database_module, "create_client", return_value=MagicMock())
def test_admin_users_requires_admin_role(mock_create: MagicMock) -> None:
    mock_client = mock_create.return_value
    mock_user = _make_mock_supabase_user(user_metadata={"role": "user"})
    mock_client.auth.get_user.return_value = SimpleNamespace(user=mock_user)

    app = create_app()
    client = TestClient(app)

    response = client.get(
        "/auth/admin/users",
        headers={"Authorization": "Bearer mock-token"},
    )

    assert response.status_code == 403


# ── Password reset ────────────────────────────────────────────────────


@patch.object(database_module, "create_client", return_value=MagicMock())
def test_password_reset_request(mock_create: MagicMock) -> None:
    mock_client = mock_create.return_value
    existing_user = _make_mock_supabase_user(
        email="user@example.com", user_metadata={"role": "user"}, app_metadata={}
    )
    mock_client.auth.admin.list_users.return_value = [existing_user]
    mock_client.auth.reset_password_email.return_value = None
    mock_client.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[])

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


@patch.object(database_module, "create_client", return_value=MagicMock())
def test_password_reset_admin_must_be_reinvited(mock_create: MagicMock) -> None:
    mock_client = mock_create.return_value
    admin_user = _make_mock_supabase_user(
        email="admin@example.com", user_metadata={"role": "admin"}, app_metadata={}
    )
    mock_client.auth.admin.list_users.return_value = [admin_user]

    app = create_app()
    client = TestClient(app)

    response = client.post("/auth/password-reset", json={"email": "admin@example.com"})

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert "invitation" in data["message"].lower()
    # No reset email is sent for admins.
    mock_client.auth.reset_password_email.assert_not_called()


@patch.object(database_module, "create_client", return_value=MagicMock())
def test_password_reset_unknown_email(mock_create: MagicMock) -> None:
    mock_client = mock_create.return_value
    mock_client.auth.admin.list_users.return_value = []

    app = create_app()
    client = TestClient(app)

    response = client.post("/auth/password-reset", json={"email": "ghost@example.com"})

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    mock_client.auth.reset_password_email.assert_not_called()
