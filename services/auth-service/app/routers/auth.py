"""Auth router for signup/login/password and admin user management."""

from fastapi import APIRouter, Header, HTTPException

from app.config import Settings
from app.exceptions import (
    AccountLockedException,
    AuthServiceException,
    InvalidCredentialsException,
    InvalidEmailException,
    InvalidPasswordException,
    InvalidUserStateException,
    UnauthorizedException,
    UserAlreadyExistsException,
)
from app.models import AuthUser
from app.schemas import (
    AdminBlockRequest,
    AdminInviteRequest,
    AdminInviteResponse,
    AdminUserResponse,
    AdminUsersResponse,
    AdminValidationRequest,
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
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401, detail="Missing or invalid Authorization header"
        )
    return authorization[7:]


def _get_current_user(authorization: str | None) -> AuthUser:
    token = _extract_token(authorization)
    service = _get_service()
    try:
        return service.get_current_user(token)
    except UnauthorizedException:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


@router.post("/signup", response_model=SessionResponse)
def signup(payload: SignupRequest) -> SessionResponse:
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
    service = _get_service()
    try:
        session = service.login(payload.email, payload.password)
    except AccountLockedException as exc:
        raise HTTPException(status_code=429, detail=str(exc))
    except InvalidCredentialsException as exc:
        raise HTTPException(status_code=401, detail=str(exc))
    except UnauthorizedException as exc:
        raise HTTPException(status_code=403, detail=str(exc))

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
    token = _extract_token(authorization)
    service = _get_service()
    try:
        service.update_password(token, payload.new_password)
    except InvalidPasswordException as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return MessageResponse(success=True, message="Password updated successfully.")


@router.get("/me", response_model=UserResponse)
def me(authorization: str | None = Header(default=None)) -> UserResponse:
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
    _extract_token(authorization)
    service = _get_service()
    service.logout()
    return MessageResponse(success=True, message="Logged out successfully.")


@router.get("/admin/users", response_model=AdminUsersResponse)
def list_users(authorization: str | None = Header(default=None)) -> AdminUsersResponse:
    token = _extract_token(authorization)
    service = _get_service()
    try:
        users = service.list_users(token)
    except UnauthorizedException as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except AuthServiceException as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return AdminUsersResponse(users=[AdminUserResponse(**user) for user in users])


@router.post("/admin/invite", response_model=AdminInviteResponse)
def invite_user(
    payload: AdminInviteRequest,
    authorization: str | None = Header(default=None),
) -> AdminInviteResponse:
    token = _extract_token(authorization)
    service = _get_service()
    try:
        result = service.invite_user(token, payload.email, payload.role)
    except UnauthorizedException as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except UserAlreadyExistsException as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except InvalidUserStateException as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except InvalidEmailException as exc:
        raise HTTPException(status_code=400, detail=f"Email error: {exc}")
    except AuthServiceException as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return AdminInviteResponse(**result)


@router.post("/admin/users/{user_id}/validate", response_model=AdminUserResponse)
def set_validation_status(
    user_id: str,
    payload: AdminValidationRequest,
    authorization: str | None = Header(default=None),
) -> AdminUserResponse:
    token = _extract_token(authorization)
    service = _get_service()
    try:
        updated = service.set_user_validation(token, user_id, payload.validated)
    except UnauthorizedException as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except InvalidUserStateException as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except AuthServiceException as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return AdminUserResponse(**updated)


@router.post("/admin/users/{user_id}/block", response_model=AdminUserResponse)
def set_block_status(
    user_id: str,
    payload: AdminBlockRequest,
    authorization: str | None = Header(default=None),
) -> AdminUserResponse:
    token = _extract_token(authorization)
    service = _get_service()
    try:
        updated = service.set_user_block(token, user_id, payload.blocked)
    except UnauthorizedException as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except AuthServiceException as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return AdminUserResponse(**updated)


@router.delete("/admin/users/{user_id}", response_model=MessageResponse)
def delete_user(
    user_id: str,
    authorization: str | None = Header(default=None),
) -> MessageResponse:
    token = _extract_token(authorization)
    service = _get_service()
    try:
        service.delete_user(token, user_id)
    except UnauthorizedException as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except AuthServiceException as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    return MessageResponse(success=True, message="User deleted successfully.")
