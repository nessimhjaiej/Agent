"""Unit tests for password and email validators."""

from pathlib import Path
import sys

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from app.validators import EmailValidator, PasswordValidator  # noqa: E402


# ── Password validation ──────────────────────────────────────────────


def test_valid_password() -> None:
    is_valid, msg = PasswordValidator.validate("Secure1!")
    assert is_valid is True
    assert msg == ""


def test_password_too_short() -> None:
    is_valid, msg = PasswordValidator.validate("Ab1!")
    assert is_valid is False
    assert "8 characters" in msg


def test_password_missing_uppercase() -> None:
    is_valid, msg = PasswordValidator.validate("abcdefg1!")
    assert is_valid is False
    assert "uppercase" in msg


def test_password_missing_lowercase() -> None:
    is_valid, msg = PasswordValidator.validate("ABCDEFG1!")
    assert is_valid is False
    assert "lowercase" in msg


def test_password_missing_special_char() -> None:
    is_valid, msg = PasswordValidator.validate("Abcdefg1")
    assert is_valid is False
    assert "special" in msg


def test_strong_password() -> None:
    is_valid, msg = PasswordValidator.validate("MyP@ssw0rd!2024")
    assert is_valid is True


# ── Email validation ─────────────────────────────────────────────────


def test_valid_email() -> None:
    assert EmailValidator.validate("user@example.com") is True


def test_invalid_email_no_at() -> None:
    assert EmailValidator.validate("userexample.com") is False


def test_invalid_email_no_domain() -> None:
    assert EmailValidator.validate("user@") is False


def test_invalid_email_no_tld() -> None:
    assert EmailValidator.validate("user@example") is False


def test_valid_email_with_dots() -> None:
    assert EmailValidator.validate("first.last@example.co.uk") is True
