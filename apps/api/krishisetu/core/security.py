"""Security utilities — JWT creation/verification, password hashing, OTP generation.

This module is the cryptographic foundation of the platform. Every security
primitive the rest of the application needs lives here, with no external
dependencies on FastAPI (so it can be unit-tested in isolation).

Design decisions:
- JWT signed with HS256 (HMAC-SHA256) using a 256-bit secret from settings
- Access tokens are short-lived (30 min) and carry role + user_id claims
- Refresh tokens are long-lived (30 days) and rotated on each use
- Refresh tokens carry a unique jti (JWT ID) for revocation tracking
- Passwords hashed with bcrypt (12 rounds, configurable)
- OTPs are 6-digit numeric, generated with secrets.randbelow for CSPRNG
"""

from __future__ import annotations

import secrets
import string
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import UUID

import jwt
from passlib.context import CryptContext

from krishisetu.core.config import settings
from krishisetu.core.exceptions import AuthenticationError

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=settings().PASSWORD_BCRYPT_ROUNDS,
)


def hash_password(plain: str) -> str:
    """Hash a plaintext password using bcrypt."""
    if len(plain) < 8:
        raise ValueError("Password must be at least 8 characters")
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash.

    Returns False on mismatch (does not raise) so callers can use a uniform
    "invalid credentials" error message without leaking which check failed.
    """
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False


# ---------------------------------------------------------------------------
# JWT tokens
# ---------------------------------------------------------------------------

TokenType = Literal["access", "refresh"]


def create_access_token(
    user_id: UUID | str,
    role: str,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Create a short-lived JWT access token.

    The token carries:
    - sub: user ID (string UUID)
    - role: user role (farmer, agri_officer, supplier, insurer, admin)
    - type: "access"
    - iat: issued at (Unix timestamp)
    - exp: expiration (Unix timestamp)
    - extra_claims: any additional claims passed by caller
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings().JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(
        payload,
        settings().JWT_SECRET.get_secret_value(),
        algorithm=settings().JWT_ALGORITHM,
    )


def create_refresh_token(user_id: UUID | str) -> tuple[str, str]:
    """Create a long-lived JWT refresh token.

    Returns a tuple of (token, jti) — the jti is a unique identifier stored
    in the database (hashed) so the token can be revoked.

    Refresh tokens do NOT carry role claims — they are only used to obtain
    new access tokens, which then carry the role.
    """
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=settings().JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    jti = secrets.token_urlsafe(32)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": "refresh",
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    token = jwt.encode(
        payload,
        settings().JWT_SECRET.get_secret_value(),
        algorithm=settings().JWT_ALGORITHM,
    )
    return token, jti


def decode_token(token: str, expected_type: TokenType = "access") -> dict[str, Any]:
    """Decode and verify a JWT token.

    Raises AuthenticationError if:
    - Token is malformed
    - Signature is invalid
    - Token has expired
    - Token type does not match expected_type (e.g., using refresh as access)
    """
    try:
        payload = jwt.decode(
            token,
            settings().JWT_SECRET.get_secret_value(),
            algorithms=[settings().JWT_ALGORITHM],
        )
    except jwt.ExpiredSignatureError as e:
        raise AuthenticationError("Token has expired") from e
    except jwt.InvalidTokenError as e:
        raise AuthenticationError(f"Invalid token: {e}") from e

    if payload.get("type") != expected_type:
        raise AuthenticationError(
            f"Expected {expected_type} token, got {payload.get('type')}"
        )

    return payload


# ---------------------------------------------------------------------------
# OTP generation
# ---------------------------------------------------------------------------

def generate_otp(length: int = 6) -> str:
    """Generate a cryptographically-secure numeric OTP.

    Uses secrets.randbelow (CSPRNG) rather than random.randint (Mersenne Twister,
    which is predictable and unsafe for security-critical randomness).
    """
    if length < 4 or length > 8:
        raise ValueError("OTP length must be between 4 and 8 digits")
    # Generate a number in [0, 10^length) and zero-pad to the requested length
    upper_bound = 10**length
    otp_int = secrets.randbelow(upper_bound)
    return str(otp_int).zfill(length)


def generate_token_urlsafe(length: int = 32) -> str:
    """Generate a URL-safe random token (for session IDs, CSRF tokens, etc.)."""
    return secrets.token_urlsafe(length)


def generate_password_reset_token() -> str:
    """Generate a password reset token (URL-safe, 32 bytes)."""
    return generate_token_urlsafe(32)


# ---------------------------------------------------------------------------
# Phone number validation
# ---------------------------------------------------------------------------

def normalize_indian_phone(phone: str) -> str:
    """Normalize an Indian phone number to 10-digit format (no country code).

    Accepts:
    - 10-digit: 9876543210
    - +91 prefix: +919876543210
    - 91 prefix: 919876543210
    - With spaces/dashes: +91 98765 43210

    Returns: 10-digit string starting with [6-9]

    Raises ValueError if the number is not a valid Indian mobile number.
    """
    # Strip everything except digits
    digits = "".join(c for c in phone if c.isdigit())

    # Handle country code prefix
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]

    if len(digits) != 10:
        raise ValueError(f"Phone number must be 10 digits, got {len(digits)}")

    if not digits[0] in "6789":
        raise ValueError("Indian mobile numbers must start with 6, 7, 8, or 9")

    return digits


# ---------------------------------------------------------------------------
# Aadhaar number validation
# ---------------------------------------------------------------------------

def validate_aadhaar(aadhaar: str) -> str:
    """Validate an Aadhaar number using the Verhoeff checksum algorithm.

    Aadhaar is a 12-digit number where the last digit is a checksum computed
    using the Verhoeff algorithm (not Luhn). This function validates the
    checksum and returns the cleaned 12-digit string.

    Ref: https://uidai.gov.in/219-blogs/news/329-why-uidai-uses-verhoeff-algorithm.html

    Raises ValueError if the number is invalid.
    """
    digits = "".join(c for c in aadhaar if c.isdigit())

    if len(digits) != 12:
        raise ValueError(f"Aadhaar must be 12 digits, got {len(digits)}")

    if digits[0] == "0":
        raise ValueError("Aadhaar cannot start with 0")

    if not _verhoeff_check(digits):
        raise ValueError("Aadhaar failed Verhoeff checksum validation")

    return digits


def hash_aadhaar(aadhaar: str) -> str:
    """Hash an Aadhaar number with a per-application salt.

    The platform NEVER stores raw Aadhaar numbers. Only this hash is stored,
    enabling duplicate detection without exposing the actual number.

    Uses SHA-256 with a salt derived from the JWT_SECRET (application-level
    salt). For higher security, migrate to per-record salts in Phase 2.
    """
    import hashlib

    salt = settings().JWT_SECRET.get_secret_value()
    return hashlib.sha256(f"{salt}:{aadhaar}".encode()).hexdigest()


# Verhoeff algorithm implementation (for Aadhaar checksum validation)
_VERHOEFF_D = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)

_VERHOEFF_P = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)


def _verhoeff_check(number: str) -> bool:
    """Verify a number's Verhoeff checksum."""
    # Verhoeff invariant: c(0) = 0
    c = 0
    # Iterate digits right-to-left, applying permutation
    for i, ch in enumerate(reversed(number)):
        digit = int(ch)
        c = _VERHOEFF_D[c][_VERHOEFF_P[i % 8][digit]]
    return c == 0
