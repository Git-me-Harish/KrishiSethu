"""Custom exception hierarchy.

Exceptions are caught by FastAPI exception handlers (registered in main.py)
and converted to consistent JSON error responses.
"""

from __future__ import annotations


class KrishiSetuError(Exception):
    """Base exception for all KrishiSetu application errors."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        status_code: int = 500,
        details: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class ValidationError(KrishiSetuError):
    """Raised when input validation fails."""

    def __init__(self, message: str, details: dict | None = None) -> None:
        super().__init__(message, code="VALIDATION_ERROR", status_code=422, details=details)


class AuthenticationError(KrishiSetuError):
    """Raised when authentication fails."""

    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__(message, code="AUTHENTICATION_ERROR", status_code=401)


class AuthorizationError(KrishiSetuError):
    """Raised when user lacks permission for an action."""

    def __init__(self, message: str = "Insufficient permissions") -> None:
        super().__init__(message, code="AUTHORIZATION_ERROR", status_code=403)


class NotFoundError(KrishiSetuError):
    """Raised when a resource is not found."""

    def __init__(self, resource: str, identifier: str) -> None:
        super().__init__(
            f"{resource} not found: {identifier}",
            code="NOT_FOUND",
            status_code=404,
        )


class ConflictError(KrishiSetuError):
    """Raised when a resource already exists or state conflict occurs."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="CONFLICT", status_code=409)


class RateLimitExceededError(KrishiSetuError):
    """Raised when rate limit is exceeded."""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(
            "Rate limit exceeded",
            code="RATE_LIMIT_EXCEEDED",
            status_code=429,
            details={"retry_after_seconds": retry_after_seconds},
        )
        self.retry_after_seconds = retry_after_seconds


class ExternalServiceError(KrishiSetuError):
    """Raised when an external API call fails."""

    def __init__(self, service: str, message: str) -> None:
        super().__init__(
            f"External service '{service}' error: {message}",
            code="EXTERNAL_SERVICE_ERROR",
            status_code=502,
            details={"service": service},
        )
