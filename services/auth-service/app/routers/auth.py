"""Auth router — signup, login, password reset, user info.

All authentication is delegated to Supabase built-in Auth.
Signup sends a verification email automatically.
"""

from fastapi import APIRouter, Header, HTTPException

from app.config import Settings
from app.exceptions import (
    AccountLockedException,
    AuthServiceException,
    InvalidCredentialsException,
    InvalidEmailException,
    InvalidPasswordException,
    UnauthorizedException,
    UserAlreadyExistsException,
)
from app.models import AuthUser
from app.schemas import (
    LoginRequest,
    MessageResponse,
    PasswordResetRequest,
    PasswordUpdateRequest,
    SessionResponse,
    SignupRequest,
    UserResponse,
)
from app.service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def _get_service() -> AuthService:
    return AuthService(Settings.from_env())


def _extract_token(authorization: str | None) -> str:
    """Extract JWT from 'Bearer <token>' header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401, detail="Missing or invalid Authorization header"
        )
    return authorization[7:]


def _get_current_user(authorization: str | None) -> AuthUser:
    """Dependency: extract and verify JWT, return AuthUser."""
    token = _extract_token(authorization)
    service = _get_service()
    try:
        return service.get_current_user(token)
    except UnauthorizedException:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# ── Public endpoints ──────────────────────────────────────────────────


@router.post("/signup", response_model=SessionResponse)
def signup(payload: SignupRequest) -> SessionResponse:
    """Register a new user.

    Supabase will send a **verification email** automatically.
    The user must confirm their email before they can log in.

    - **email**: Valid email address
    - **password**: Min 6 characters
    - **role**: ``user`` (default) or ``admin``
    """
    service = _get_service()
    try:
        session = service.signup(payload.email, payload.password, payload.role)
    except UserAlreadyExistsException as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except InvalidPasswordException as exc:
        raise HTTPException(status_code=400, detail=f"Password error: {exc}")
    except InvalidEmailException as exc:
        raise HTTPException(status_code=400, detail=f"Email error: {exc}")
    except AuthServiceException as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return SessionResponse(
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        token_type=session.token_type,
        expires_in=session.expires_in,
        user=UserResponse(
            id=session.user.id if session.user else "",
            email=session.user.email if session.user else payload.email,
            role=session.user.role if session.user else payload.role,
            email_confirmed=session.user.email_confirmed if session.user else False,
            created_at=session.user.created_at if session.user else "",
        ),
    )


@router.post("/login", response_model=SessionResponse)
def login(payload: LoginRequest) -> SessionResponse:
    """Login with email and password.

    Returns access and refresh tokens.
    Only works after the user has **confirmed their email**.
    """
    service = _get_service()
    try:
        session = service.login(payload.email, payload.password)
    except AccountLockedException as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except InvalidCredentialsException as exc:
        raise HTTPException(status_code=401, detail=str(exc))

    return SessionResponse(
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        token_type=session.token_type,
        expires_in=session.expires_in,
        user=UserResponse(
            id=session.user.id if session.user else "",
            email=session.user.email if session.user else payload.email,
            role=session.user.role if session.user else "",
            email_confirmed=session.user.email_confirmed if session.user else False,
            created_at=session.user.created_at if session.user else "",
        ),
    )


@router.post("/password-reset", response_model=MessageResponse)
def request_password_reset(payload: PasswordResetRequest) -> MessageResponse:
    """Request a password reset email.

    Supabase will send an email with a reset link.
    """
    service = _get_service()
    try:
        service.request_password_reset(payload.email)
    except AuthServiceException as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return MessageResponse(
        success=True,
        message="If the email exists, a password reset link has been sent.",
    )


@router.post("/update-password", response_model=MessageResponse)
def update_password(
    payload: PasswordUpdateRequest,
    authorization: str | None = Header(default=None),
) -> MessageResponse:
    """Update password using a valid access token.

    Use the token from the reset email link or an active session.
    """
    token = _extract_token(authorization)
    service = _get_service()
    try:
        service.update_password(token, payload.new_password)
    except InvalidPasswordException as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return MessageResponse(success=True, message="Password updated successfully.")


# ── Protected endpoints ───────────────────────────────────────────────


@router.get("/me", response_model=UserResponse)
def me(authorization: str | None = Header(default=None)) -> UserResponse:
    """Get current authenticated user info."""
    user = _get_current_user(authorization)

    return UserResponse(
        id=user.id,
        email=user.email,
        role=user.role,
        email_confirmed=user.email_confirmed,
        created_at=user.created_at,
    )


@router.post("/logout", response_model=MessageResponse)
def logout(authorization: str | None = Header(default=None)) -> MessageResponse:
    """Sign out the current user."""
    _extract_token(authorization)  # validate header format
    service = _get_service()
    service.logout()
    return MessageResponse(success=True, message="Logged out successfully.")
