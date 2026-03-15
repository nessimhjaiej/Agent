"""Pydantic schemas for the auth-service API layer."""

from pydantic import BaseModel, Field


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
