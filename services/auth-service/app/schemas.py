"""Pydantic schemas for the auth-service API layer."""

from pydantic import BaseModel, Field


# ── Requests ──────────────────────────────────────────────────────────


class SignupRequest(BaseModel):
    email: str = Field(..., min_length=1)
    password: str = Field(..., min_length=6)
    role: str = Field(default="user", pattern=r"^(user|admin)$")


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class PasswordResetRequest(BaseModel):
    email: str = Field(..., min_length=1)


class PasswordUpdateRequest(BaseModel):
    new_password: str = Field(..., min_length=6)


# ── Responses ─────────────────────────────────────────────────────────


class UserResponse(BaseModel):
    id: str
    email: str
    role: str
    email_confirmed: bool
    created_at: str


class SessionResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class MessageResponse(BaseModel):
    success: bool
    message: str


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str
    version: str
