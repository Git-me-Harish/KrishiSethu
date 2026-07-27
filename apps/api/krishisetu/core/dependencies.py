"""Shared FastAPI dependencies for authentication and authorization.

These dependencies are injected into route handlers via FastAPI's `Depends()`
mechanism. They enforce:
1. Authentication — `get_current_user` validates the JWT and returns the User
2. Authorization — `require_permissions(*perms)` checks the user's role has
   all required permissions
3. Optional auth — `get_optional_user` returns User or None (for endpoints
   that work both authenticated and anonymous)

Usage in routes:
    from krishisetu.core.dependencies import get_current_user, require_permissions
    from krishisetu.domains.identity.permissions import PERM_PLOT_CREATE

    @router.post("/plots", dependencies=[Depends(require_permissions(PERM_PLOT_CREATE))])
    async def create_plot(
        payload: PlotCreate,
        current_user: Annotated[User, Depends(get_current_user)],
        db: Annotated[AsyncSession, Depends(get_db)],
    ) -> PlotResponse:
        ...
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from krishisetu.core.database import get_db
from krishisetu.core.exceptions import AuthenticationError, AuthorizationError
from krishisetu.core.logging import get_logger
from krishisetu.core.security import decode_token
from krishisetu.domains.identity import repository as repo
from krishisetu.domains.identity.models import User, UserRole
from krishisetu.domains.identity.permissions import has_all_permissions

logger = get_logger(__name__)

# FastAPI's HTTPBearer auto-extracts the Bearer token from Authorization header
# and generates proper OpenAPI documentation showing the security scheme.
_bearer_scheme = HTTPBearer(
    bearerFormat="JWT",
    auto_error=True,
    description="JWT access token issued by /auth/verify-otp or /auth/refresh",
)


async def get_current_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(_bearer_scheme)],
    request: Request,
) -> User:
    """Validate the JWT and return the authenticated user.

    Raises AuthenticationError if:
    - Token is missing, malformed, expired, or has invalid signature
    - User does not exist in the database
    - User account is deactivated

    The dependency also supports an alternative auth method via the
    X-User-Id header (used for internal service-to-service calls), but
    this is disabled in production.
    """
    token = credentials.credentials

    # Decode and validate the JWT
    try:
        payload = decode_token(token, expected_type="access")
    except AuthenticationError:
        raise
    except Exception as e:
        logger.warning("auth.token_decode_failed", error=str(e))
        raise AuthenticationError("Invalid authentication token") from e

    user_id = payload.get("sub")
    if not user_id:
        raise AuthenticationError("Token missing 'sub' claim")

    # Look up the user
    user = await repo.get_user_by_id(db, user_id)
    if not user:
        logger.warning("auth.user_not_found", user_id=user_id)
        raise AuthenticationError("User not found")

    if not user.is_active:
        logger.warning("auth.inactive_user", user_id=str(user.id))
        raise AuthenticationError("Account is deactivated")

    # Bind user context to logs for the duration of this request
    import structlog

    structlog.contextvars.bind_contextvars(
        user_id=str(user.id),
        user_role=user.role.value,
    )

    # Store user on request.state for access in middleware/handlers
    request.state.user = user

    return user


async def get_optional_user(
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
    authorization: str | None = Header(default=None),
) -> User | None:
    """Return the authenticated user if a valid token is present, else None.

    Used for endpoints that work both authenticated (personalized) and
    anonymous (public). Example: scheme detail page shows eligibility only
    if user is logged in.
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None

    token = authorization.removeprefix("Bearer ").strip()
    try:
        payload = decode_token(token, expected_type="access")
    except AuthenticationError:
        return None

    user_id = payload.get("sub")
    if not user_id:
        return None

    user = await repo.get_user_by_id(db, user_id)
    if not user or not user.is_active:
        return None

    return user


def require_permissions(*permissions: str):
    """FastAPI dependency factory that enforces role-based authorization.

    Usage:
        @router.post(
            "/plots",
            dependencies=[Depends(require_permissions(PERM_PLOT_CREATE))],
        )
        async def create_plot(...):
            ...

    Raises AuthorizationError (403) if the authenticated user's role does not
    grant ALL the specified permissions.
    """
    async def permission_checker(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if not has_all_permissions(current_user.role, *permissions):
            missing = [
                p for p in permissions
                if not has_all_permissions(current_user.role, p)
            ]
            logger.warning(
                "authz.permission_denied",
                user_id=str(current_user.id),
                role=current_user.role.value,
                required=permissions,
                missing=missing,
            )
            raise AuthorizationError(
                f"Insufficient permissions. Required: {', '.join(permissions)}"
            )
        return current_user

    return permission_checker


def require_role(*roles: UserRole):
    """FastAPI dependency factory that enforces role-based access.

    Simpler than require_permissions when you just need a role check.
    Usage:
        @router.post(
            "/admin/users",
            dependencies=[Depends(require_role(UserRole.ADMIN))],
        )
    """
    async def role_checker(
        current_user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if current_user.role not in roles:
            logger.warning(
                "authz.role_denied",
                user_id=str(current_user.id),
                role=current_user.role.value,
                required_roles=[r.value for r in roles],
            )
            raise AuthorizationError(
                f"Access restricted to roles: {', '.join(r.value for r in roles)}"
            )
        return current_user

    return role_checker


# Type aliases for cleaner route signatures
CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentUserOptional = Annotated[User | None, Depends(get_optional_user)]
DBSession = Annotated[AsyncSession, Depends(get_db)]
