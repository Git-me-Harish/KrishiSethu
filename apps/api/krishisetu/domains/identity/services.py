"""Identity domain — business logic services.

The service layer contains business logic that doesn't belong in routes
(HTTP concerns) or repository (data access concerns). It orchestrates
multiple repository calls, applies business rules, and integrates with
external services (SMS gateway, etc.).

Services are async and accept a database session. They raise domain
exceptions (from krishisetu.core.exceptions) which are caught by FastAPI
exception handlers and converted to HTTP responses.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from krishisetu.core.config import settings
from krishisetu.core.exceptions import (
    AuthenticationError,
    ConflictError,
    RateLimitExceededError,
    ValidationError,
)
from krishisetu.core.logging import get_logger
from krishisetu.core.redis import get_redis
from krishisetu.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_otp,
)
from krishisetu.core.sms import get_sms_backend
from krishisetu.domains.identity.models import User, UserRole
from krishisetu.domains.identity import repository as repo
from krishisetu.domains.identity.schemas import (
    TokenResponse,
    UserPublic,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Rate limit constants
# ---------------------------------------------------------------------------

# OTP rate limits (per phone number, sliding window)
OTP_SEND_MAX_PER_HOUR = 5
OTP_SEND_MAX_PER_DAY = 20
OTP_VERIFY_MAX_ATTEMPTS = 3

# OTP storage TTLs (seconds)
OTP_TTL_SECONDS = 5 * 60  # 5 minutes
OTP_COOLDOWN_SECONDS = 60  # Min time between OTP sends

# Account lockout policy
ACCOUNT_LOCKOUT_THRESHOLD = 5  # Failed attempts before lock
ACCOUNT_LOCKOUT_DURATION_MINUTES = 15
ACCOUNT_LOCKOUT_EXTENDED_MINUTES = 24 * 60  # 24 hours after 3 lockouts in 24h


# ---------------------------------------------------------------------------
# OTP send flow
# ---------------------------------------------------------------------------


async def send_otp(
    db: AsyncSession,
    phone: str,
    purpose: str = "login",
) -> dict[str, Any]:
    """Generate and dispatch an OTP to the given phone number.

    Rate limits (per phone, per purpose):
    - Max 5 OTPs per hour
    - Max 20 OTPs per day
    - Min 60 seconds between OTPs (cooldown)

    The OTP is stored in Redis (not Postgres) for performance, with a 5-minute
    TTL. The phone-prefixed Redis key includes the purpose to allow concurrent
    OTPs for different purposes (e.g., signup + login).

    Returns a dict with metadata about the send (used for the API response).
    """
    redis = await get_redis()
    now = datetime.now(timezone.utc)

    # --- Rate limit checks ---
    hour_key = f"otp:rl:{phone}:{purpose}:hour:{now.strftime('%Y%m%d%H')}"
    day_key = f"otp:rl:{phone}:{purpose}:day:{now.strftime('%Y%m%d')}"
    cooldown_key = f"otp:cd:{phone}:{purpose}"

    hour_count = int(await redis.get(hour_key) or 0)
    day_count = int(await redis.get(day_key) or 0)

    if hour_count >= OTP_SEND_MAX_PER_HOUR:
        raise RateLimitExceededError(retry_after_seconds=3600)
    if day_count >= OTP_SEND_MAX_PER_DAY:
        raise RateLimitExceededError(retry_after_seconds=86400)

    if await redis.exists(cooldown_key):
        ttl = await redis.ttl(cooldown_key)
        raise RateLimitExceededError(retry_after_seconds=max(ttl, 1))

    # --- For signup: check user doesn't already exist ---
    if purpose == "signup":
        existing = await repo.get_user_by_phone(db, phone)
        if existing:
            raise ConflictError("Phone number already registered. Use login instead.")

    # --- For login: check user exists and is active ---
    if purpose == "login":
        existing = await repo.get_user_by_phone(db, phone)
        if existing and not existing.is_active:
            raise AuthenticationError("Account is deactivated. Contact support.")

    # --- Generate OTP and store in Redis ---
    otp = generate_otp(length=6)
    otp_key = f"otp:{phone}:{purpose}"
    attempts_key = f"otp:attempts:{phone}:{purpose}"

    # Store OTP as SHA-256 hash (never store raw OTP in Redis for defense in depth)
    # But for dev convenience, we also store the raw OTP (logged by ConsoleSMSBackend)
    otp_hash = hashlib.sha256(otp.encode()).hexdigest()

    pipe = redis.pipeline()
    pipe.set(otp_key, otp_hash, ex=OTP_TTL_SECONDS)
    pipe.set(attempts_key, 0, ex=OTP_TTL_SECONDS)
    pipe.incr(hour_key)
    pipe.expire(hour_key, 3600)
    pipe.incr(day_key)
    pipe.expire(day_key, 86400)
    pipe.set(cooldown_key, "1", ex=OTP_COOLDOWN_SECONDS)
    await pipe.execute()

    # --- Dispatch OTP via SMS gateway ---
    sms_backend = get_sms_backend()
    sent = await sms_backend.send_otp(phone, otp, purpose=purpose)

    if not sent:
        logger.error("otp.send_failed", phone=phone, purpose=purpose)
        # Don't expose SMS failure to client (security: don't reveal backend issues)
        # The OTP is in Redis; client can request resend after cooldown

    logger.info("otp.sent", phone=phone, purpose=purpose, ttl=OTP_TTL_SECONDS)

    return {
        "phone": phone,
        "purpose": purpose,
        "ttl_seconds": OTP_TTL_SECONDS,
        "cooldown_seconds": OTP_COOLDOWN_SECONDS,
        "max_attempts": OTP_VERIFY_MAX_ATTEMPTS,
        # In development with ConsoleSMSBackend, the OTP is logged to stdout
        # In production, we never return the OTP in the response
        "debug_otp": otp if settings().is_development else None,
    }


# ---------------------------------------------------------------------------
# OTP verify flow
# ---------------------------------------------------------------------------


async def verify_otp(
    db: AsyncSession,
    phone: str,
    otp: str,
    full_name: str | None = None,
    preferred_language: str = "en",
) -> TokenResponse:
    """Verify an OTP and return tokens (login existing user or signup new user).

    Raises:
    - ValidationError: OTP is wrong / expired / max attempts exceeded
    - AuthenticationError: account locked / deactivated
    """
    redis = await get_redis()
    otp_key = f"otp:{phone}:login"
    signup_otp_key = f"otp:{phone}:signup"
    attempts_key_prefix = f"otp:attempts:{phone}"

    # Check both login and signup OTP stores (we don't know which the user used)
    stored_hash = None
    active_purpose = None
    for purpose in ("login", "signup"):
        h = await redis.get(f"otp:{phone}:{purpose}")
        if h:
            stored_hash = h
            active_purpose = purpose
            break

    if not stored_hash:
        raise ValidationError("OTP has expired or was not requested. Please request a new OTP.")

    # Check attempt count
    attempts_key = f"{attempts_key_prefix}:{active_purpose}"
    attempts = int(await redis.get(attempts_key) or 0)
    if attempts >= OTP_VERIFY_MAX_ATTEMPTS:
        # Invalidate the OTP — too many attempts
        await redis.delete(f"otp:{phone}:{active_purpose}")
        await redis.delete(attempts_key)
        raise ValidationError(
            "Maximum OTP verification attempts exceeded. Please request a new OTP."
        )

    # Verify OTP
    provided_hash = hashlib.sha256(otp.encode()).hexdigest()
    if provided_hash != stored_hash:
        # Increment attempts
        await redis.incr(attempts_key)
        remaining = OTP_VERIFY_MAX_ATTEMPTS - (attempts + 1)
        raise ValidationError(
            f"Invalid OTP. {remaining} attempt(s) remaining."
            if remaining > 0
            else "Invalid OTP. Maximum attempts exceeded. Please request a new OTP."
        )

    # OTP verified — clean up Redis
    await redis.delete(f"otp:{phone}:{active_purpose}")
    await redis.delete(attempts_key)

    # --- Lookup or create user ---
    user = await repo.get_user_by_phone(db, phone)
    if user is None:
        # New user — signup flow
        if active_purpose == "login":
            # User tried to login but doesn't exist — auto-convert to signup
            # This is a UX choice; alternatively raise NotFoundError
            pass

        if not full_name:
            raise ValidationError("Full name is required for new user signup.")

        user = await repo.create_user(
            db,
            phone=phone,
            full_name=full_name,
            preferred_language=preferred_language,
            phone_verified=True,
        )
        logger.info("user.created", user_id=str(user.id), phone=phone, role=user.role)
    else:
        # Existing user — login flow
        if not user.is_active:
            raise AuthenticationError("Account is deactivated. Contact support.")

        if user.is_locked:
            raise AuthenticationError(
                "Account is temporarily locked due to too many failed login attempts. "
                "Try again later or contact support."
            )

        # Update preferred_language if user changed it
        if preferred_language != user.preferred_language:
            await repo.update_user(
                db, user.id, preferred_language=preferred_language
            )

    # --- Reset failed login counter ---
    await repo.reset_failed_login(db, user.id)

    # --- Update last login ---
    await repo.update_last_login(db, user.id)

    # --- Issue tokens ---
    return await _issue_tokens(db, user)


# ---------------------------------------------------------------------------
# Token issuance
# ---------------------------------------------------------------------------


async def _issue_tokens(
    db: AsyncSession,
    user: User,
    device_info: str | None = None,
    ip_address: str | None = None,
) -> TokenResponse:
    """Issue access + refresh tokens for a user.

    The refresh token is persisted to the database (hashed) for revocation
    tracking. The access token is stateless (not persisted).
    """
    access_token = create_access_token(
        user_id=user.id,
        role=user.role.value,
        extra_claims={
            "name": user.full_name,
            "lang": user.preferred_language,
        },
    )
    refresh_token, jti = create_refresh_token(user.id)

    # Persist refresh token
    token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(
        days=settings().JWT_REFRESH_TOKEN_EXPIRE_DAYS
    )

    await repo.create_refresh_token(
        db,
        user_id=user.id,
        token_hash=token_hash,
        jti=jti,
        expires_at=expires_at,
        device_info=device_info,
        ip_address=ip_address,
    )

    logger.info(
        "tokens.issued",
        user_id=str(user.id),
        role=user.role.value,
        jti=jti,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings().JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserPublic.model_validate(user),
    )


# ---------------------------------------------------------------------------
# Refresh token flow (with rotation)
# ---------------------------------------------------------------------------


async def refresh_access_token(
    db: AsyncSession,
    refresh_token: str,
    device_info: str | None = None,
    ip_address: str | None = None,
) -> TokenResponse:
    """Exchange a refresh token for a new access + refresh token pair.

    Implements refresh token rotation:
    1. Decode the refresh token (validates signature and expiration)
    2. Look up the jti in the database
    3. If the token is revoked, raise error (token reuse detected → revoke all)
    4. If the token is valid, revoke it and issue a new pair
    5. Return new tokens

    If a revoked token is presented, the entire session family is revoked
    (suspected token theft).
    """
    # Decode the refresh token (will raise AuthenticationError if invalid)
    payload = decode_token(refresh_token, expected_type="refresh")
    jti = payload.get("jti")
    user_id_str = payload.get("sub")

    if not jti or not user_id_str:
        raise AuthenticationError("Malformed refresh token")

    from uuid import UUID

    user_id = UUID(user_id_str)

    # Look up the stored token
    stored_token = await repo.get_refresh_token_by_jti(db, jti)
    if not stored_token:
        # Token not in DB — either it was never issued (forged) or already
        # cleaned up. Either way, treat as invalid.
        raise AuthenticationError("Refresh token not recognized")

    # --- Token reuse detection ---
    if stored_token.is_revoked:
        # CRITICAL: A revoked token is being used. This means:
        # 1. The token was stolen and the legitimate user already rotated
        # 2. Or the legitimate user is trying to reuse an old token
        # Either way, revoke ALL tokens for this user (defensive)
        logger.warning(
            "refresh_token.reuse_detected",
            user_id=user_id_str,
            jti=jti,
            revoked_reason=stored_token.revoked_reason,
        )
        await repo.revoke_all_user_tokens(
            db, user_id, reason="suspected_theft"
        )
        raise AuthenticationError(
            "Refresh token has been revoked. Please log in again."
        )

    # --- Verify the token hash matches ---
    provided_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
    if provided_hash != stored_token.token_hash:
        # Token signature is valid but hash doesn't match — suspicious
        logger.warning(
            "refresh_token.hash_mismatch",
            user_id=user_id_str,
            jti=jti,
        )
        raise AuthenticationError("Refresh token validation failed")

    # --- Check user is still valid ---
    user = await repo.get_user_by_id(db, user_id)
    if not user or not user.is_active:
        raise AuthenticationError("User account is not active")

    if user.is_locked:
        raise AuthenticationError("Account is temporarily locked")

    # --- Rotate: revoke old token, issue new pair ---
    await repo.revoke_refresh_token(db, jti, reason="rotation")

    return await _issue_tokens(
        db, user, device_info=device_info, ip_address=ip_address
    )


# ---------------------------------------------------------------------------
# Logout flow
# ---------------------------------------------------------------------------


async def logout(db: AsyncSession, refresh_token: str) -> None:
    """Revoke a refresh token (logout).

    Idempotent — calling logout with an already-revoked token is a no-op.
    """
    try:
        payload = decode_token(refresh_token, expected_type="refresh")
    except AuthenticationError:
        # Token is invalid/expired — nothing to revoke
        logger.info("logout.invalid_token")
        return

    jti = payload.get("jti")
    if jti:
        await repo.revoke_refresh_token(db, jti, reason="logout")
        logger.info("logout.success", jti=jti)


async def logout_all_sessions(db: AsyncSession, user_id) -> None:
    """Revoke all active refresh tokens for a user (force logout all devices)."""
    from uuid import UUID

    count = await repo.revoke_all_user_tokens(
        db, UUID(str(user_id)), reason="logout_all"
    )
    logger.info("logout_all.success", user_id=str(user_id), revoked_count=count)


# ---------------------------------------------------------------------------
# Password-based login (alternative to OTP)
# ---------------------------------------------------------------------------


async def login_with_password(
    db: AsyncSession,
    phone_or_email: str,
    password: str,
    device_info: str | None = None,
    ip_address: str | None = None,
) -> TokenResponse:
    """Login with phone/email + password (alternative to OTP).

    Used by admin/officer accounts that have passwords set. Farmers typically
    use OTP-only auth.
    """
    from krishisetu.core.security import normalize_indian_phone, verify_password

    # Try phone first, then email
    user = None
    try:
        phone = normalize_indian_phone(phone_or_email)
        user = await repo.get_user_by_phone(db, phone)
    except ValueError:
        pass

    if not user and "@" in phone_or_email:
        user = await repo.get_user_by_email(db, phone_or_email)

    if not user:
        # Don't reveal whether user exists — uniform error message
        raise AuthenticationError("Invalid credentials")

    if not user.is_active:
        raise AuthenticationError("Account is deactivated")

    if user.is_locked:
        raise AuthenticationError(
            "Account is temporarily locked. Try again later or contact support."
        )

    if not user.password_hash:
        # User has no password set (OTP-only) — can't login with password
        raise AuthenticationError(
            "Password login is not enabled for this account. Use OTP login."
        )

    if not verify_password(password, user.password_hash):
        # Increment failed login count
        failed_count = await repo.increment_failed_login(db, user.id)

        if failed_count >= ACCOUNT_LOCKOUT_THRESHOLD:
            # Check if we should do extended lockout (3 lockouts in 24h)
            # For now, simple 15-minute lockout
            await repo.lock_account(
                db, user.id, ACCOUNT_LOCKOUT_DURATION_MINUTES
            )
            logger.warning(
                "account.locked",
                user_id=str(user.id),
                failed_count=failed_count,
            )
            raise AuthenticationError(
                "Account locked due to too many failed attempts. "
                f"Try again in {ACCOUNT_LOCKOUT_DURATION_MINUTES} minutes."
            )

        remaining = ACCOUNT_LOCKOUT_THRESHOLD - failed_count
        raise AuthenticationError(
            f"Invalid credentials. {remaining} attempt(s) remaining before account lock."
        )

    # --- Password verified ---
    await repo.reset_failed_login(db, user.id)
    await repo.update_last_login(db, user.id)

    return await _issue_tokens(db, user, device_info=device_info, ip_address=ip_address)
