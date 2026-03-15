from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import sys

import pytest

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.config import Settings  # noqa: E402
from app.exceptions import InvalidUserStateException, UserAlreadyExistsException  # noqa: E402
from app.service import AuthService  # noqa: E402
import app.database as database_module  # noqa: E402


def _make_user(**overrides):
    defaults = dict(
        id="user-1",
        email="user@example.com",
        user_metadata={"role": "user"},
        app_metadata={},
        created_at="2026-01-01T00:00:00+00:00",
        email_confirmed_at="2026-01-01T00:00:00+00:00",
        last_sign_in_at="",
        banned_until=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


@patch.object(database_module, "create_client", return_value=MagicMock())
def test_map_admin_user_marks_incomplete_invite_as_invited(mock_create: MagicMock) -> None:
    service = AuthService(Settings())

    invited_user = _make_user(
        app_metadata={
            "account_validated": True,
            "account_blocked": False,
            "invited_by_admin": True,
            "invited_at": "2026-03-10T00:00:00+00:00",
        },
        user_metadata={
            "role": "user",
            "invite_onboarding_completed": False,
        },
    )

    mapped = service._map_admin_user(invited_user)

    assert mapped["status"] == "invited"
    assert mapped["invited"] is True
    assert mapped["validated"] is False


@patch.object(database_module, "create_client", return_value=MagicMock())
def test_map_admin_user_marks_recovery_completed_invite_as_validated(
    mock_create: MagicMock,
) -> None:
    service = AuthService(Settings())

    invited_user = _make_user(
        app_metadata={
            "account_validated": True,
            "account_blocked": False,
            "invited_by_admin": True,
            "invited_at": "2026-03-10T00:00:00+00:00",
        },
        user_metadata={
            "role": "user",
            "invite_onboarding_completed": False,
        },
        last_sign_in_at="2026-03-10T01:00:00+00:00",
    )

    mapped = service._map_admin_user(invited_user)

    assert mapped["status"] == "validated"
    assert mapped["invited"] is False
    assert mapped["validated"] is True


@patch.object(database_module, "create_client", return_value=MagicMock())
def test_invite_user_refreshes_existing_invited_user_without_duplicate(
    mock_create: MagicMock,
) -> None:
    mock_client = mock_create.return_value
    admin_user = _make_user(id="admin-1", email="admin@example.com", user_metadata={"role": "admin"})
    existing_invited_user = _make_user(
        id="invited-1",
        email="invitee@example.com",
        app_metadata={
            "account_validated": True,
            "account_blocked": False,
            "invited_by_admin": True,
        },
        user_metadata={
            "role": "user",
            "username": "",
            "invite_onboarding_completed": False,
        },
    )

    mock_client.auth.get_user.return_value = SimpleNamespace(user=admin_user)
    mock_client.auth.admin.list_users.return_value = [existing_invited_user]
    mock_client.auth.admin.update_user_by_id.return_value = SimpleNamespace(user=existing_invited_user)

    service = AuthService(Settings())
    service._generate_password = MagicMock(return_value="TempPass1!")
    service._send_invite_email = MagicMock(return_value=(True, ""))

    result = service.invite_user("admin-token", "invitee@example.com")

    assert result["message"] == "Invitation refreshed"
    assert result["user_id"] == "invited-1"
    mock_client.auth.admin.create_user.assert_not_called()
    mock_client.auth.admin.update_user_by_id.assert_called_once()


@patch.object(database_module, "create_client", return_value=MagicMock())
def test_invite_user_finds_existing_invited_user_on_later_page(
    mock_create: MagicMock,
) -> None:
    mock_client = mock_create.return_value
    admin_user = _make_user(id="admin-1", email="admin@example.com", user_metadata={"role": "admin"})
    first_page_user = _make_user(id="user-1", email="someone@example.com")
    existing_invited_user = _make_user(
        id="invited-2",
        email="invitee@example.com",
        app_metadata={
            "account_validated": True,
            "account_blocked": False,
            "invited_by_admin": True,
        },
        user_metadata={
            "role": "user",
            "invite_onboarding_completed": False,
        },
    )

    mock_client.auth.get_user.return_value = SimpleNamespace(user=admin_user)
    mock_client.auth.admin.list_users.side_effect = [
        [first_page_user] * 200,
        [existing_invited_user],
    ]
    mock_client.auth.admin.update_user_by_id.return_value = SimpleNamespace(user=existing_invited_user)

    service = AuthService(Settings())
    service._generate_password = MagicMock(return_value="TempPass1!")
    service._send_invite_email = MagicMock(return_value=(True, ""))

    result = service.invite_user("admin-token", "invitee@example.com")

    assert result["message"] == "Invitation refreshed"
    assert mock_client.auth.admin.list_users.call_count == 2
    mock_client.auth.admin.create_user.assert_not_called()


@patch.object(database_module, "create_client", return_value=MagicMock())
def test_invite_user_rejects_existing_non_invited_user(mock_create: MagicMock) -> None:
    mock_client = mock_create.return_value
    admin_user = _make_user(id="admin-1", email="admin@example.com", user_metadata={"role": "admin"})
    existing_validated_user = _make_user(
        id="user-2",
        email="existing@example.com",
        app_metadata={
            "account_validated": True,
            "account_blocked": False,
            "invited_by_admin": False,
        },
        user_metadata={
            "role": "user",
            "invite_onboarding_completed": True,
        },
    )

    mock_client.auth.get_user.return_value = SimpleNamespace(user=admin_user)
    mock_client.auth.admin.list_users.return_value = [existing_validated_user]

    service = AuthService(Settings())

    with pytest.raises(UserAlreadyExistsException):
        service.invite_user("admin-token", "existing@example.com")


@patch.object(database_module, "create_client", return_value=MagicMock())
def test_set_user_validation_blocks_incomplete_invites(mock_create: MagicMock) -> None:
    mock_client = mock_create.return_value
    admin_user = _make_user(id="admin-1", email="admin@example.com", user_metadata={"role": "admin"})
    invited_user = _make_user(
        id="invited-1",
        email="invitee@example.com",
        app_metadata={
            "account_validated": True,
            "account_blocked": False,
            "invited_by_admin": True,
        },
        user_metadata={
            "role": "user",
            "invite_onboarding_completed": False,
        },
    )

    mock_client.auth.get_user.return_value = SimpleNamespace(user=admin_user)
    mock_client.auth.admin.get_user_by_id.return_value = SimpleNamespace(user=invited_user)

    service = AuthService(Settings())

    with pytest.raises(InvalidUserStateException):
        service.set_user_validation("admin-token", "invited-1", True)


@patch.object(database_module, "create_client", return_value=MagicMock())
@patch("app.service.smtplib.SMTP")
def test_send_invite_email_uses_recovery_link_in_smtp_message(
    mock_smtp: MagicMock,
    mock_create: MagicMock,
) -> None:
    service = AuthService(
        Settings(
            smtp_host="smtp.gmail.com",
            smtp_port=587,
            smtp_username="sender@example.com",
            smtp_password="secret",
            smtp_from_email="sender@example.com",
            smtp_from_name="ICC Agent Admin",
            frontend_url="http://localhost:5173",
        )
    )
    service._generate_recovery_link = MagicMock(return_value="https://example.com/set-password")

    sent_messages: list[object] = []
    smtp_instance = mock_smtp.return_value.__enter__.return_value
    smtp_instance.send_message.side_effect = lambda msg: sent_messages.append(msg)

    email_sent, recovery_link = service._send_invite_email("invitee@example.com", "TempPass1!")

    assert email_sent is True
    assert recovery_link == ""
    assert len(sent_messages) == 1
    message_text = sent_messages[0].get_content()
    assert "Welcome to ICC Agent." in message_text
    assert "To complete your sign up, please set your password" in message_text
    assert "https://example.com/set-password" in message_text
    assert "Temporary password" not in message_text


@patch.object(database_module, "create_client", return_value=MagicMock())
def test_send_invite_email_returns_generated_link_when_smtp_and_fallback_fail(
    mock_create: MagicMock,
) -> None:
    mock_client = mock_create.return_value
    mock_client.auth.reset_password_email.side_effect = Exception("delivery failed")

    service = AuthService(
        Settings(
            smtp_host="smtp.gmail.com",
            smtp_port=587,
            smtp_username="sender@example.com",
            smtp_password="secret",
            smtp_from_email="sender@example.com",
            smtp_from_name="ICC Agent Admin",
            frontend_url="http://localhost:5173",
        )
    )
    service._generate_recovery_link = MagicMock(return_value="https://example.com/set-password")

    with patch("app.service.smtplib.SMTP", side_effect=Exception("smtp failed")):
        email_sent, recovery_link = service._send_invite_email("invitee@example.com", "TempPass1!")

    assert email_sent is False
    assert recovery_link == "https://example.com/set-password"


@patch.object(database_module, "create_client", return_value=MagicMock())
def test_generate_recovery_link_reads_nested_properties_action_link(
    mock_create: MagicMock,
) -> None:
    mock_client = mock_create.return_value
    mock_client.auth.admin.generate_link.return_value = SimpleNamespace(
        properties=SimpleNamespace(action_link="https://example.com/set-password"),
        user=SimpleNamespace(action_link=""),
    )

    service = AuthService(Settings(frontend_url="http://localhost:5173"))

    link = service._generate_recovery_link("invitee@example.com", "http://localhost:5173/login")

    assert link == "https://example.com/set-password"
