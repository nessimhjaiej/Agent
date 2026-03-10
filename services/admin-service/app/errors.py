class AdminServiceError(Exception):
    """Base error for admin-service."""


class ConfigurationError(AdminServiceError):
    """Raised when service configuration is invalid."""


class PlannerError(AdminServiceError):
    """Raised when the request cannot be mapped to a tool."""


class AuthorizationError(AdminServiceError):
    """Raised when the caller is not authorized to perform the action."""


class ToolExecutionError(AdminServiceError):
    """Raised when a tool or upstream dependency fails."""


class UpstreamServiceError(AdminServiceError):
    """Raised when an upstream service call fails."""
