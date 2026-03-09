"""Auth service using Supabase built-in Auth."""

from __future__ import annotations

import secrets
import smtplib
import string
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any

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
)
from app.models import AuthSession, AuthUser


class AuthService:
    """Authentication service using Supabase built-in Auth."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._db = SupabaseClient(settings)

    @staticmethod
    def _map_user(supabase_user) -> AuthUser:
        metadata = supabase_user.user_metadata or {}
        return AuthUser(
            id=supabase_user.id,
            email=supabase_user.email or "",
            role=metadata.get("role", "user"),
            email_confirmed=supabase_user.email_confirmed_at is not None,
            created_at=str(supabase_user.created_at) if supabase_user.created_at else "",
        )

    @staticmethod
    def _map_session(session, user: AuthUser) -> AuthSession:
        return AuthSession(
            access_token=session.access_token,
            refresh_token=session.refresh_token,
            token_type="bearer",
            expires_in=session.expires_in or 3600,
            user=user,
        )

    @staticmethod
    def _is_user_validated(supabase_user) -> bool:
        role = (getattr(supabase_user, "user_metadata", None) or {}).get("role", "user")
        app_metadata = getattr(supabase_user, "app_metadata", None) or {}
        if role == "admin":
            return True
        if "account_validated" not in app_metadata:
            return True
        return app_metadata.get("account_validated") is True

    @staticmethod
    def _is_user_blocked(supabase_user) -> bool:
        app_metadata = getattr(supabase_user, "app_metadata", None) or {}
        return app_metadata.get("account_blocked") is True or bool(
            getattr(supabase_user, "banned_until", None)
        )

    def _kick_user_sessions(self, user_id: str) -> bool:
        try:
            self._db.auth.admin.sign_out(user_id)
            return True
        except Exception:
            return False

    def _kick_all_blocked_user_sessions(self) -> int:
        kicked = 0
        try:
            users = self._db.auth.admin.list_users()
        except Exception:
            return kicked

        for user in users:
            app_metadata = getattr(user, "app_metadata", None) or {}
            if app_metadata.get("account_blocked") is True or bool(getattr(user, "banned_until", None)):
                if self._kick_user_sessions(user.id):
                    kicked += 1
        return kicked

    def signup(self, email: str, password: str, role: str = "user") -> AuthSession:
        try:
            response = self._db.auth.sign_up(
                {
                    "email": email,
                    "password": password,
                    "options": {
                        "data": {
                            "role": role,
                        },
                    },
                }
            )
        except Exception as exc:
            error_msg = str(exc).lower()
            if "already registered" in error_msg or "already been registered" in error_msg:
                raise UserAlreadyExistsException("User with this email already exists") from exc
            if "password" in error_msg:
                raise InvalidPasswordException(str(exc)) from exc
            if "email" in error_msg:
                raise InvalidEmailException(str(exc)) from exc
            raise AuthServiceException(f"Signup failed: {exc}") from exc

        if not response.user:
            raise AuthServiceException("Signup failed: no user returned")

        user = self._map_user(response.user)

        try:
            self._db.log_audit(user.id, "USER_SIGNUP", {"email": email, "role": role})
        except Exception:
            pass

        if response.session:
            return self._map_session(response.session, user)

        return AuthSession(
            access_token="",
            refresh_token="",
            token_type="bearer",
            expires_in=0,
            user=user,
        )

    def login(self, email: str, password: str) -> AuthSession:
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

        if self._is_user_blocked(response.user):
            self._db.record_login_attempt(email, False)
            self._db.auth.sign_out()
            raise UnauthorizedException("Account is blocked by an administrator")

        if not self._is_user_validated(response.user):
            self._db.record_login_attempt(email, False)
            self._db.auth.sign_out()
            raise UnauthorizedException("Account pending admin validation")

        self._db.record_login_attempt(email, True)

        user = self._map_user(response.user)
        try:
            self._db.log_audit(user.id, "USER_LOGIN", {"email": email})
        except Exception:
            pass

        return self._map_session(response.session, user)

    def get_current_user(self, access_token: str) -> AuthUser:
        try:
            response = self._db.auth.get_user(access_token)
        except Exception as exc:
            raise UnauthorizedException("Invalid or expired token") from exc

        if not response.user:
            raise UnauthorizedException("Invalid or expired token")

        return self._map_user(response.user)

    def _require_admin_token(self, access_token: str) -> AuthUser:
        try:
            response = self._db.auth.get_user(access_token)
        except Exception as exc:
            raise UnauthorizedException("Invalid or expired token") from exc

        if not response.user:
            raise UnauthorizedException("Invalid or expired token")

        requester = self._map_user(response.user)
        if requester.role != "admin":
            raise UnauthorizedException("Admin access required")
        return requester

    @staticmethod
    def _map_admin_user(supabase_user) -> dict[str, Any]:
        user_metadata = supabase_user.user_metadata or {}
        app_metadata = supabase_user.app_metadata or {}
        role = user_metadata.get("role", "user")
        return {
            "id": supabase_user.id,
            "email": supabase_user.email or "",
            "username": str(user_metadata.get("username") or ""),
            "phone_number": str(user_metadata.get("phone_number") or ""),
            "profile_picture": str(user_metadata.get("profile_picture") or ""),
            "role": role,
            "created_at": str(supabase_user.created_at) if supabase_user.created_at else "",
            "email_confirmed": supabase_user.email_confirmed_at is not None,
            "validated": role == "admin" or app_metadata.get("account_validated") is True,
            "blocked": app_metadata.get("account_blocked") is True
            or bool(getattr(supabase_user, "banned_until", None)),
            "invited": app_metadata.get("invited_by_admin") is True,
            "invited_at": str(app_metadata.get("invited_at") or ""),
            "last_sign_in_at": str(getattr(supabase_user, "last_sign_in_at", "") or ""),
        }

    def list_users(self, access_token: str) -> list[dict[str, Any]]:
        self._require_admin_token(access_token)
        try:
            users = self._db.auth.admin.list_users()
        except Exception as exc:
            raise AuthServiceException(f"Unable to list users: {exc}") from exc
        return [self._map_admin_user(user) for user in users]

    @staticmethod
    def _generate_password(length: int = 14) -> str:
        letters = string.ascii_letters
        digits = string.digits
        specials = "!@#$%^&*()_+-=[]{}|;:,.<>?"

        required = [
            secrets.choice(string.ascii_uppercase),
            secrets.choice(string.ascii_lowercase),
            secrets.choice(digits),
            secrets.choice(specials),
        ]
        remaining = [secrets.choice(letters + digits + specials) for _ in range(max(0, length - 4))]
        chars = required + remaining
        secrets.SystemRandom().shuffle(chars)
        return "".join(chars)

    def _generate_recovery_link(
        self, recipient_email: str, generated_password: str, login_url: str
    ) -> str:
        options = {"redirect_to": login_url} if login_url else {}
        params = {
            "type": "recovery",
            "email": recipient_email,
            "password": generated_password,
            "options": options,
        }
        response = self._db.auth.admin.generate_link(params)
        action_link = getattr(response, "action_link", None)
        if action_link:
            return str(action_link)
        properties = getattr(response, "properties", None)
        if isinstance(properties, dict):
            return str(properties.get("action_link") or "")
        return ""

    def _send_invite_email(
        self, recipient_email: str, generated_password: str
    ) -> tuple[bool, str]:
        login_url = (
            f"{self._settings.frontend_url.rstrip('/')}/login"
            if self._settings.frontend_url
            else ""
        )
        options = {"redirect_to": login_url} if login_url else None

        if (
            not self._settings.smtp_host
            or not self._settings.smtp_username
            or not self._settings.smtp_password
            or not self._settings.smtp_from_email
        ):
            # Default fallback path: use Supabase built-in recovery email delivery.
            try:
                self._db.auth.reset_password_email(recipient_email, options)
                return True, ""
            except Exception:
                try:
                    recovery_link = self._generate_recovery_link(
                        recipient_email=recipient_email,
                        generated_password=generated_password,
                        login_url=login_url,
                    )
                    if recovery_link:
                        return False, recovery_link
                except Exception:
                    pass
                return False, ""

        msg = EmailMessage()
        msg["Subject"] = "Your ICC Agent account invitation"
        msg["From"] = f"{self._settings.smtp_from_name} <{self._settings.smtp_from_email}>"
        msg["To"] = recipient_email
        lines = [
            "You have been invited to ICC Agent.",
            "",
            f"Email: {recipient_email}",
            f"Temporary password: {generated_password}",
            "",
            "Please sign in and complete your account setup:",
            "- set your username (required)",
            "- set your own password (required)",
            "- phone number and profile picture are optional.",
        ]
        if login_url:
            lines.extend(["", f"Login URL: {login_url}"])
        msg.set_content("\n".join(lines))

        try:
            with smtplib.SMTP(self._settings.smtp_host, self._settings.smtp_port, timeout=20) as smtp:
                if self._settings.smtp_use_tls:
                    smtp.starttls()
                smtp.login(self._settings.smtp_username, self._settings.smtp_password)
                smtp.send_message(msg)
            return True, ""
        except Exception:
            # If SMTP fails at runtime, fallback to Supabase delivery/link generation.
            try:
                self._db.auth.reset_password_email(recipient_email, options)
                return True, ""
            except Exception:
                try:
                    recovery_link = self._generate_recovery_link(
                        recipient_email=recipient_email,
                        generated_password=generated_password,
                        login_url=login_url,
                    )
                    if recovery_link:
                        return False, recovery_link
                except Exception:
                    pass
                return False, ""

    def invite_user(self, access_token: str, email: str, role: str = "user") -> dict[str, Any]:
        admin_user = self._require_admin_token(access_token)
        generated_password = self._generate_password()

        try:
            response = self._db.auth.admin.create_user(
                {
                    "email": email,
                    "password": generated_password,
                    "email_confirm": True,
                    "user_metadata": {
                        "role": role,
                        "username": "",
                        "phone_number": "",
                        "profile_picture": "",
                        "invite_onboarding_completed": False,
                    },
                    "app_metadata": {
                        "account_validated": True,
                        "account_blocked": False,
                        "invited_by_admin": True,
                        "invited_by": admin_user.id,
                        "invited_at": datetime.now(timezone.utc).isoformat(),
                    },
                }
            )
        except Exception as exc:
            error_msg = str(exc).lower()
            if "already registered" in error_msg or "already been registered" in error_msg:
                raise UserAlreadyExistsException("User with this email already exists") from exc
            if "email" in error_msg:
                raise InvalidEmailException(str(exc)) from exc
            raise AuthServiceException(f"Invitation failed: {exc}") from exc

        if not response.user:
            raise AuthServiceException("Invitation failed: no user returned")

        email_sent = False
        recovery_link = ""
        try:
            email_sent, recovery_link = self._send_invite_email(email, generated_password)
        except Exception:
            email_sent = False
            recovery_link = ""

        try:
            self._db.log_audit(
                admin_user.id,
                "USER_INVITE",
                {"target_email": email, "target_user_id": response.user.id, "email_sent": email_sent},
            )
        except Exception:
            pass

        return {
            "success": True,
            "message": "Invitation created",
            "user_id": response.user.id,
            "email": email,
            "generated_password": generated_password,
            "email_sent": email_sent,
            "recovery_link": recovery_link,
        }

    def set_user_validation(self, access_token: str, user_id: str, validated: bool) -> dict[str, Any]:
        admin_user = self._require_admin_token(access_token)

        try:
            current = self._db.auth.admin.get_user_by_id(user_id)
            current_app_metadata = current.user.app_metadata or {}
            current_app_metadata["account_validated"] = validated
            updated = self._db.auth.admin.update_user_by_id(
                user_id,
                {
                    "app_metadata": current_app_metadata,
                },
            )
        except Exception as exc:
            raise AuthServiceException(f"Failed to update validation: {exc}") from exc

        try:
            self._db.log_audit(
                admin_user.id,
                "USER_VALIDATE_TOGGLE",
                {"target_user_id": user_id, "validated": validated},
            )
        except Exception:
            pass

        return self._map_admin_user(updated.user)

    def set_user_block(self, access_token: str, user_id: str, blocked: bool) -> dict[str, Any]:
        admin_user = self._require_admin_token(access_token)
        kicked_sessions = 0

        try:
            current = self._db.auth.admin.get_user_by_id(user_id)
            current_app_metadata = current.user.app_metadata or {}
            current_app_metadata["account_blocked"] = blocked
            updated = self._db.auth.admin.update_user_by_id(
                user_id,
                {
                    "app_metadata": current_app_metadata,
                    "ban_duration": "876000h" if blocked else "none",
                },
            )
            if blocked:
                # Ensure currently logged-in blocked users are kicked out globally.
                kicked_sessions = self._kick_all_blocked_user_sessions()
        except Exception as exc:
            raise AuthServiceException(f"Failed to update block status: {exc}") from exc

        try:
            self._db.log_audit(
                admin_user.id,
                "USER_BLOCK_TOGGLE",
                {
                    "target_user_id": user_id,
                    "blocked": blocked,
                    "kicked_sessions": kicked_sessions,
                },
            )
        except Exception:
            pass

        return self._map_admin_user(updated.user)

    def delete_user(self, access_token: str, user_id: str) -> bool:
        admin_user = self._require_admin_token(access_token)

        if admin_user.id == user_id:
            raise UnauthorizedException("Admin cannot delete their own account")

        try:
            target_user = self._db.auth.admin.get_user_by_id(user_id)
            target_role = (target_user.user.user_metadata or {}).get("role", "user")
            if target_role == "admin":
                raise UnauthorizedException("Admin accounts cannot be deleted here")

            self._db.auth.admin.delete_user(user_id, should_soft_delete=False)
        except UnauthorizedException:
            raise
        except Exception as exc:
            raise AuthServiceException(f"Failed to delete user: {exc}") from exc

        try:
            self._db.log_audit(
                admin_user.id,
                "USER_DELETE",
                {"target_user_id": user_id},
            )
        except Exception:
            pass

        return True

    def logout(self) -> bool:
        try:
            self._db.auth.sign_out()
            return True
        except Exception:
            return False

    def request_password_reset(self, email: str) -> bool:
        try:
            self._db.auth.reset_password_email(email)
            return True
        except Exception as exc:
            raise AuthServiceException(f"Password reset failed: {exc}") from exc

    def update_password(self, access_token: str, new_password: str) -> bool:
        try:
            self._db.auth.update_user(
                jwt=access_token,
                attributes={"password": new_password},
            )
            return True
        except Exception as exc:
            raise InvalidPasswordException(f"Password update failed: {exc}") from exc

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
