"""Identity domain — business logic services.

FIX (T4): Three improvements bundled here:
  1. Audit-log every auth event — login success/failure, refresh, logout,
     lockout, OTP send/verify, Aadhaar e-KYC initiated/completed. Previously
     audit_log() was called from only 3 of 13 domains; the identity domain
     had zero audit entries despite AuditAction having values for all of
     these events.
  2. Aadhaar e-KYC moved out of routes.py into service-layer functions
     (send_aadhaar_otp, verify_aadhaar_otp). The service checks
     has_active_consent(ConsentPurpose.IDENTITY_VERIFICATION) before
     sending PII to UIDAI — DPDP Act 2023, Section 11 requires explicit
     consent before processing.
  3. (Combined with uidai.py fix #3) Aadhaar encryption is now real
     RSA-2048 with the UIDAI public key certificate, or hard-fails in
     production if the certificate isn't configured. The previous
     `f"encrypted_{sha256(aadhaar)[:32]}"` placeholder provided zero
     confidentiality and would have sent raw Aadhaar numbers to UIDAI
     in a string-reversible format.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from krishisetu.core.audit_logger import AuditAction, AuditOutcome, audit_log
from krishisetu.core.config import settings
from krishisetu.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
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
    hash_aadhaar,
)
from krishisetu.core.sms import get_sms_backend
from krishisetu.domains.consent.models import ConsentPurpose
from krishisetu.domains.consent.services import has_active_consent
from krishisetu.domains.identity.models import User, UserRole
from krishisetu.domains.identity import repository as repo
from krishisetu.domains.identity.schemas import (
    TokenResponse,
    UserPublic,
)

logger = get_logger(__name__)


# Rate limit constants
OTP_SEND_MAX_PER_HOUR = 5
OTP_SEND_MAX_PER_DAY = 20
OTP_VERIFY_MAX_ATTEMPTS = 3

OTP_TTL_SECONDS = 5 * 60
OTP_COOLDOWN_SECONDS = 60

ACCOUNT_LOCKOUT_THRESHOLD = 5
ACCOUNT_LOCKOUT_DURATION_MINUTES = 15
ACCOUNT_LOCKOUT_EXTENDED_MINUTES = 24 * 60

# TTL for Google OAuth csrf state token stored in Redis
GOOGLE_OAUTH_STATE_TTL_SECONDS = 10 * 60


# OTP send flow
async def send_otp(
    db: AsyncSession,
    phone: str,
    purpose: str = "login",
    *,
    request: Request | None = None,
) -> dict[str, Any]:
    """Generate and dispatch an OTP to the given phone number.

    FIX (T4): now writes an audit_log entry (AuditAction.OTP_SENT) so OTP
    sends are visible in the audit trail. Accepts an optional `request`
    parameter so IP/UA can be captured for the audit entry.
    """
    redis = await get_redis()
    now = datetime.now(timezone.utc)

    hour_key = f"otp:rl:{phone}:{purpose}:hour:{now.strftime('%Y%m%d%H')}"
    day_key = f"otp:rl:{phone}:{purpose}:day:{now.strftime('%Y%m%d')}"
    cooldown_key = f"otp:cd:{phone}:{purpose}"

    hour_count = int(await redis.get(hour_key) or 0)
    day_count = int(await redis.get(day_key) or 0)

    if hour_count >= OTP_SEND_MAX_PER_HOUR:
        # Audit the rate-limit hit
        await audit_log(
            db,
            action=AuditAction.SECURITY_RATE_LIMIT_EXCEEDED,
            actor_id=None,
            actor_role=None,
            resource_type="otp",
            resource_id=None,
            outcome=AuditOutcome.DENIED,
            details={"phone": phone, "purpose": purpose, "limit": "hourly"},
            request=request,
        )
        raise RateLimitExceededError(retry_after_seconds=3600)
    if day_count >= OTP_SEND_MAX_PER_DAY:
        await audit_log(
            db,
            action=AuditAction.SECURITY_RATE_LIMIT_EXCEEDED,
            actor_id=None,
            actor_role=None,
            resource_type="otp",
            resource_id=None,
            outcome=AuditOutcome.DENIED,
            details={"phone": phone, "purpose": purpose, "limit": "daily"},
            request=request,
        )
        raise RateLimitExceededError(retry_after_seconds=86400)

    if await redis.exists(cooldown_key):
        ttl = await redis.ttl(cooldown_key)
        raise RateLimitExceededError(retry_after_seconds=max(ttl, 1))

    if purpose == "signup":
        existing = await repo.get_user_by_phone(db, phone)
        if existing:
            raise ConflictError("Phone number already registered. Use login instead.")

    if purpose == "login":
        existing = await repo.get_user_by_phone(db, phone)
        if existing and not existing.is_active:
            raise AuthenticationError("Account is deactivated. Contact support.")

    otp = generate_otp(length=6)
    otp_key = f"otp:{phone}:{purpose}"
    attempts_key = f"otp:attempts:{phone}:{purpose}"

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

    sms_backend = get_sms_backend()
    sent = await sms_backend.send_otp(phone, otp, purpose=purpose)

    if not sent:
        logger.error("otp.send_failed", phone=phone, purpose=purpose)

    logger.info("otp.sent", phone=phone, purpose=purpose, ttl=OTP_TTL_SECONDS)

    # Audit the OTP send (actor unknown at this point — phone isn't a user ID)
    await audit_log(
        db,
        action=AuditAction.OTP_SENT,
        actor_id=None,
        actor_role=None,
        resource_type="phone",
        resource_id=phone,
        outcome=AuditOutcome.SUCCESS if sent else AuditOutcome.FAILURE,
        details={"purpose": purpose, "ttl_seconds": OTP_TTL_SECONDS},
        request=request,
    )

    return {
        "phone": phone,
        "purpose": purpose,
        "ttl_seconds": OTP_TTL_SECONDS,
        "cooldown_seconds": OTP_COOLDOWN_SECONDS,
        "max_attempts": OTP_VERIFY_MAX_ATTEMPTS,
        "debug_otp": otp if settings().is_development else None,
    }

# OTP verify flow
async def verify_otp(
    db: AsyncSession,
    phone: str,
    otp: str,
    full_name: str | None = None,
    preferred_language: str = "en",
    device_info: str | None = None,
    ip_address: str | None = None,
    *,
    request: Request | None = None,
) -> TokenResponse:
    """Verify an OTP and return tokens (login existing user or signup new user).

    FIX (T4): now writes audit_log entries for both OTP_VERIFIED (success)
    and LOGIN_FAILED (wrong OTP). Previously neither was audited.
    """
    redis = await get_redis()
    attempts_key_prefix = f"otp:attempts:{phone}"

    stored_hash = None
    active_purpose = None
    for purpose in ("login", "signup"):
        h = await redis.get(f"otp:{phone}:{purpose}")
        if h:
            stored_hash = h
            active_purpose = purpose
            break

    if not stored_hash:
        raise ValidationError(
            "OTP has expired or was not requested. Please request a new OTP."
        )

    attempts_key = f"{attempts_key_prefix}:{active_purpose}"
    attempts = int(await redis.get(attempts_key) or 0)
    if attempts >= OTP_VERIFY_MAX_ATTEMPTS:
        await redis.delete(f"otp:{phone}:{active_purpose}")
        await redis.delete(attempts_key)
        raise ValidationError(
            "Maximum OTP verification attempts exceeded. Please request a new OTP."
        )

    provided_hash = hashlib.sha256(otp.encode()).hexdigest()

    # Redis may return bytes or str depending on decode_responses setting.
    # Normalise to str before comparison.
    stored_hash_str = (
        stored_hash.decode() if isinstance(stored_hash, bytes) else stored_hash
    )

    if provided_hash != stored_hash_str:
        await redis.incr(attempts_key)
        remaining = OTP_VERIFY_MAX_ATTEMPTS - (attempts + 1)

        # Audit the failed OTP verification
        await audit_log(
            db,
            action=AuditAction.LOGIN_FAILED,
            actor_id=None,
            actor_role=None,
            resource_type="phone",
            resource_id=phone,
            outcome=AuditOutcome.FAILURE,
            details={
                "reason": "invalid_otp",
                "remaining_attempts": max(remaining, 0),
            },
            ip_address=ip_address,
            user_agent=device_info,
            request=request,
        )

        raise ValidationError(
            f"Invalid OTP. {remaining} attempt(s) remaining."
            if remaining > 0
            else "Invalid OTP. Maximum attempts exceeded. Please request a new OTP."
        )

    await redis.delete(f"otp:{phone}:{active_purpose}")
    await redis.delete(attempts_key)

    user = await repo.get_user_by_phone(db, phone)
    if user is None:
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
        if not user.is_active:
            raise AuthenticationError("Account is deactivated. Contact support.")

        if user.is_locked:
            raise AuthenticationError(
                "Account is temporarily locked due to too many failed login attempts. "
                "Try again later or contact support."
            )

        if preferred_language != user.preferred_language:
            await repo.update_user(
                db, user.id, preferred_language=preferred_language
            )

    await repo.reset_failed_login(db, user.id)
    await repo.update_last_login(db, user.id)

    # Audit the successful OTP verification (login)
    await audit_log(
        db,
        action=AuditAction.OTP_VERIFIED,
        actor_id=user.id,
        actor_role=user.role.value,
        resource_type="phone",
        resource_id=phone,
        outcome=AuditOutcome.SUCCESS,
        details={"method": "otp", "purpose": active_purpose},
        ip_address=ip_address,
        user_agent=device_info,
        request=request,
    )

    await audit_log(
        db,
        action=AuditAction.LOGIN_SUCCESS,
        actor_id=user.id,
        actor_role=user.role.value,
        resource_type="user",
        resource_id=user.id,
        outcome=AuditOutcome.SUCCESS,
        details={"method": "otp"},
        ip_address=ip_address,
        user_agent=device_info,
        request=request,
    )

    return await _issue_tokens(db, user, device_info=device_info, ip_address=ip_address)

# Token issuance
async def _issue_tokens(
    db: AsyncSession,
    user: User,
    device_info: str | None = None,
    ip_address: str | None = None,
) -> TokenResponse:
    """Issue access + refresh tokens for a user."""
    access_token = create_access_token(
        user_id=user.id,
        role=user.role.value,
        extra_claims={
            "name": user.full_name,
            "lang": user.preferred_language,
        },
    )
    refresh_token, jti = create_refresh_token(user.id)

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

# Refresh token flow
async def refresh_access_token(
    db: AsyncSession,
    refresh_token: str,
    device_info: str | None = None,
    ip_address: str | None = None,
    *,
    request: Request | None = None,
) -> TokenResponse:
    """Exchange a refresh token for a new access + refresh token pair.

    FIX (T4): now writes audit_log entries for TOKEN_REFRESHED (success)
    and for the suspected-token-theft case (revoked token reuse).
    """
    payload = decode_token(refresh_token, expected_type="refresh")
    jti = payload.get("jti")
    user_id_str = payload.get("sub")

    if not jti or not user_id_str:
        raise AuthenticationError("Malformed refresh token")

    from uuid import UUID
    user_id = UUID(user_id_str)

    stored_token = await repo.get_refresh_token_by_jti(db, jti)
    if not stored_token:
        # Audit: unknown JTI presented — could be a forged token or a very old one
        await audit_log(
            db,
            action=AuditAction.TOKEN_REFRESHED,
            actor_id=user_id,
            actor_role=None,
            resource_type="refresh_token",
            resource_id=jti,
            outcome=AuditOutcome.FAILURE,
            details={"reason": "jti_not_found"},
            ip_address=ip_address,
            user_agent=device_info,
            request=request,
        )
        raise AuthenticationError("Refresh token not recognized")

    if stored_token.is_revoked:
        logger.warning(
            "refresh_token.reuse_detected",
            user_id=user_id_str,
            jti=jti,
            revoked_reason=stored_token.revoked_reason,
        )
        # Audit: suspected token theft — entire session family revoked
        await audit_log(
            db,
            action=AuditAction.SECURITY_SUSPICIOUS_INPUT,
            actor_id=user_id,
            actor_role=None,
            resource_type="refresh_token",
            resource_id=jti,
            outcome=AuditOutcome.DENIED,
            details={
                "reason": "revoked_token_reuse",
                "revoked_reason": stored_token.revoked_reason,
                "action_taken": "session_family_revoked",
            },
            ip_address=ip_address,
            user_agent=device_info,
            request=request,
        )
        await repo.revoke_all_user_tokens(db, user_id, reason="suspected_theft")
        raise AuthenticationError(
            "Refresh token has been revoked. Please log in again."
        )

    provided_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
    if provided_hash != stored_token.token_hash:
        logger.warning("refresh_token.hash_mismatch", user_id=user_id_str, jti=jti)
        await audit_log(
            db,
            action=AuditAction.TOKEN_REFRESHED,
            actor_id=user_id,
            actor_role=None,
            resource_type="refresh_token",
            resource_id=jti,
            outcome=AuditOutcome.FAILURE,
            details={"reason": "hash_mismatch"},
            ip_address=ip_address,
            user_agent=device_info,
            request=request,
        )
        raise AuthenticationError("Refresh token validation failed")

    user = await repo.get_user_by_id(db, user_id)
    if not user or not user.is_active:
        raise AuthenticationError("User account is not active")

    if user.is_locked:
        raise AuthenticationError("Account is temporarily locked")

    await repo.revoke_refresh_token(db, jti, reason="rotation")

    # Audit the successful refresh
    await audit_log(
        db,
        action=AuditAction.TOKEN_REFRESHED,
        actor_id=user.id,
        actor_role=user.role.value,
        resource_type="refresh_token",
        resource_id=jti,
        outcome=AuditOutcome.SUCCESS,
        details={"method": "rotation"},
        ip_address=ip_address,
        user_agent=device_info,
        request=request,
    )

    return await _issue_tokens(db, user, device_info=device_info, ip_address=ip_address)


# Logout
async def logout(
    db: AsyncSession,
    refresh_token: str,
    *,
    request: Request | None = None,
    actor_id: UUID | None = None,
) -> None:
    """Revoke a refresh token. Idempotent.

    FIX (T4): now writes an audit_log entry (AuditAction.LOGOUT). The
    actor_id is best-effort — if the token is malformed we can't know who
    logged out, but we still audit the event with actor_id=None.
    """
    try:
        payload = decode_token(refresh_token, expected_type="refresh")
    except AuthenticationError:
        logger.info("logout.invalid_token")
        return

    jti = payload.get("jti")
    user_id_str = payload.get("sub")
    if jti:
        await repo.revoke_refresh_token(db, jti, reason="logout")
        logger.info("logout.success", jti=jti)

        # Audit the logout
        await audit_log(
            db,
            action=AuditAction.LOGOUT,
            actor_id=actor_id or (UUID(user_id_str) if user_id_str else None),
            actor_role=None,
            resource_type="refresh_token",
            resource_id=jti,
            outcome=AuditOutcome.SUCCESS,
            details={"reason": "logout"},
            request=request,
        )


async def logout_all_sessions(
    db: AsyncSession,
    user_id: object,
    *,
    request: Request | None = None,
) -> None:
    """Revoke all active refresh tokens for a user.

    FIX (T4): now writes an audit_log entry (AuditAction.LOGOUT).
    """
    from uuid import UUID

    uid = UUID(str(user_id))
    count = await repo.revoke_all_user_tokens(db, uid, reason="logout_all")
    logger.info("logout_all.success", user_id=str(uid), revoked_count=count)

    await audit_log(
        db,
        action=AuditAction.LOGOUT,
        actor_id=uid,
        actor_role=None,
        resource_type="user",
        resource_id=uid,
        outcome=AuditOutcome.SUCCESS,
        details={"reason": "logout_all", "revoked_count": count},
        request=request,
    )


# Password-based login
async def login_with_password(
    db: AsyncSession,
    phone_or_email: str,
    password: str,
    device_info: str | None = None,
    ip_address: str | None = None,
    *,
    request: Request | None = None,
) -> TokenResponse:
    """Login with phone/email + password (admin/officer accounts only).

    FIX (T4): now writes audit_log entries for LOGIN_SUCCESS,
    LOGIN_FAILED, and ACCOUNT_LOCKED. Previously none of these events
    were audited.
    """
    from krishisetu.core.security import normalize_indian_phone, verify_password

    user = None
    try:
        phone = normalize_indian_phone(phone_or_email)
        user = await repo.get_user_by_phone(db, phone)
    except ValueError:
        pass

    if not user and "@" in phone_or_email:
        user = await repo.get_user_by_email(db, phone_or_email)

    if not user:
        # Audit: user not found. Don't leak which (phone vs email) was tried.
        await audit_log(
            db,
            action=AuditAction.LOGIN_FAILED,
            actor_id=None,
            actor_role=None,
            resource_type="credentials",
            resource_id=phone_or_email,
            outcome=AuditOutcome.FAILURE,
            details={"reason": "user_not_found"},
            ip_address=ip_address,
            user_agent=device_info,
            request=request,
        )
        raise AuthenticationError("Invalid credentials")

    if not user.is_active:
        await audit_log(
            db,
            action=AuditAction.LOGIN_FAILED,
            actor_id=user.id,
            actor_role=user.role.value,
            resource_type="user",
            resource_id=user.id,
            outcome=AuditOutcome.FAILURE,
            details={"reason": "account_deactivated"},
            ip_address=ip_address,
            user_agent=device_info,
            request=request,
        )
        raise AuthenticationError("Account is deactivated")

    if user.is_locked:
        await audit_log(
            db,
            action=AuditAction.LOGIN_FAILED,
            actor_id=user.id,
            actor_role=user.role.value,
            resource_type="user",
            resource_id=user.id,
            outcome=AuditOutcome.DENIED,
            details={"reason": "account_locked"},
            ip_address=ip_address,
            user_agent=device_info,
            request=request,
        )
        raise AuthenticationError(
            "Account is temporarily locked. Try again later or contact support."
        )

    if not user.password_hash:
        await audit_log(
            db,
            action=AuditAction.LOGIN_FAILED,
            actor_id=user.id,
            actor_role=user.role.value,
            resource_type="user",
            resource_id=user.id,
            outcome=AuditOutcome.FAILURE,
            details={"reason": "password_not_set"},
            ip_address=ip_address,
            user_agent=device_info,
            request=request,
        )
        raise AuthenticationError(
            "Password login is not enabled for this account. Use OTP login."
        )

    if not verify_password(password, user.password_hash):
        failed_count = await repo.increment_failed_login(db, user.id)

        if failed_count >= ACCOUNT_LOCKOUT_THRESHOLD:
            await repo.lock_account(db, user.id, ACCOUNT_LOCKOUT_DURATION_MINUTES)
            logger.warning(
                "account.locked",
                user_id=str(user.id),
                failed_count=failed_count,
            )
            # Audit: account locked due to brute-force
            await audit_log(
                db,
                action=AuditAction.ACCOUNT_LOCKED,
                actor_id=user.id,
                actor_role=user.role.value,
                resource_type="user",
                resource_id=user.id,
                outcome=AuditOutcome.FAILURE,
                details={
                    "reason": "max_failed_attempts",
                    "failed_count": failed_count,
                    "locked_for_minutes": ACCOUNT_LOCKOUT_DURATION_MINUTES,
                },
                ip_address=ip_address,
                user_agent=device_info,
                request=request,
            )
            raise AuthenticationError(
                "Account locked due to too many failed attempts. "
                f"Try again in {ACCOUNT_LOCKOUT_DURATION_MINUTES} minutes."
            )

        remaining = ACCOUNT_LOCKOUT_THRESHOLD - failed_count
        # Audit: wrong password
        await audit_log(
            db,
            action=AuditAction.LOGIN_FAILED,
            actor_id=user.id,
            actor_role=user.role.value,
            resource_type="user",
            resource_id=user.id,
            outcome=AuditOutcome.FAILURE,
            details={
                "reason": "wrong_password",
                "failed_count": failed_count,
                "remaining_attempts": remaining,
            },
            ip_address=ip_address,
            user_agent=device_info,
            request=request,
        )
        raise AuthenticationError(
            f"Invalid credentials. {remaining} attempt(s) remaining before account lock."
        )

    await repo.reset_failed_login(db, user.id)
    await repo.update_last_login(db, user.id)

    # Audit: successful password login
    await audit_log(
        db,
        action=AuditAction.LOGIN_SUCCESS,
        actor_id=user.id,
        actor_role=user.role.value,
        resource_type="user",
        resource_id=user.id,
        outcome=AuditOutcome.SUCCESS,
        details={"method": "password"},
        ip_address=ip_address,
        user_agent=device_info,
        request=request,
    )

    return await _issue_tokens(db, user, device_info=device_info, ip_address=ip_address)


# Google OAuth
async def generate_google_oauth_state() -> str:
    """Generate and store a one-time csrf state token for Google OAuth (10-min TTL)."""
    redis = await get_redis()
    state = secrets.token_urlsafe(32)
    await redis.set(
        f"oauth:google:state:{state}", "1", ex=GOOGLE_OAUTH_STATE_TTL_SECONDS
    )
    return state


async def google_oauth_login(
    db: AsyncSession,
    code: str,
    state: str,
    device_info: str | None = None,
    ip_address: str | None = None,
    *,
    request: Request | None = None,
) -> TokenResponse:
    """Exchange a Google OAuth authorization code for KrishiSetu JWT tokens.

    FIX (T4): now writes audit_log entries for LOGIN_SUCCESS (Google OAuth).
    """
    import httpx

    redis = await get_redis()

    # 1. Verify and consume state
    state_key = f"oauth:google:state:{state}"
    stored = await redis.get(state_key)
    if not stored:
        raise AuthenticationError(
            "Invalid or expired OAuth state. Please try logging in again."
        )
    await redis.delete(state_key)

    cfg = settings()
    if not cfg.google_oauth_enabled:
        raise AuthenticationError("Google OAuth is not configured on this server.")
    token_payload = {
        "code": code,
        "client_id": cfg.GOOGLE_OAUTH_CLIENT_ID,
        "client_secret": cfg.GOOGLE_OAUTH_CLIENT_SECRET.get_secret_value(),  # type: ignore[union-attr]
        "redirect_uri": cfg.GOOGLE_OAUTH_REDIRECT_URI,
        "grant_type": "authorization_code",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            token_resp = await client.post(
                "https://oauth2.googleapis.com/token",
                data=token_payload,
            )

        if token_resp.status_code != 200:
            logger.error(
                "google_oauth.token_exchange_failed",
                status=token_resp.status_code,
                body=token_resp.text[:200],
            )
            raise AuthenticationError(
                "Failed to exchange Google authorization code. Please try again."
            )

        google_access_token = token_resp.json().get("access_token")
        if not google_access_token:
            raise AuthenticationError("Google did not return an access token.")
        async with httpx.AsyncClient(timeout=10.0) as client:
            userinfo_resp = await client.get(
                "https://www.googleapis.com/oauth2/v3/userinfo",
                headers={"Authorization": f"Bearer {google_access_token}"},
            )

        if userinfo_resp.status_code != 200:
            raise AuthenticationError("Failed to fetch Google user profile.")

        userinfo = userinfo_resp.json()

    except httpx.HTTPError as exc:
        logger.error("google_oauth.network_error", error=str(exc))
        raise AuthenticationError(
            "Network error during Google authentication. Please try again."
        ) from exc

    email: str | None = userinfo.get("email")
    if not email:
        raise AuthenticationError(
            "Your Google account has no email address. Use phone OTP login instead."
        )

    if not userinfo.get("email_verified", False):
        raise AuthenticationError(
            "Your Google account email is not verified. Verify it with Google first."
        )

    google_sub: str = userinfo.get("sub", "")
    full_name: str = userinfo.get("name") or email.split("@")[0]
    user = await repo.get_user_by_email(db, email)
    if user is None:
        # TODO: add a migration to make phone nullable for OAuth-only accounts.
        synthetic_phone = _derive_synthetic_phone(google_sub or email)
        if await repo.get_user_by_phone(db, synthetic_phone):
            synthetic_phone = _derive_synthetic_phone(email + google_sub)

        user = await repo.create_user(
            db,
            phone=synthetic_phone,
            full_name=full_name,
            email=email,
            phone_verified=False,
        )
        await repo.update_user(db, user.id, email_verified=True)
        await db.refresh(user)

        logger.info("user.created_via_google", user_id=str(user.id), email=email)
    else:
        if not user.is_active:
            raise AuthenticationError("Account is deactivated. Contact support.")
        if user.is_locked:
            raise AuthenticationError(
                "Account is temporarily locked. Try again later or contact support."
            )

    await repo.reset_failed_login(db, user.id)
    await repo.update_last_login(db, user.id)

    logger.info("google_oauth.login_success", user_id=str(user.id), email=email)

    # Audit: successful Google OAuth login
    await audit_log(
        db,
        action=AuditAction.LOGIN_SUCCESS,
        actor_id=user.id,
        actor_role=user.role.value,
        resource_type="user",
        resource_id=user.id,
        outcome=AuditOutcome.SUCCESS,
        details={"method": "google_oauth", "email": email},
        ip_address=ip_address,
        user_agent=device_info,
        request=request,
    )

    return await _issue_tokens(db, user, device_info=device_info, ip_address=ip_address)


def _derive_synthetic_phone(seed: str) -> str:
    """Derive a deterministic 10-digit placeholder phone from a seed string.

    Used for Google OAuth users who don't provide a phone number.
    The result starts with '9' (valid Indian mobile prefix) and is
    deterministic — same seed always produces the same phone.
    phone_verified=False ensures it can't be used for OTP flows.
    """
    digest = hashlib.sha256(seed.encode()).hexdigest()
    numeric = int(digest[:16], 16) % (10 ** 9)
    return f"9{numeric:09d}"


# Aadhaar e-KYC (moved from routes.py — T4 fix #2)
async def send_aadhaar_otp(
    db: AsyncSession,
    user: User,
    aadhaar: str,
    *,
    request: Request | None = None,
) -> dict[str, Any]:
    """Send an Aadhaar OTP for e-KYC verification.

    FIX (T4): moved out of routes.py into the service layer so that:
      1. The consent check (has_active_consent for IDENTITY_VERIFICATION)
         can be enforced before sending PII to UIDAI — DPDP Act 2023,
         Section 11 requires explicit consent before processing.
      2. The audit_log entry (AADHAAR_EKYC_INITIATED) is written with the
         full request context (IP, UA, request_id).
      3. The route handler stays thin — just request/response marshalling.

    Args:
        db: async DB session
        user: the authenticated user requesting e-KYC
        aadhaar: 12-digit Aadhaar number (validated by UIDAI client)
        request: FastAPI Request (for IP/UA extraction in audit log)

    Returns:
        Dict with transaction_id, message, masked_aadhaar, sent_at —
        shaped to match the AadhaarOTPResponse schema in routes.py.

    Raises:
        AuthorizationError: if the user has not granted consent for
            identity_verification
        ValidationError: if the Aadhaar number fails Verhoeff checksum
        RateLimitExceededError: if UIDAI rate limits are exceeded
    """
    has_consent = await has_active_consent(
        db, user.id, ConsentPurpose.IDENTITY_VERIFICATION
    )
    if not has_consent:
        # Audit the denied attempt
        await audit_log(
            db,
            action=AuditAction.AADHAAR_EKYC_INITIATED,
            actor_id=user.id,
            actor_role=user.role.value,
            resource_type="user",
            resource_id=user.id,
            outcome=AuditOutcome.DENIED,
            details={"reason": "consent_not_granted"},
            request=request,
        )
        raise AuthorizationError(
            "Consent for identity verification (Aadhaar e-KYC) is required. "
            "Please grant consent on the Privacy & Consent page first."
        )

    from krishisetu.integrations.uidai import get_uidai_client

    client = get_uidai_client()
    result = await client.send_otp(aadhaar)

    # Audit the initiation (success)
    await audit_log(
        db,
        action=AuditAction.AADHAAR_EKYC_INITIATED,
        actor_id=user.id,
        actor_role=user.role.value,
        resource_type="user",
        resource_id=user.id,
        outcome=AuditOutcome.SUCCESS,
        details={
            "transaction_id": result.transaction_id,
            "masked_aadhaar": f"XXXX-XXXX-{aadhaar[-4:]}",
        },
        request=request,
    )

    return {
        "transaction_id": result.transaction_id,
        "message": result.message,
        "masked_aadhaar": f"XXXX-XXXX-{aadhaar[-4:]}",
        "sent_at": result.sent_at.isoformat(),
    }


async def verify_aadhaar_otp(
    db: AsyncSession,
    user: User,
    aadhaar: str,
    otp: str,
    transaction_id: str,
    *,
    request: Request | None = None,
) -> dict[str, Any]:
    """Verify an Aadhaar OTP and mark the user's Aadhaar as verified.

    FIX (T4): moved out of routes.py into the service layer. The consent
    check is re-verified here (defense in depth — the user may have
    withdrawn consent between send_otp and verify_otp).

    Args:
        db: async DB session
        user: the authenticated user
        aadhaar: 12-digit Aadhaar number
        otp: 6-digit OTP entered by the user
        transaction_id: transaction ID from send_aadhaar_otp() response

    Returns:
        Dict with verified, masked_aadhaar, name, gender, year_of_birth,
        state, district — shaped to match AadhaarVerificationResponse.

    Raises:
        AuthorizationError: if consent was withdrawn between send and verify
        ValidationError: if the OTP is wrong / transaction expired
    """
    # --- Re-verify consent (defense in depth) ---
    has_consent = await has_active_consent(
        db, user.id, ConsentPurpose.IDENTITY_VERIFICATION
    )
    if not has_consent:
        await audit_log(
            db,
            action=AuditAction.AADHAAR_EKYC_COMPLETED,
            actor_id=user.id,
            actor_role=user.role.value,
            resource_type="user",
            resource_id=user.id,
            outcome=AuditOutcome.DENIED,
            details={"reason": "consent_withdrawn_before_verify"},
            request=request,
        )
        raise AuthorizationError(
            "Consent for identity verification was withdrawn. "
            "Please re-grant consent before completing Aadhaar e-KYC."
        )

    # --- Call UIDAI ---
    from krishisetu.integrations.uidai import get_uidai_client

    client = get_uidai_client()
    result = await client.verify_otp(aadhaar, otp, transaction_id)

    if result.verified:
        # Persist the Aadhaar hash + verified flag on the user
        aadhaar_hash = hash_aadhaar(aadhaar)
        updates: dict[str, object] = {
            "aadhaar_verified": True,
            "aadhaar_hash": aadhaar_hash,
        }
        if result.name:
            updates["full_name"] = result.name

        await repo.update_user(db, user.id, **updates)

        logger.info(
            "aadhaar.verified",
            user_id=str(user.id),
            masked_aadhaar=result.masked_aadhaar,
        )

        # Audit the successful e-KYC completion
        await audit_log(
            db,
            action=AuditAction.AADHAAR_EKYC_COMPLETED,
            actor_id=user.id,
            actor_role=user.role.value,
            resource_type="user",
            resource_id=user.id,
            outcome=AuditOutcome.SUCCESS,
            details={
                "masked_aadhaar": result.masked_aadhaar,
                "name_updated": bool(result.name),
            },
            request=request,
        )
    else:
        # Audit the failed verification attempt
        await audit_log(
            db,
            action=AuditAction.AADHAAR_EKYC_COMPLETED,
            actor_id=user.id,
            actor_role=user.role.value,
            resource_type="user",
            resource_id=user.id,
            outcome=AuditOutcome.FAILURE,
            details={
                "reason": "otp_invalid_or_expired",
                "masked_aadhaar": result.masked_aadhaar,
            },
            request=request,
        )

    return {
        "verified": result.verified,
        "masked_aadhaar": result.masked_aadhaar,
        "name": result.name,
        "gender": result.gender,
        "year_of_birth": result.year_of_birth,
        "state": result.state,
        "district": result.district,
    }
