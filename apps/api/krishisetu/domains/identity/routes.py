"""Authentication routes.

Endpoints:
- POST /auth/send-otp          — request OTP via SMS
- POST /auth/verify-otp        — verify OTP, get tokens (login or signup)
- POST /auth/login-password    — alternative: phone/email + password login
- POST /auth/refresh           — exchange refresh token for new token pair
- POST /auth/logout            — revoke refresh token
- POST /auth/logout-all        — revoke all sessions for current user
- GET  /me                     — get current user profile
- PATCH /me                    — update current user profile
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

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

    # X-Forwarded-For is set by the load balancer; fall back to direct client
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
    """Request an OTP to be sent via SMS to the given phone number.

    Rate limits:
    - Max 5 OTPs per hour per phone
    - Max 20 OTPs per day per phone
    - Min 60 seconds between OTPs (cooldown)

    The OTP expires after 5 minutes. Max 3 verification attempts per OTP.
    """
    result = await services.send_otp(db, payload.phone, payload.purpose)
    return SendOTPResponse(**result)


@router.post("/verify-otp", response_model=TokenResponse, status_code=200)
async def verify_otp(
    payload: VerifyOTPRequest,
    db: DBSession,
    request: Request,
) -> TokenResponse:
    """Verify an OTP and authenticate the user.

    If the phone number is already registered → login (full_name and
    preferred_language are ignored if provided).

    If the phone number is NOT registered → signup (full_name is required,
    a new user account is created with role=farmer).

    Returns access_token + refresh_token on success.
    """
    device_info, ip_address = _get_device_info(request)
    return await services.verify_otp(
        db,
        payload.phone,
        payload.otp,
        full_name=payload.full_name,
        preferred_language=payload.preferred_language,
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

    Account lockout policy:
    - After 5 failed attempts: 15-minute lock
    - After 3 lockouts in 24h: 24-hour lock (Phase 2 enhancement)
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
# Google OAuth (placeholder flow)
# ---------------------------------------------------------------------------


from fastapi.responses import RedirectResponse


@router.get("/google", status_code=302)
async def google_oauth_start() -> RedirectResponse:
    """Start Google OAuth flow by redirecting the user to Google."""
    import os

    client_id = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
    redirect_uri = os.getenv("GOOGLE_OAUTH_REDIRECT_URI", "")
    scope = "openid email profile"
    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope={scope}"
        f"&access_type=offline"
        f"&prompt=consent"
    )
    return RedirectResponse(url=auth_url)


@router.get("/google/callback", status_code=200)
async def google_oauth_callback(request: Request) -> dict:
    """Handle Google OAuth callback.

    Expects `code` query param. In production, exchange it for tokens and
    create/login the user. This placeholder returns the received code.
    """
    code = request.query_params.get("code")
    if not code:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail="Missing code")
    return {"message": "Google OAuth callback received", "code": code}


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

    Implements refresh token rotation:
    - The old refresh token is revoked
    - A new access + refresh token pair is issued

    If a revoked token is presented (token reuse), ALL tokens for the user
    are immediately revoked (suspected token theft).
    """
    device_info, ip_address = _get_device_info(request)
    return await services.refresh_access_token(
        db,
        payload.refresh_token,
        device_info=device_info,
        ip_address=ip_address,
    )


# ---------------------------------------------------------------------------
# Aadhaar e-KYC (Phase D — real UIDAI integration)
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
    """Send Aadhaar OTP for e-KYC verification.

    Calls UIDAI's Aadhaar Authentication API to send an OTP to the
    farmer's mobile number registered with Aadhaar.

    Rate limits:
    - Max 5 OTP requests per hour per Aadhaar
    - Max 20 OTP requests per day per Aadhaar
    - 60-second cooldown between requests

    In development mode, the OTP is printed to the API logs.
    """
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
    """Verify Aadhaar OTP and mark the user's Aadhaar as verified.

    On successful verification:
    1. Updates user.aadhaar_verified = True
    2. Stores the Aadhaar hash (SHA-256 + salt, never raw)
    3. Updates user's name/state/district from UIDAI response (if provided)

    In development mode, use the OTP from the API logs.
    """
    from krishisetu.integrations.uidai import get_uidai_client
    from krishisetu.core.security import hash_aadhaar
    from krishisetu.domains.identity import repository as repo

    client = get_uidai_client()
    result = await client.verify_otp(
        payload.aadhaar, payload.otp, payload.transaction_id
    )

    if result.verified:
        # Update user record
        aadhaar_hash = hash_aadhaar(payload.aadhaar)
        updates: dict[str, object] = {
            "aadhaar_verified": True,
            "aadhaar_hash": aadhaar_hash,
        }
        if result.name:
            updates["full_name"] = result.name
        if result.state:
            # Could update farmer profile state if different
            pass

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
    """Revoke the given refresh token (logout from current device).

    Idempotent — calling with an already-revoked or invalid token is a no-op.
    """
    await services.logout(db, payload.refresh_token)
    return {"message": "Logged out successfully"}


class LogoutAllRequest(BaseModel):
    """Request body for POST /auth/logout-all."""

    refresh_token: str = Field(..., description="Any active refresh token (used to identify the user)")


@router.post("/logout-all", status_code=200)
async def logout_all(
    current_user: CurrentUser,
    db: DBSession,
) -> dict:
    """Revoke ALL active refresh tokens for the current user (logout all devices).

    Useful when:
    - User suspects their account is compromised
    - User changes their password
    - Admin forces a logout
    """
    await services.logout_all_sessions(db, current_user.id)
    return {"message": "All sessions logged out successfully"}


# ---------------------------------------------------------------------------
# Current user profile (/me)
# ---------------------------------------------------------------------------

me_router = APIRouter(prefix="/me", tags=["profile"])


class UpdateProfileRequest(BaseModel):
    """Schema for PATCH /me."""

    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    email: str | None = Field(default=None, max_length=255)
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

    Only the fields provided in the request body are updated. Phone number
    and Aadhaar cannot be changed via this endpoint (they require separate
    verification flows).
    """
    from krishisetu.domains.identity import repository as repo

    updates: dict[str, object] = {}
    if payload.full_name is not None:
        updates["full_name"] = payload.full_name
    if payload.email is not None:
        updates["email"] = payload.email
    if payload.preferred_language is not None:
        allowed = {"en", "hi", "mr", "ta", "te", "bn", "kn", "gu", "pa", "ml"}
        if payload.preferred_language not in allowed:
            from krishisetu.core.exceptions import ValidationError

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
    from krishisetu.core.dependencies import require_role
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
        # No-op
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
