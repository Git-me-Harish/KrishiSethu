"""Identity domain — business logic services."""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from krishisetu.core.config import settings
from krishisetu.core.exceptions import (
    AuthenticationError,
    RateLimitExceededError,
    ValidationError,
)
from krishisetu.core.logging import get_logger
from krishisetu.core.rate_limiter import check_ip_rate_limit
from krishisetu.core.redis import get_redis
from krishisetu.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_otp,
)
from krishisetu.core.sms import ConsoleSMSBackend, get_sms_backend
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

OTP_SEND_MAX_PER_HOUR = 5
OTP_SEND_MAX_PER_DAY = 20
OTP_VERIFY_MAX_ATTEMPTS = 3

OTP_TTL_SECONDS = 5 * 60
OTP_COOLDOWN_SECONDS = 60

ACCOUNT_LOCKOUT_THRESHOLD = 5
ACCOUNT_LOCKOUT_DURATION_MINUTES = 15
ACCOUNT_LOCKOUT_EXTENDED_MINUTES = 24 * 60

# Exponential backoff for repeated password failures, in minutes: the Nth
# failure past the threshold waits 2^N minutes, capped at 24h.
ACCOUNT_LOCKOUT_BASE_MINUTES = 1

# TTL for Google OAuth CSRF state token stored in Redis
GOOGLE_OAUTH_STATE_TTL_SECONDS = 10 * 60

# TTL for the single-use code that the frontend exchanges for a token pair.
# Short by design: it exists only to survive one browser redirect.
OAUTH_EXCHANGE_CODE_TTL_SECONDS = 60

# Single error message for every password-login failure — see
# login_with_password for why the previous per-case messages were a problem.
_INVALID_CREDENTIALS = "Invalid credentials"

# Bcrypt hash of a value nobody can supply, used to burn the same CPU on the
# "no such user" path as on a real verify. Built lazily so importing this
# module doesn't pay for a bcrypt round.
_DUMMY_PASSWORD_HASH: str | None = None


def _dummy_password_hash() -> str:
    """A real bcrypt hash to verify against when there is no user to check."""
    global _DUMMY_PASSWORD_HASH
    if _DUMMY_PASSWORD_HASH is None:
        from krishisetu.core.security import hash_password

        _DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))
    return _DUMMY_PASSWORD_HASH


def _lockout_minutes(failed_count: int) -> int:
    """Backoff duration for a given consecutive-failure count."""
    overrun = failed_count - ACCOUNT_LOCKOUT_THRESHOLD
    return min(
        ACCOUNT_LOCKOUT_BASE_MINUTES * (2**overrun),
        ACCOUNT_LOCKOUT_EXTENDED_MINUTES,
    )


# ---------------------------------------------------------------------------
# OTP send flow
# ---------------------------------------------------------------------------


async def send_otp(
    db: AsyncSession,
    phone: str,
    purpose: str = "login",
) -> dict[str, Any]:
    """Generate and dispatch an OTP to the given phone number."""
    redis = await get_redis()
    now = datetime.now(timezone.utc)

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

    # NOTE: this endpoint deliberately does NOT branch on whether the phone
    # number is registered. It previously returned 409 for an existing number
    # on signup and 401 for a deactivated account on login, which let anyone
    # enumerate the user base one phone number at a time. Both cases now take
    # the identical path and are resolved at verify time, where the caller has
    # already had to prove possession of the phone.
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

    # Echo the OTP back to the caller ONLY when no real SMS was sent — i.e.
    # the console backend is active, so the OTP is already on stdout and the
    # response reveals nothing new. Gating on ENV was wrong: a production
    # deployment left on the default ENV, or a staging box, would hand every
    # caller a valid OTP for any phone number.
    #
    # The `not is_production` conjunct is not redundant: get_sms_backend()
    # silently falls back to the console backend when no gateway is
    # configured, so backend-alone would turn a production misconfiguration
    # into "hand any caller an OTP for any phone number".
    is_console_backend = (
        isinstance(sms_backend, ConsoleSMSBackend) and not settings().is_production
    )

    return {
        "phone": phone,
        "purpose": purpose,
        "ttl_seconds": OTP_TTL_SECONDS,
        "cooldown_seconds": OTP_COOLDOWN_SECONDS,
        "max_attempts": OTP_VERIFY_MAX_ATTEMPTS,
        "debug_otp": otp if is_console_backend else None,
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
    # FIX: added device_info + ip_address so routes.py can pass them through
    # to _issue_tokens for refresh token device tracking.
    device_info: str | None = None,
    ip_address: str | None = None,
) -> TokenResponse:
    """Verify an OTP and return tokens (login existing user or signup new user)."""
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

    # FIX: device_info + ip_address now forwarded to _issue_tokens
    return await _issue_tokens(db, user, device_info=device_info, ip_address=ip_address)


# ---------------------------------------------------------------------------
# Token issuance
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Refresh token flow
# ---------------------------------------------------------------------------


async def refresh_access_token(
    db: AsyncSession,
    refresh_token: str,
    device_info: str | None = None,
    ip_address: str | None = None,
) -> TokenResponse:
    """Exchange a refresh token for a new access + refresh token pair."""
    payload = decode_token(refresh_token, expected_type="refresh")
    jti = payload.get("jti")
    user_id_str = payload.get("sub")

    if not jti or not user_id_str:
        raise AuthenticationError("Malformed refresh token")

    from uuid import UUID
    user_id = UUID(user_id_str)

    stored_token = await repo.get_refresh_token_by_jti(db, jti)
    if not stored_token:
        raise AuthenticationError("Refresh token not recognized")

    if stored_token.is_revoked:
        logger.warning(
            "refresh_token.reuse_detected",
            user_id=user_id_str,
            jti=jti,
            revoked_reason=stored_token.revoked_reason,
        )
        await repo.revoke_all_user_tokens(db, user_id, reason="suspected_theft")
        raise AuthenticationError(
            "Refresh token has been revoked. Please log in again."
        )

    provided_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
    if provided_hash != stored_token.token_hash:
        logger.warning("refresh_token.hash_mismatch", user_id=user_id_str, jti=jti)
        raise AuthenticationError("Refresh token validation failed")

    user = await repo.get_user_by_id(db, user_id)
    if not user or not user.is_active:
        raise AuthenticationError("User account is not active")

    # Deliberately NOT gated on user.is_locked. The lockout counter exists to
    # slow down password guessing; refusing to refresh an already-issued
    # session as well meant anyone who knew a user's phone or email could
    # forcibly log them out of every device by failing five logins.
    await repo.revoke_refresh_token(db, jti, reason="rotation")

    return await _issue_tokens(db, user, device_info=device_info, ip_address=ip_address)


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


async def logout(db: AsyncSession, refresh_token: str) -> None:
    """Revoke a refresh token. Idempotent."""
    try:
        payload = decode_token(refresh_token, expected_type="refresh")
    except AuthenticationError:
        logger.info("logout.invalid_token")
        return

    jti = payload.get("jti")
    if jti:
        await repo.revoke_refresh_token(db, jti, reason="logout")
        logger.info("logout.success", jti=jti)


async def logout_all_sessions(db: AsyncSession, user_id: object) -> None:
    """Revoke all active refresh tokens for a user."""
    from uuid import UUID

    count = await repo.revoke_all_user_tokens(
        db, UUID(str(user_id)), reason="logout_all"
    )
    logger.info("logout_all.success", user_id=str(user_id), revoked_count=count)


# ---------------------------------------------------------------------------
# Password-based login
# ---------------------------------------------------------------------------


async def login_with_password(
    db: AsyncSession,
    phone_or_email: str,
    password: str,
    device_info: str | None = None,
    ip_address: str | None = None,
) -> TokenResponse:
    """Login with phone/email + password (admin/officer accounts only).

    Every failure path returns exactly the same error. The endpoint used to
    distinguish "no such user" (bare "Invalid credentials"), "OTP-only
    account" ("Password login is not enabled"), "deactivated", "locked", and
    "wrong password" (which helpfully counted down the remaining attempts) —
    four oracles for probing which phone numbers and emails are registered
    and what kind of account they are.
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

    # Per-IP backstop, checked before touching the per-account counter, so a
    # remote attacker cannot lock arbitrary accounts out for free: they run
    # out of requests from their own address long before the victim's account
    # runs out of attempts.
    if ip_address:
        allowed, retry_after = await check_ip_rate_limit(
            bucket="login-password-fail",
            identifier=ip_address,
            rate=settings().RATE_LIMIT_AUTH,
        )
        if not allowed:
            raise RateLimitExceededError(retry_after_seconds=retry_after)

    # Constant-time-ish dummy verify on the miss path: without it, a request
    # for an unknown identifier returns in microseconds while a known one
    # pays for a bcrypt comparison, which is a timing oracle for account
    # existence regardless of how uniform the error messages are.
    if user is None or not user.password_hash:
        verify_password(password, _dummy_password_hash())
        raise AuthenticationError(_INVALID_CREDENTIALS)

    if not user.is_active or user.is_locked:
        verify_password(password, _dummy_password_hash())
        raise AuthenticationError(_INVALID_CREDENTIALS)

    if not verify_password(password, user.password_hash):
        failed_count = await repo.increment_failed_login(db, user.id)

        if failed_count >= ACCOUNT_LOCKOUT_THRESHOLD:
            # Exponential backoff rather than a flat 15-minute wall: the first
            # overrun costs a minute, and only a sustained attack escalates to
            # hours. A hard lock let anyone freeze a known account for 15
            # minutes at a time, indefinitely, for the price of 5 requests.
            lock_minutes = _lockout_minutes(failed_count)
            await repo.lock_account(db, user.id, lock_minutes)
            logger.warning(
                "account.locked",
                user_id=str(user.id),
                failed_count=failed_count,
                lock_minutes=lock_minutes,
            )

        raise AuthenticationError(_INVALID_CREDENTIALS)

    await repo.reset_failed_login(db, user.id)
    await repo.update_last_login(db, user.id)

    return await _issue_tokens(db, user, device_info=device_info, ip_address=ip_address)


# ---------------------------------------------------------------------------
# Google OAuth
# ---------------------------------------------------------------------------


def _sign_oauth_state(state: str) -> str:
    """HMAC a state value with the app secret, for the browser-bound cookie."""
    secret = settings().JWT_SECRET.get_secret_value().encode("utf-8")
    return hmac.new(secret, state.encode("ascii"), "sha256").hexdigest()


def build_oauth_state_cookie(state: str) -> str:
    """Cookie value binding an OAuth state to this browser: "<state>.<sig>"."""
    return f"{state}.{_sign_oauth_state(state)}"


def verify_oauth_state_cookie(cookie_value: str | None, state: str) -> bool:
    """Check that the callback's `state` matches the signed cookie we set.

    This is what actually makes `state` a CSRF defence. Storing state only in
    Redis proved that *someone* started a flow on this server, not that the
    browser completing it is the one that started it — so an attacker could
    start their own flow and feed the victim the resulting callback URL,
    silently signing the victim into the attacker's account.
    """
    if not cookie_value:
        return False
    cookie_state, _, signature = cookie_value.partition(".")
    if not cookie_state or not signature:
        return False
    if not hmac.compare_digest(cookie_state, state):
        return False
    return hmac.compare_digest(_sign_oauth_state(cookie_state), signature)


async def generate_google_oauth_state() -> tuple[str, str]:
    """Start an OAuth flow: mint a state + PKCE verifier (10-min TTL).

    Returns (state, code_challenge). The caller must set the state cookie
    from build_oauth_state_cookie(state) and send code_challenge to Google.
    """
    redis = await get_redis()
    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)

    await redis.set(
        f"oauth:google:state:{state}",
        code_verifier,
        ex=GOOGLE_OAUTH_STATE_TTL_SECONDS,
    )

    # PKCE S256 challenge: base64url(sha256(verifier)), unpadded.
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return state, code_challenge


async def google_oauth_login(
    db: AsyncSession,
    code: str,
    state: str,
    state_cookie: str | None = None,
    device_info: str | None = None,
    ip_address: str | None = None,
) -> TokenResponse:
    """Exchange a Google OAuth authorization code for KrishiSetu JWT tokens.

    Flow:
    1. Verify state against the signed browser cookie AND the Redis record
       (one-time use), recovering the PKCE verifier
    2. Exchange code + verifier → Google access token
    3. Fetch Google user profile
    4. Find or create KrishiSetu user (matched on google_sub)
    5. Issue JWT tokens
    """
    import httpx

    redis = await get_redis()

    # 1. Verify browser binding, then verify and consume the server-side state
    if not verify_oauth_state_cookie(state_cookie, state):
        logger.warning("google_oauth.state_cookie_mismatch")
        raise AuthenticationError(
            "Invalid or expired OAuth state. Please try logging in again."
        )

    state_key = f"oauth:google:state:{state}"
    code_verifier = await redis.get(state_key)
    if not code_verifier:
        raise AuthenticationError(
            "Invalid or expired OAuth state. Please try logging in again."
        )
    await redis.delete(state_key)
    if isinstance(code_verifier, bytes):
        code_verifier = code_verifier.decode()

    cfg = settings()
    if not cfg.google_oauth_enabled:
        raise AuthenticationError("Google OAuth is not configured on this server.")

    # 2. Exchange code for Google tokens
    token_payload = {
        "code": code,
        "client_id": cfg.GOOGLE_OAUTH_CLIENT_ID,
        "client_secret": cfg.GOOGLE_OAUTH_CLIENT_SECRET.get_secret_value(),  # type: ignore[union-attr]
        "redirect_uri": cfg.GOOGLE_OAUTH_REDIRECT_URI,
        "grant_type": "authorization_code",
        "code_verifier": code_verifier,
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

        # 3. Fetch user profile
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
    if not google_sub:
        raise AuthenticationError("Google did not return an account identifier.")
    full_name: str = userinfo.get("name") or email.split("@")[0]

    # 4. Find or create user.
    #
    # google_sub is Google's immutable subject id and is matched FIRST. The
    # previous email-only match was a pre-emptive account takeover: anyone
    # could create a KrishiSetu account claiming a victim's Gmail address
    # (PATCH /me accepted any email, unverified), and the first time the
    # victim signed in with Google they were handed the attacker's account —
    # along with whatever role and data it carried.
    user = await repo.get_user_by_google_sub(db, google_sub)

    if user is None:
        candidate = await repo.get_user_by_email(db, email)
        # Adopting an existing record by email is only safe when that record's
        # email was itself verified by us. Otherwise it is an unproven claim.
        if candidate is not None and candidate.email_verified:
            user = candidate
            await repo.update_user(db, user.id, google_sub=google_sub)
            await db.refresh(user)
            logger.info(
                "google_oauth.linked_existing_account",
                user_id=str(user.id),
            )
        elif candidate is not None:
            logger.warning(
                "google_oauth.unverified_email_collision",
                user_id=str(candidate.id),
            )
            raise AuthenticationError(
                "An account already exists for this email address. Log in with "
                "your phone number and verify your email to link Google sign-in."
            )

    if user is None:
        # Google users don't have a phone — derive a synthetic placeholder.
        # phone_verified=False means it can't be used for OTP.
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
        # email_verified is set from Google's verified claim (checked above),
        # never from anything the user typed.
        await repo.update_user(
            db, user.id, email_verified=True, google_sub=google_sub
        )
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

    return await _issue_tokens(db, user, device_info=device_info, ip_address=ip_address)


# ---------------------------------------------------------------------------
# Single-use OAuth exchange codes
# ---------------------------------------------------------------------------


async def store_oauth_exchange_code(token_response: TokenResponse) -> str:
    """Stash a freshly-issued token pair behind an opaque short-lived code.

    The OAuth callback used to redirect to the frontend with the access and
    refresh tokens in the query string, which wrote a 30-day refresh token
    into browser history, the Referer header of the next request, and every
    proxy and access log along the way. The redirect now carries only this
    code, which is worthless once redeemed.
    """
    redis = await get_redis()
    code = secrets.token_urlsafe(32)
    await redis.set(
        f"oauth:exchange:{code}",
        token_response.model_dump_json(),
        ex=OAUTH_EXCHANGE_CODE_TTL_SECONDS,
    )
    return code


async def consume_oauth_exchange_code(code: str) -> TokenResponse:
    """Redeem an exchange code exactly once, returning the token pair."""
    redis = await get_redis()
    key = f"oauth:exchange:{code}"

    # GETDEL is atomic, so two concurrent redemptions cannot both succeed.
    raw = await redis.getdel(key)
    if not raw:
        raise AuthenticationError(
            "This sign-in link has expired or was already used. Please try again."
        )
    if isinstance(raw, bytes):
        raw = raw.decode()

    return TokenResponse.model_validate_json(raw)


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