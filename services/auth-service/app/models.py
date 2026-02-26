"""Domain models for auth service."""

from dataclasses import dataclass, field
from datetime import datetime, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class AuthUser:
    """User model mapped from Supabase Auth response."""

    id: str
    email: str
    role: str = "user"
    email_confirmed: bool = False
    created_at: str = field(default_factory=utc_now_iso)


@dataclass(slots=True)
class AuthSession:
    """Session model from Supabase Auth."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 3600
    user: AuthUser | None = None
