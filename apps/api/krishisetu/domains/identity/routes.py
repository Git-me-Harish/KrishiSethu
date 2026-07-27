"""Authentication routes.

Endpoints:
- POST /auth/send-otp          — request OTP via SMS
- POST /auth/verify-otp        — verify OTP, get tokens (login or signup)
- POST /auth/login-password    — alternative: phone/email + password login
- GET  /auth/google            — start Google OAuth flow (redirect to Google)
- GET  /auth/google/callback   — Google OAuth callback (exchange code, issue tokens)
- POST /auth/refresh           — exchange refresh token for new token pair
- POST /auth/logout            — revoke refresh token
- POST /auth/logout-all        — revoke all sessions for current user
- GET  /me                     — get current user profile
- PATCH /me                    — update current user profile
"""

from __future__ import annotations

import asyncio
from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from krishisetu.core.config import settings
from krishisetu.core.dependencies import CurrentUser, DBSession
from krishisetu.core.logging import get_logger
from krishisetu.domains.identity import services
from krishisetu.domains.identity.models import UserRole
from krishisetu.domains.identity.schemas import (
    AdminUserListResponse,
    AdminUserUpdate,
    LogoutRequest,
    RefreshTokenRequest,
    SendOTPRequest,
    TokenResponse,
    UserPublic,
    VerifyOTPRequest,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])


# ---------------------------------------------------------------------------
# Helper: extract device info from request
# ---------------------------------------------------------------------------


def _get_device_info(request: Request) -> tuple[str | None, str | None]:
    """Extract User-Agent and client IP from the request."""
    user_agent = request.headers.get("User-Agent")
    if user_agent and len(user_agent) > 512:
        user_agent = user_agent[:512]

    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        client_ip = forwarded_for.split(",")[0].strip()
    else:
        client_ip = request.client.host if request.client else None

    return user_agent, client_ip


# ---------------------------------------------------------------------------
# OTP-based authentication
# ---------------------------------------------------------------------------


class SendOTPResponse(BaseModel):
    """Response for POST /auth/send-otp."""

    phone: str
    purpose: str
    ttl_seconds: int
    cooldown_seconds: int
    max_attempts: int
    debug_otp: str | None = Field(
        default=None,
        description="OTP returned only in development environment (ConsoleSMSBackend)",
    )


@router.post("/send-otp", response_model=SendOTPResponse, status_code=202)
async def send_otp(
    payload: SendOTPRequest,
    db: DBSession,
) -> SendOTPResponse:
    """Request an OTP to be sent via SMS to the given phone number."""
    result = await services.send_otp(db, payload.phone, payload.purpose)
    return SendOTPResponse(**result)


@router.post("/verify-otp", response_model=TokenResponse, status_code=200)
async def verify_otp(
    payload: VerifyOTPRequest,
    db: DBSession,
    request: Request,
) -> TokenResponse:
    """Verify an OTP and authenticate the user.

    If the phone number is already registered → login.
    If the phone number is NOT registered → signup (full_name required).
    Returns access_token + refresh_token on success.
    """
    device_info, ip_address = _get_device_info(request)
    return await services.verify_otp(
        db,
        payload.phone,
        payload.otp,
        full_name=payload.full_name,
        preferred_language=payload.preferred_language,
        device_info=device_info,
        ip_address=ip_address,
    )


# ---------------------------------------------------------------------------
# Password-based authentication (alternative)
# ---------------------------------------------------------------------------


class PasswordLoginRequest(BaseModel):
    """Request body for POST /auth/login-password."""

    phone_or_email: str = Field(
        ...,
        description="Phone number (10 digits) or email address",
        examples=["9876543210", "admin@krishisetu.in"],
    )
    password: str = Field(..., min_length=8, max_length=128)


@router.post("/login-password", response_model=TokenResponse, status_code=200)
async def login_with_password(
    payload: PasswordLoginRequest,
    db: DBSession,
    request: Request,
) -> TokenResponse:
    """Login with phone/email and password.

    Used by admin, officer, supplier, and insurer accounts that have
    passwords set. Farmers typically use OTP-only auth.
    """
    device_info, ip_address = _get_device_info(request)
    return await services.login_with_password(
        db,
        payload.phone_or_email,
        payload.password,
        device_info=device_info,
        ip_address=ip_address,
    )


# ---------------------------------------------------------------------------
# Google OAuth
# ---------------------------------------------------------------------------


# Cookie that binds an in-flight OAuth state to this browser. HttpOnly (no
# JS needs it) and SameSite=Lax so it survives Google's top-level GET
# redirect back to the callback.
OAUTH_STATE_COOKIE = "ks_oauth_state"


@router.get("/google", status_code=302)
async def google_oauth_start() -> RedirectResponse:
    """Start Google OAuth flow by redirecting the user to Google.

    Mints a state token plus a PKCE verifier (stored in Redis, 10-min TTL),
    sets the state in a signed HttpOnly cookie, then redirects to Google's
    authorization endpoint.

    Both the cookie and the Redis record are checked in /auth/google/callback.
    The cookie is what makes state a real CSRF defence — without it, `state`
    only proves some flow was started on this server, not that the browser
    finishing the flow is the one that began it.
    """
    cfg = settings()

    if not cfg.google_oauth_enabled:
        raise HTTPException(
            status_code=503,
            detail="Google OAuth is not configured on this server.",
        )

    state, code_challenge = await services.generate_google_oauth_state()

    params = urlencode({
        "client_id": cfg.GOOGLE_OAUTH_CLIENT_ID,
        "redirect_uri": cfg.GOOGLE_OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    })

    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{params}"
    response = RedirectResponse(url=auth_url)
    response.set_cookie(
        key=OAUTH_STATE_COOKIE,
        value=services.build_oauth_state_cookie(state),
        max_age=services.GOOGLE_OAUTH_STATE_TTL_SECONDS,
        httponly=True,
        secure=cfg.is_production or cfg.CSRF_COOKIE_SECURE,
        samesite="lax",
        path="/api/v1/auth",
    )
    return response


@router.get("/google/callback")
async def google_oauth_callback(
    request: Request,
    db: DBSession,
) -> RedirectResponse:
    """Handle Google OAuth callback.

    Expects `code` and `state` query params from Google.

    Flow:
    1. Validate state against the signed cookie + Redis (CSRF protection)
    2. Exchange code for Google tokens
    3. Fetch user profile from Google
    4. Find or create KrishiSetu user
    5. Issue KrishiSetu JWT tokens
    6. Redirect to frontend /auth/callback with a single-use exchange code

    On error: redirect to frontend login page with error query param.
    """
    from krishisetu.core.exceptions import AuthenticationError

    cfg = settings()
    frontend_url = cfg.FRONTEND_URL.rstrip("/")

    code = request.query_params.get("code")
    state = request.query_params.get("state")
    error = request.query_params.get("error")

    def _redirect_to_login(error_code: str) -> RedirectResponse:
        response = RedirectResponse(
            url=f"{frontend_url}/login?error={error_code}", status_code=302
        )
        response.delete_cookie(OAUTH_STATE_COOKIE, path="/api/v1/auth")
        return response

    # Google may return error (e.g. user denied consent)
    if error:
        logger.warning("google_oauth.user_denied", error=error)
        return _redirect_to_login("google_denied")

    if not code or not state:
        return _redirect_to_login("google_invalid_callback")

    device_info, ip_address = _get_device_info(request)

    try:
        token_response = await services.google_oauth_login(
            db,
            code=code,
            state=state,
            state_cookie=request.cookies.get(OAUTH_STATE_COOKIE),
            device_info=device_info,
            ip_address=ip_address,
        )
        exchange_code = await services.store_oauth_exchange_code(token_response)
    except AuthenticationError as exc:
        logger.warning("google_oauth.callback_failed", reason=str(exc))
        # Redirect to frontend with a safe error code (no internal details)
        return _redirect_to_login("google_auth_failed")
    except Exception as exc:
        logger.error("google_oauth.unexpected_error", error=str(exc))
        return _redirect_to_login("google_server_error")

    # Redirect with a single-use, 60-second exchange code instead of the
    # tokens themselves. Query strings leak into browser history, Referer
    # headers and proxy logs — a 30-day refresh token must never travel there.
    # The frontend redeems this via POST /auth/google/exchange.
    callback_params = urlencode({"code": exchange_code})
    response = RedirectResponse(
        url=f"{frontend_url}/auth/callback?{callback_params}", status_code=302
    )
    response.delete_cookie(OAUTH_STATE_COOKIE, path="/api/v1/auth")
    return response


class GoogleExchangeRequest(BaseModel):
    """Request body for POST /auth/google/exchange."""

    code: str = Field(
        ...,
        min_length=16,
        max_length=128,
        description="Single-use code from the /auth/callback redirect",
    )


@router.post("/google/exchange", response_model=TokenResponse, status_code=200)
async def google_oauth_exchange(payload: GoogleExchangeRequest) -> TokenResponse:
    """Redeem a single-use OAuth exchange code for the issued token pair.

    The code is deleted atomically on read, so a replay — from history, a log,
    or a second tab — gets nothing.
    """
    return await services.consume_oauth_exchange_code(payload.code)


# ---------------------------------------------------------------------------
# Token refresh
# ---------------------------------------------------------------------------


@router.post("/refresh", response_model=TokenResponse, status_code=200)
async def refresh_token(
    payload: RefreshTokenRequest,
    db: DBSession,
    request: Request,
) -> TokenResponse:
    """Exchange a refresh token for a new access + refresh token pair.

    Implements refresh token rotation with reuse detection.
    """
    device_info, ip_address = _get_device_info(request)
    return await services.refresh_access_token(
        db,
        payload.refresh_token,
        device_info=device_info,
        ip_address=ip_address,
    )


# ---------------------------------------------------------------------------
# Aadhaar e-KYC (Phase D)
# ---------------------------------------------------------------------------


class AadhaarSendOTPRequest(BaseModel):
    """Request body for POST /auth/aadhaar/send-otp."""

    aadhaar: str = Field(
        ...,
        min_length=12,
        max_length=12,
        description="12-digit Aadhaar number",
    )


class AadhaarVerifyOTPRequest(BaseModel):
    """Request body for POST /auth/aadhaar/verify-otp."""

    aadhaar: str = Field(..., min_length=12, max_length=12)
    otp: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")
    transaction_id: str = Field(..., min_length=10, max_length=64)


class AadhaarOTPResponse(BaseModel):
    """Response for Aadhaar OTP send."""

    transaction_id: str
    message: str
    masked_aadhaar: str
    sent_at: str


class AadhaarVerificationResponse(BaseModel):
    """Response for Aadhaar OTP verification."""

    verified: bool
    masked_aadhaar: str
    name: str | None = None
    gender: str | None = None
    year_of_birth: str | None = None
    state: str | None = None
    district: str | None = None


@router.post("/aadhaar/send-otp", response_model=AadhaarOTPResponse, status_code=202)
async def send_aadhaar_otp(
    payload: AadhaarSendOTPRequest,
    current_user: CurrentUser,
) -> AadhaarOTPResponse:
    """Send Aadhaar OTP for e-KYC verification."""
    from krishisetu.integrations.uidai import get_uidai_client

    client = get_uidai_client()
    result = await client.send_otp(payload.aadhaar)

    return AadhaarOTPResponse(
        transaction_id=result.transaction_id,
        message=result.message,
        masked_aadhaar=f"XXXX-XXXX-{payload.aadhaar[-4:]}",
        sent_at=result.sent_at.isoformat(),
    )


@router.post("/aadhaar/verify-otp", response_model=AadhaarVerificationResponse)
async def verify_aadhaar_otp(
    payload: AadhaarVerifyOTPRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> AadhaarVerificationResponse:
    """Verify Aadhaar OTP and mark the user's Aadhaar as verified."""
    from krishisetu.integrations.uidai import get_uidai_client
    from krishisetu.core.security import hash_aadhaar
    from krishisetu.domains.identity import repository as repo

    client = get_uidai_client()
    result = await client.verify_otp(
        payload.aadhaar, payload.otp, payload.transaction_id
    )

    if result.verified:
        # PBKDF2 at 310k iterations is ~200ms of CPU — run it off the event
        # loop so one e-KYC call doesn't stall every other request.
        aadhaar_hash = await asyncio.to_thread(hash_aadhaar, payload.aadhaar)
        updates: dict[str, object] = {
            "aadhaar_verified": True,
            "aadhaar_hash": aadhaar_hash,
        }
        if result.name:
            updates["full_name"] = result.name

        await repo.update_user(db, current_user.id, **updates)

        logger.info(
            "aadhaar.verified",
            user_id=str(current_user.id),
            masked_aadhaar=result.masked_aadhaar,
        )

    return AadhaarVerificationResponse(
        verified=result.verified,
        masked_aadhaar=result.masked_aadhaar,
        name=result.name,
        gender=result.gender,
        year_of_birth=result.year_of_birth,
        state=result.state,
        district=result.district,
    )


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


@router.post("/logout", status_code=200)
async def logout(
    payload: LogoutRequest,
    db: DBSession,
) -> dict:
    """Revoke the given refresh token (logout from current device). Idempotent."""
    await services.logout(db, payload.refresh_token)
    return {"message": "Logged out successfully"}


class LogoutAllRequest(BaseModel):
    """Request body for POST /auth/logout-all."""

    refresh_token: str = Field(
        ..., description="Any active refresh token (used to identify the user)"
    )


@router.post("/logout-all", status_code=200)
async def logout_all(
    current_user: CurrentUser,
    db: DBSession,
) -> dict:
    """Revoke ALL active refresh tokens for the current user (logout all devices)."""
    await services.logout_all_sessions(db, current_user.id)
    return {"message": "All sessions logged out successfully"}


# ---------------------------------------------------------------------------
# Current user profile (/me)
# ---------------------------------------------------------------------------

me_router = APIRouter(prefix="/me", tags=["profile"])


class UpdateProfileRequest(BaseModel):
    """Schema for PATCH /me."""

    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    email: str | None = Field(
        default=None,
        max_length=255,
        description=(
            "Rejected: email changes require a verification flow that does "
            "not exist yet. Retained so callers get a clear 422 rather than "
            "a silently ignored field."
        ),
    )
    preferred_language: str | None = Field(
        default=None,
        description="One of: en, hi, mr, ta, te, bn, kn, gu, pa, ml",
    )


@me_router.get("", response_model=UserPublic)
@me_router.get("/", response_model=UserPublic, include_in_schema=False)
async def get_me(current_user: CurrentUser) -> UserPublic:
    """Get the current authenticated user's profile."""
    return UserPublic.model_validate(current_user)


@me_router.patch("", response_model=UserPublic)
async def update_me(
    payload: UpdateProfileRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> UserPublic:
    """Update the current user's profile.

    Email is deliberately NOT updatable here. This endpoint used to accept an
    arbitrary address, write it straight to the record, and leave
    email_verified untouched — so anyone could claim a stranger's Gmail
    address and, under the old email-matching OAuth login, be handed that
    stranger's Google sign-in. Changing an email needs a verification round
    trip; until that exists, the field is refused outright.
    """
    from krishisetu.core.exceptions import ValidationError
    from krishisetu.domains.identity import repository as repo

    if payload.email is not None and payload.email != current_user.email:
        raise ValidationError(
            "Email address cannot be changed here — it requires verification. "
            "Contact support to update your email."
        )

    updates: dict[str, object] = {}
    if payload.full_name is not None:
        updates["full_name"] = payload.full_name
    if payload.preferred_language is not None:
        allowed = {"en", "hi", "mr", "ta", "te", "bn", "kn", "gu", "pa", "ml"}
        if payload.preferred_language not in allowed:
            raise ValidationError(
                f"Language must be one of: {', '.join(sorted(allowed))}"
            )
        updates["preferred_language"] = payload.preferred_language

    if updates:
        updated = await repo.update_user(db, current_user.id, **updates)
        if updated:
            return UserPublic.model_validate(updated)

    return UserPublic.model_validate(current_user)


# ---------------------------------------------------------------------------
# Admin user management (/admin/users)
# ---------------------------------------------------------------------------

admin_router = APIRouter(prefix="/admin/users", tags=["admin"])


@admin_router.get("", response_model=AdminUserListResponse)
async def list_users(
    db: DBSession,
    current_user: CurrentUser,
    page: int = 1,
    page_size: int = 20,
    role: UserRole | None = None,
    is_active: bool | None = None,
) -> AdminUserListResponse:
    """List all users with pagination and filters (admin only)."""
    from krishisetu.core.exceptions import AuthorizationError

    if current_user.role != UserRole.ADMIN:
        raise AuthorizationError("Admin access required")

    from krishisetu.domains.identity import repository as repo

    page = max(1, page)
    page_size = max(1, min(100, page_size))

    users, total = await repo.list_users(
        db,
        page=page,
        page_size=page_size,
        role=role,
        is_active=is_active,
    )

    return AdminUserListResponse(
        users=[UserPublic.model_validate(u) for u in users],
        total=total,
        page=page,
        page_size=page_size,
        has_more=(page * page_size) < total,
    )


@admin_router.patch("/{user_id}", response_model=UserPublic)
async def update_user_admin(
    user_id: str,
    payload: AdminUserUpdate,
    current_user: CurrentUser,
    db: DBSession,
) -> UserPublic:
    """Update a user's role or active status (admin only)."""
    from uuid import UUID

    from krishisetu.core.exceptions import AuthorizationError, NotFoundError
    from krishisetu.domains.identity import repository as repo

    if current_user.role != UserRole.ADMIN:
        raise AuthorizationError("Admin access required")

    try:
        uid = UUID(user_id)
    except ValueError as e:
        raise NotFoundError("User", user_id) from e

    updates: dict[str, object] = {}
    if payload.role is not None:
        updates["role"] = payload.role
    if payload.is_active is not None:
        updates["is_active"] = payload.is_active
    if payload.full_name is not None:
        updates["full_name"] = payload.full_name

    if not updates:
        existing = await repo.get_user_by_id(db, uid)
        if not existing:
            raise NotFoundError("User", user_id)
        return UserPublic.model_validate(existing)

    updated = await repo.update_user(db, uid, **updates)
    if not updated:
        raise NotFoundError("User", user_id)

    logger.info(
        "admin.user_updated",
        target_user_id=user_id,
        updated_by=str(current_user.id),
        fields=list(updates.keys()),
    )

    return UserPublic.model_validate(updated)