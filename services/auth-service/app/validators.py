"""Password and email validation."""

import re


class PasswordValidator:
    """Validates password strength according to policy.

    Requirements:
        - Minimum 8 characters
        - At least 1 uppercase letter
        - At least 1 lowercase letter
        - At least 1 special character
    """

    MIN_LENGTH = 8
    SPECIAL_CHARS = r"!@#$%^&*()_+-=[]{}|;:,.<>?"

    @staticmethod
    def validate(password: str) -> tuple[bool, str]:
        """Return ``(is_valid, error_message)``."""
        if len(password) < PasswordValidator.MIN_LENGTH:
            return (
                False,
                f"Password must be at least {PasswordValidator.MIN_LENGTH} characters long",
            )

        if not re.search(r"[A-Z]", password):
            return False, "Password must contain at least 1 uppercase letter"

        if not re.search(r"[a-z]", password):
            return False, "Password must contain at least 1 lowercase letter"

        if not re.search(f"[{re.escape(PasswordValidator.SPECIAL_CHARS)}]", password):
            return (
                False,
                "Password must contain at least 1 special character (!@#$%^&*()_+-=[]{}|;:,.<>?)",
            )

        return True, ""


class EmailValidator:
    """Validates email format."""

    PATTERN = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"

    @staticmethod
    def validate(email: str) -> bool:
        return re.match(EmailValidator.PATTERN, email) is not None
