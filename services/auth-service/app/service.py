"""Auth service — uses Supabase built-in Auth.

Supabase handles:
  - Password hashing & verification
  - JWT token creation & validation
  - Email verification (sends confirmation email on signup)
  - Password reset emails
"""

from app.config import Settings
from app.database import SupabaseClient
from app.exceptions import (
    AccountLockedException,
    AuthServiceException,
    InvalidCredentialsException,
    InvalidEmailException,
    InvalidPasswordException,
    UnauthorizedException,
    UserAlreadyExistsException,
    UserNotFoundException,
)
from app.models import AuthSession, AuthUser


class AuthService:
    """Authentication service using Supabase built-in Auth.

    Signup sends a confirmation email automatically.
    Login only works after email is confirmed.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._db = SupabaseClient(settings)

    # ── Helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _map_user(supabase_user) -> AuthUser:
        """Map Supabase auth user to our AuthUser model."""
        metadata = supabase_user.user_metadata or {}
        return AuthUser(
            id=supabase_user.id,
            email=supabase_user.email or "",
            role=metadata.get("role", "user"),
            email_confirmed=supabase_user.email_confirmed_at is not None,
            created_at=str(supabase_user.created_at)
            if supabase_user.created_at
            else "",
        )

    @staticmethod
    def _map_session(session, user: AuthUser) -> AuthSession:
        """Map Supabase auth session to our AuthSession model."""
        return AuthSession(
            access_token=session.access_token,
            refresh_token=session.refresh_token,
            token_type="bearer",
            expires_in=session.expires_in or 3600,
            user=user,
        )

    # ── Authentication ────────────────────────────────────────────────

    def signup(self, email: str, password: str, role: str = "user") -> AuthSession:
        """Register a new user via Supabase Auth.

        Supabase will automatically send a confirmation email.
        The user must confirm their email before they can log in.

        Returns:
            AuthSession with tokens and user info.

        Raises:
            UserAlreadyExistsException: If email is already taken.
            InvalidPasswordException: If password is too weak.
            AuthServiceException: For any other Supabase error.
        """
        try:
            response = self._db.auth.sign_up(
                {
                    "email": email,
                    "password": password,
                    "options": {
                        "data": {"role": role},
                    },
                }
            )
        except Exception as exc:
            error_msg = str(exc).lower()
            if (
                "already registered" in error_msg
                or "already been registered" in error_msg
            ):
                raise UserAlreadyExistsException(
                    "User with this email already exists"
                ) from exc
            if "password" in error_msg:
                raise InvalidPasswordException(str(exc)) from exc
            if "email" in error_msg:
                raise InvalidEmailException(str(exc)) from exc
            raise AuthServiceException(f"Signup failed: {exc}") from exc

        if not response.user:
            raise AuthServiceException("Signup failed: no user returned")

        user = self._map_user(response.user)

        # Log audit (may fail if audit_logs table doesn't exist yet — non-fatal)
        try:
            self._db.log_audit(user.id, "USER_SIGNUP", {"email": email, "role": role})
        except Exception:
            pass  # audit is best-effort

        # Supabase may or may not return a session depending on email confirmation settings
        if response.session:
            return self._map_session(response.session, user)

        # No session = email confirmation required
        return AuthSession(
            access_token="",
            refresh_token="",
            token_type="bearer",
            expires_in=0,
            user=user,
        )

    def login(self, email: str, password: str) -> AuthSession:
        """Authenticate user via Supabase Auth.

        Returns:
            AuthSession with tokens and user info.

        Raises:
            AccountLockedException: Too many failed attempts.
            InvalidCredentialsException: Bad email/password.
        """
        # Check rate limiting
        failed_attempts = self._db.get_failed_login_count(
            email, self._settings.lockout_duration_minutes
        )
        if failed_attempts >= self._settings.max_login_attempts:
            raise AccountLockedException(
                "Account locked due to too many failed login attempts"
            )

        try:
            response = self._db.auth.sign_in_with_password(
                {
                    "email": email,
                    "password": password,
                }
            )
        except Exception as exc:
            self._db.record_login_attempt(email, False)
            raise InvalidCredentialsException("Invalid email or password") from exc

        if not response.user or not response.session:
            self._db.record_login_attempt(email, False)
            raise InvalidCredentialsException("Invalid email or password")

        self._db.record_login_attempt(email, True)

        user = self._map_user(response.user)
        try:
            self._db.log_audit(user.id, "USER_LOGIN", {"email": email})
        except Exception:
            pass

        return self._map_session(response.session, user)

    # ── Session management ────────────────────────────────────────────

    def get_current_user(self, access_token: str) -> AuthUser:
        """Get the currently authenticated user from a JWT token.

        Raises:
            UnauthorizedException: If token is invalid/expired.
        """
        try:
            response = self._db.auth.get_user(access_token)
        except Exception as exc:
            raise UnauthorizedException("Invalid or expired token") from exc

        if not response.user:
            raise UnauthorizedException("Invalid or expired token")

        return self._map_user(response.user)

    def logout(self) -> bool:
        """Sign out the current user."""
        try:
            self._db.auth.sign_out()
            return True
        except Exception:
            return False

    # ── Password management ───────────────────────────────────────────

    def request_password_reset(self, email: str) -> bool:
        """Send a password reset email.

        Supabase sends an email with a reset link automatically.
        """
        try:
            self._db.auth.reset_password_email(email)
            return True
        except Exception as exc:
            raise AuthServiceException(f"Password reset failed: {exc}") from exc

    def update_password(self, access_token: str, new_password: str) -> bool:
        """Update password for the authenticated user.

        Requires a valid access token (from reset link or active session).
        """
        try:
            self._db.auth.update_user(
                jwt=access_token,
                attributes={"password": new_password},
            )
            return True
        except Exception as exc:
            raise InvalidPasswordException(f"Password update failed: {exc}") from exc

    # ── Authorization helpers ─────────────────────────────────────────

    @staticmethod
    def has_admin_role(user: AuthUser) -> bool:
        return user.role == "admin"

    @staticmethod
    def check_authorization(user: AuthUser, required_role: str) -> bool:
        if required_role == "admin":
            return user.role == "admin"
        if required_role == "user":
            return user.role in ("user", "admin")
        return False
