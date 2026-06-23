"""Pydantic schemas for the auth-service API layer."""

from pydantic import BaseModel, Field


class SignupRequest(BaseModel):
    email: str = Field(..., min_length=1)
    password: str = Field(..., min_length=6)
    role: str = Field(default="user", pattern=r"^(user|admin)$")
    username: str | None = None
    phone_number: str | None = None


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class PasswordResetRequest(BaseModel):
    email: str = Field(..., min_length=1)


class PasswordUpdateRequest(BaseModel):
    new_password: str = Field(..., min_length=6)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1)


class UpdateProfileRequest(BaseModel):
    username: str | None = None
    phone_number: str | None = None
    profile_picture: str | None = None
    invite_onboarding_completed: bool | None = None
    new_password: str | None = Field(default=None, min_length=6)


class AdminInviteRequest(BaseModel):
    email: str = Field(..., min_length=1)
    role: str = Field(default="user", pattern=r"^(user|admin)$")


class AdminValidationRequest(BaseModel):
    validated: bool


class AdminBlockRequest(BaseModel):
    blocked: bool


class UserResponse(BaseModel):
    id: str
    email: str
    role: str
    email_confirmed: bool
    created_at: str


class CurrentUserResponse(BaseModel):
    """Full self-profile for the frontend (mirrors the Supabase user shape).

    Keeps id/email/role at the top level so the admin-service token check
    (which reads those from /auth/me) stays compatible, and adds the metadata
    the UI needs now that it no longer calls Supabase directly.
    """

    id: str
    email: str
    role: str
    email_confirmed: bool
    created_at: str
    user_metadata: dict = {}
    app_metadata: dict = {}


class SessionResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class MessageResponse(BaseModel):
    success: bool
    message: str


class AdminUserResponse(BaseModel):
    id: str
    email: str
    username: str = ""
    phone_number: str = ""
    profile_picture: str = ""
    role: str
    created_at: str
    email_confirmed: bool
    validated: bool
    blocked: bool
    invited: bool
    status: str
    invited_at: str = ""
    last_sign_in_at: str = ""


class AdminUsersResponse(BaseModel):
    users: list[AdminUserResponse]


class AdminInviteResponse(BaseModel):
    success: bool
    message: str
    user_id: str
    email: str
    generated_password: str
    email_sent: bool
    recovery_link: str = ""


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str
    version: str
