"""Custom exceptions for auth service."""


class AuthServiceException(Exception):
    """Base exception for auth service."""


class InvalidCredentialsException(AuthServiceException):
    """Raised when email/password is invalid."""


class UserNotFoundException(AuthServiceException):
    """Raised when user is not found."""


class UserAlreadyExistsException(AuthServiceException):
    """Raised when user already exists."""


class InvalidPasswordException(AuthServiceException):
    """Raised when password doesn't meet requirements."""


class InvalidEmailException(AuthServiceException):
    """Raised when email format is invalid."""


class UnauthorizedException(AuthServiceException):
    """Raised when user is not authorized."""


class TokenExpiredException(AuthServiceException):
    """Raised when JWT token is expired."""


class AccountLockedException(AuthServiceException):
    """Raised when user account is locked due to too many failed login attempts."""


class InvalidUserStateException(AuthServiceException):
    """Raised when an operation is not allowed for the user's current state."""
