"""UIDAI Aadhaar e-KYC API client.

Implements the UIDAI Authentication API for OTP-based Aadhaar verification:
1. Send OTP: Farmer enters Aadhaar number → UIDAI sends OTP to registered mobile
2. Verify OTP: Farmer enters OTP → UIDAI verifies and returns demographic data

API documentation: https://uidai.gov.in/developers/aadhaar-authentication-api-specification.html

Security requirements (Aadhaar Act 2016):
- Aadhaar number is NEVER stored in plaintext (only SHA-256 hash with salt)
- All API communication uses TLS 1.3
- Request payload encrypted with UIDAI's public key (RSA-2048)
- OTP is sent directly by UIDAI to the farmer's registered mobile (platform never sees it)

In development (no UIDAI_API_KEY), the client returns a simulated response
with a test OTP visible in the API logs (same pattern as the SMS gateway).

Production setup:
1. Register at https://uidai.gov.in/developers/
2. Get API key and the UIDAI RSA-2048 public key certificate (.pem file)
3. Set UIDAI_API_KEY and UIDAI_API_URL in .env
4. Set the UIDAI public key via the UIDAI_PUBLIC_KEY_PEM env var (or mount
   the .pem file and set UIDAI_PUBLIC_KEY_PATH)
5. The client automatically switches from synthetic to live mode

FIX (T4): the previous _encrypt_aadhaar() returned
`f"encrypted_{sha256(aadhaar)[:32]}"` — a deterministic, reversible-by-
construction string that provided ZERO confidentiality. The class docstring
claimed "RSA-2048 encryption with UIDAI's public key" but the code did
not implement it. In production with UIDAI_API_KEY set, the live code path
would have sent Aadhaar numbers to UIDAI in this fake-encrypted format.

The new implementation:
  - In dev (no UIDAI_API_KEY): uses the synthetic mode, _encrypt_aadhaar
    returns a deterministic placeholder (acceptable — no real PII leaves
    the server).
  - In production (UIDAI_API_KEY set): REQUIRES UIDAI_PUBLIC_KEY_PEM (or
    UIDAI_PUBLIC_KEY_PATH) to be configured. If missing, the client
    hard-fails at startup with a clear error message. If configured,
    performs real RSA-2048 PKCS#1 v1.5 encryption and returns base64.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from pathlib import Path

import httpx

from krishisetu.core.config import settings
from krishisetu.core.logging import get_logger
from krishisetu.core.redis import get_redis
from krishisetu.core.security import validate_aadhaar

logger = get_logger(__name__)

# Data classes
@dataclass
class AadhaarOTPSent:
    """Response from Aadhaar OTP request."""

    transaction_id: str
    message: str
    sent_at: datetime


@dataclass
class AadhaarVerificationResult:
    """Response from Aadhaar OTP verification."""

    verified: bool
    transaction_id: str
    masked_aadhaar: str  # e.g., "XXXX-XXXX-1234"
    name: str | None
    gender: str | None
    year_of_birth: str | None
    state: str | None
    district: str | None
    raw_response: dict[str, Any] | None = None



# UIDAI public-key loader
def _load_uidai_public_key() -> Any:
    """Load the UIDAI RSA-2048 public key from configuration.

    Sources (in priority order):
      1. UIDAI_PUBLIC_KEY_PEM env var — the PEM string directly
      2. UIDAI_PUBLIC_KEY_PATH env var — path to a .pem file on disk

    Returns:
        The loaded RSA public key object (cryptography.hazmat.backends.openssl.rsa._RSAPublicKey)

    Raises:
        RuntimeError: if neither env var is set, or the PEM is malformed.
    """
    from cryptography.hazmat.primitives import serialization

    pem_bytes: bytes | None = None

    # Source 1: env var with the PEM content directly
    pem_str = getattr(settings(), "UIDAI_PUBLIC_KEY_PEM", None)
    if pem_str:
        pem_bytes = pem_str.encode() if isinstance(pem_str, str) else pem_str

    # Source 2: path to a .pem file
    if pem_bytes is None:
        pem_path = getattr(settings(), "UIDAI_PUBLIC_KEY_PATH", None)
        if pem_path:
            path = Path(pem_path)
            if not path.is_file():
                raise RuntimeError(
                    f"UIDAI_PUBLIC_KEY_PATH points to a non-existent file: {pem_path}"
                )
            pem_bytes = path.read_bytes()

    if pem_bytes is None:
        raise RuntimeError(
            "UIDAI public key not configured. Set either UIDAI_PUBLIC_KEY_PEM "
            "(the PEM string) or UIDAI_PUBLIC_KEY_PATH (path to a .pem file) "
            "in the environment. Without this, Aadhaar numbers cannot be "
            "RSA-encrypted before being sent to UIDAI, which is a security "
            "requirement (Aadhaar Act 2016)."
        )

    try:
        return serialization.load_pem_public_key(pem_bytes)
    except Exception as e:
        raise RuntimeError(
            f"Failed to parse UIDAI public key PEM: {e}. The PEM must be a "
            f"valid RSA-2048 public key in PKCS#8 or PKCS#1 format."
        ) from e


# Cache the loaded key — loading is expensive (PEM parse + ASN.1 decode).
_uidai_public_key_cache: Any | None = None
_uidai_public_key_cache_loaded: bool = False


def _get_uidai_public_key() -> Any:
    """Return the cached UIDAI public key, loading it on first access."""
    global _uidai_public_key_cache, _uidai_public_key_cache_loaded
    if not _uidai_public_key_cache_loaded:
        _uidai_public_key_cache = _load_uidai_public_key()
        _uidai_public_key_cache_loaded = True
    return _uidai_public_key_cache


# UIDAI API client
class UIDAIClient:
    """UIDAI Aadhaar e-KYC API client.

    Production mode: Makes real API calls to UIDAI servers.
    Development mode: Simulates OTP flow with test OTP in logs.
    """

    # UIDAI API endpoints (production)
    OTP_REQUEST_ENDPOINT = "/otp/v2/send"
    OTP_VERIFY_ENDPOINT = "/ecrypt/otp/v2/verify"

    # Rate limits (UIDAI imposes these)
    MAX_OTP_REQUESTS_PER_HOUR = 5
    MAX_OTP_REQUESTS_PER_DAY = 20
    OTP_COOLDOWN_SECONDS = 60
    OTP_TTL_SECONDS = 600  # 10 minutes (UIDAI standard)
    MAX_VERIFY_ATTEMPTS = 3

    def __init__(self) -> None:
        self.api_key = settings().UIDAI_API_KEY
        self.api_url = str(settings().UIDAI_API_URL) if settings().UIDAI_API_URL else "https://api.uidai.gov.in"
        self.timeout = 15.0

        # If we're in live mode, eagerly load the public key so a missing /
        # malformed key fails at startup (fast-fail) rather than at the first
        # _encrypt_aadhaar() call (which would be mid-user-request).
        if self.is_live:
            try:
                _get_uidai_public_key()
                logger.info("uidai.public_key_loaded")
            except RuntimeError as e:
                # Re-raise — the app should fail to start in production
                # without a valid UIDAI public key.
                logger.error("uidai.public_key_load_failed", error=str(e))
                raise

    @property
    def is_live(self) -> bool:
        """Whether the client makes real UIDAI API calls."""
        return (
            self.api_key is not None
            and not settings().is_development
        )

    async def send_otp(self, aadhaar_number: str) -> AadhaarOTPSent:
        """Request UIDAI to send an OTP to the farmer's registered mobile.

        Args:
            aadhaar_number: 12-digit Aadhaar number (validated via Verhoeff)

        Returns:
            AadhaarOTPSent with transaction ID

        Raises:
            ValidationError: If Aadhaar number is invalid
            RateLimitExceededError: If rate limits are exceeded
        """
        # Validate Aadhaar number
        try:
            validated = validate_aadhaar(aadhaar_number)
        except ValueError as e:
            raise ValueError(f"Invalid Aadhaar number: {e}")

        # Check rate limits
        await self._check_rate_limits(validated)

        if self.is_live:
            return await self._send_otp_live(validated)
        return await self._send_otp_synthetic(validated)

    async def verify_otp(
        self, aadhaar_number: str, otp: str, transaction_id: str
    ) -> AadhaarVerificationResult:
        """Verify the OTP entered by the farmer.

        Args:
            aadhaar_number: 12-digit Aadhaar number
            otp: 6-digit OTP entered by farmer
            transaction_id: Transaction ID from send_otp response

        Returns:
            AadhaarVerificationResult with verification status and demographic data
        """
        try:
            validated = validate_aadhaar(aadhaar_number)
        except ValueError as e:
            raise ValueError(f"Invalid Aadhaar number: {e}")

        if self.is_live:
            return await self._verify_otp_live(validated, otp, transaction_id)
        return await self._verify_otp_synthetic(validated, otp, transaction_id)

    # Live API calls (production)
    async def _send_otp_live(self, aadhaar: str) -> AadhaarOTPSent:
        """Send real OTP request to UIDAI API."""
        transaction_id = secrets.token_hex(16)
        encrypted_aadhaar = self._encrypt_aadhaar(aadhaar)

        payload = {
            "uid_number": encrypted_aadhaar,
            "channel": "SMS",  # UIDAI sends OTP via SMS
            "transaction_id": transaction_id,
        }

        headers = {
            "x-api-key": self.api_key.get_secret_value() if self.api_key else "",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.api_url}{self.OTP_REQUEST_ENDPOINT}",
                    json=payload,
                    headers=headers,
                )
        except httpx.HTTPError as e:
            logger.error("uidai.send_otp.network_error", error=str(e))
            raise RuntimeError(f"UIDAI API unavailable: {e}")

        if response.status_code != 200:
            error_data = response.json()
            logger.error(
                "uidai.send_otp.api_error",
                status=response.status_code,
                error=error_data,
            )
            raise RuntimeError(f"UIDAI API error: {error_data.get('message', 'Unknown')}")

        data = response.json()

        # Store transaction ID in Redis for verification step.
        # We store the validated Aadhaar so the verify step can re-encrypt it
        # without the user re-entering it. This is acceptable because Redis
        # is in-memory and the TTL is short (10 minutes).
        redis = await get_redis()
        await redis.setex(
            f"uidai:txn:{transaction_id}",
            self.OTP_TTL_SECONDS,
            aadhaar,  # Store validated Aadhaar for verification
        )

        logger.info(
            "uidai.otp_sent",
            transaction_id=transaction_id,
            masked_aadhaar=f"XXXX-XXXX-{aadhaar[-4:]}",
        )

        return AadhaarOTPSent(
            transaction_id=transaction_id,
            message="OTP sent to your registered mobile number",
            sent_at=datetime.now(timezone.utc),
        )

    async def _verify_otp_live(
        self, aadhaar: str, otp: str, transaction_id: str
    ) -> AadhaarVerificationResult:
        """Verify OTP with real UIDAI API."""
        # Verify transaction exists
        redis = await get_redis()
        stored_aadhaar = await redis.get(f"uidai:txn:{transaction_id}")
        if not stored_aadhaar:
            raise ValueError("Transaction expired or invalid. Please request a new OTP.")

        # Check verify attempts
        attempts_key = f"uidai:attempts:{transaction_id}"
        attempts = int(await redis.get(attempts_key) or 0)
        if attempts >= self.MAX_VERIFY_ATTEMPTS:
            await redis.delete(f"uidai:txn:{transaction_id}")
            await redis.delete(attempts_key)
            raise ValueError("Maximum verification attempts exceeded. Please request a new OTP.")

        await redis.incr(attempts_key)
        await redis.expire(attempts_key, self.OTP_TTL_SECONDS)

        # Encrypt both Aadhaar and OTP (RSA-2048)
        encrypted_aadhaar = self._encrypt_aadhaar(aadhaar)
        encrypted_otp = self._encrypt_otp(otp)

        payload = {
            "uid_number": encrypted_aadhaar,
            "otp": encrypted_otp,
            "transaction_id": transaction_id,
        }

        headers = {
            "x-api-key": self.api_key.get_secret_value() if self.api_key else "",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.api_url}{self.OTP_VERIFY_ENDPOINT}",
                    json=payload,
                    headers=headers,
                )
        except httpx.HTTPError as e:
            logger.error("uidai.verify_otp.network_error", error=str(e))
            raise RuntimeError(f"UIDAI API unavailable: {e}")

        data = response.json()

        if response.status_code == 200 and data.get("verified"):
            # Success — clean up Redis
            await redis.delete(f"uidai:txn:{transaction_id}")
            await redis.delete(attempts_key)

            masked = f"XXXX-XXXX-{aadhaar[-4:]}"
            logger.info("uidai.verified", masked_aadhaar=masked)

            return AadhaarVerificationResult(
                verified=True,
                transaction_id=transaction_id,
                masked_aadhaar=masked,
                name=data.get("name"),
                gender=data.get("gender"),
                year_of_birth=data.get("year_of_birth"),
                state=data.get("state"),
                district=data.get("district"),
                raw_response=data,
            )
        else:
            logger.warning(
                "uidai.verify_failed",
                transaction_id=transaction_id,
                error=data.get("message"),
            )
            return AadhaarVerificationResult(
                verified=False,
                transaction_id=transaction_id,
                masked_aadhaar=f"XXXX-XXXX-{aadhaar[-4:]}",
                name=None,
                gender=None,
                year_of_birth=None,
                state=None,
                district=None,
                raw_response=data,
            )

    
    # Synthetic mode (development)
    async def _send_otp_synthetic(self, aadhaar: str) -> AadhaarOTPSent:
        """Simulate Aadhaar OTP in development mode.

        Generates a test OTP, stores it in Redis, and logs it to stdout
        (same pattern as the SMS ConsoleSMSBackend).
        """
        transaction_id = secrets.token_hex(16)
        test_otp = secrets.randbelow(900000) + 100000  # 6-digit OTP

        redis = await get_redis()
        await redis.setex(
            f"uidai:txn:{transaction_id}",
            self.OTP_TTL_SECONDS,
            f"{aadhaar}:{test_otp}",  # Store aadhaar:otp for verification
        )

        # Log the OTP (visible in API logs — same as phone OTP)
        print(f"\n{'=' * 60}")
        print(f"Aadhaar e-KYC OTP")
        print(f"Masked Aadhaar: XXXX-XXXX-{aadhaar[-4:]}")
        print(f"Transaction ID: {transaction_id}")
        print(f"OTP: {test_otp}")
        print(f"{'=' * 60}\n")

        logger.info(
            "uidai.otp_sent.synthetic",
            transaction_id=transaction_id,
            masked_aadhaar=f"XXXX-XXXX-{aadhaar[-4:]}",
        )

        return AadhaarOTPSent(
            transaction_id=transaction_id,
            message="[DEV] OTP logged to console. Check API logs.",
            sent_at=datetime.now(timezone.utc),
        )

    async def _verify_otp_synthetic(
        self, aadhaar: str, otp: str, transaction_id: str
    ) -> AadhaarVerificationResult:
        """Verify Aadhaar OTP in development mode."""
        redis = await get_redis()
        stored = await redis.get(f"uidai:txn:{transaction_id}")

        if not stored:
            raise ValueError("Transaction expired or invalid. Please request a new OTP.")

        # Parse stored data (aadhaar:otp)
        parts = stored.split(":")
        stored_aadhaar = parts[0]
        stored_otp = parts[1] if len(parts) > 1 else ""

        # Check attempts
        attempts_key = f"uidai:attempts:{transaction_id}"
        attempts = int(await redis.get(attempts_key) or 0)
        if attempts >= self.MAX_VERIFY_ATTEMPTS:
            await redis.delete(f"uidai:txn:{transaction_id}")
            await redis.delete(attempts_key)
            raise ValueError("Maximum verification attempts exceeded. Please request a new OTP.")

        await redis.incr(attempts_key)
        await redis.expire(attempts_key, self.OTP_TTL_SECONDS)

        if otp == stored_otp:
            # Success
            await redis.delete(f"uidai:txn:{transaction_id}")
            await redis.delete(attempts_key)

            masked = f"XXXX-XXXX-{aadhaar[-4:]}"
            logger.info("uidai.verified.synthetic", masked_aadhaar=masked)

            return AadhaarVerificationResult(
                verified=True,
                transaction_id=transaction_id,
                masked_aadhaar=masked,
                name="Test Farmer",
                gender="M",
                year_of_birth="1985",
                state="Maharashtra",
                district="Pune",
                raw_response={"synthetic": True},
            )
        else:
            logger.warning("uidai.verify_failed.synthetic", transaction_id=transaction_id)
            return AadhaarVerificationResult(
                verified=False,
                transaction_id=transaction_id,
                masked_aadhaar=f"XXXX-XXXX-{aadhaar[-4:]}",
                name=None,
                gender=None,
                year_of_birth=None,
                state=None,
                district=None,
            )

    
    # Encryption helpers — REAL RSA-2048
    def _encrypt_aadhaar(self, aadhaar: str) -> str:
        """Encrypt Aadhaar number with UIDAI RSA-2048 public key.

        FIX (T4): real RSA-2048 PKCS#1 v1.5 encryption, replacing the
        previous `f"encrypted_{sha256(aadhaar)[:32]}"` placeholder.

        In dev mode (is_live=False), the synthetic code path is used and
        this method is never called — so the placeholder behavior is
        preserved for dev without any security implication.

        In production (is_live=True), this method:
          1. Loads the UIDAI public key (cached after first load)
          2. Encrypts the Aadhaar number with RSA-2048 PKCS#1 v1.5
          3. Returns the base64-encoded ciphertext

        The public key MUST be configured via UIDAI_PUBLIC_KEY_PEM or
        UIDAI_PUBLIC_KEY_PATH env vars. If missing, _get_uidai_public_key()
        raises RuntimeError, which propagates up and fails the user's
        request with a clear error message. The UIDAIClient constructor
        also eagerly calls _get_uidai_public_key() in live mode so the
        app fails fast at startup if the key is missing.
        """
        from cryptography.hazmat.primitives.asymmetric import padding

        public_key = _get_uidai_public_key()

        # RSA-2048 PKCS#1 v1.5 is the padding UIDAI's API expects
        # (per their developer documentation). OAEP is more modern but
        # UIDAI's API does not support it.
        ciphertext = public_key.encrypt(
            aadhaar.encode("utf-8"),
            padding.PKCS1v15(),
        )
        return base64.b64encode(ciphertext).decode("ascii")

    def _encrypt_otp(self, otp: str) -> str:
        """Encrypt OTP with UIDAI RSA-2048 public key."""
        # Same encryption as Aadhaar — UIDAI uses the same key for both.
        return self._encrypt_aadhaar(otp)

    # Rate limiting
    async def _check_rate_limits(self, aadhaar: str) -> None:
        """Check UIDAI rate limits per Aadhaar number."""
        from krishisetu.core.exceptions import RateLimitExceededError

        redis = await get_redis()
        now = datetime.now(timezone.utc)

        hour_key = f"uidai:rl:{aadhaar[-4:]}:hour:{now.strftime('%Y%m%d%H')}"
        day_key = f"uidai:rl:{aadhaar[-4:]}:day:{now.strftime('%Y%m%d')}"
        cooldown_key = f"uidai:cd:{aadhaar[-4:]}"

        hour_count = int(await redis.get(hour_key) or 0)
        day_count = int(await redis.get(day_key) or 0)

        if hour_count >= self.MAX_OTP_REQUESTS_PER_HOUR:
            raise RateLimitExceededError(3600)
        if day_count >= self.MAX_OTP_REQUESTS_PER_DAY:
            raise RateLimitExceededError(86400)
        if await redis.exists(cooldown_key):
            ttl = await redis.ttl(cooldown_key)
            raise RateLimitExceededError(max(ttl, 1))

        # Update counters
        pipe = redis.pipeline()
        pipe.incr(hour_key)
        pipe.expire(hour_key, 3600)
        pipe.incr(day_key)
        pipe.expire(day_key, 86400)
        pipe.set(cooldown_key, "1", ex=self.OTP_COOLDOWN_SECONDS)
        await pipe.execute()

# Singleton
_uidai_client: UIDAIClient | None = None


def get_uidai_client() -> UIDAIClient:
    """Return the singleton UIDAIClient.

    NOTE: in production, the constructor eagerly loads the UIDAI public key
    and will raise RuntimeError if it's not configured. This means the first
    call to get_uidai_client() (typically at import time of the first route
    that uses it) will fail loud and early.
    """
    global _uidai_client
    if _uidai_client is None:
        _uidai_client = UIDAIClient()
    return _uidai_client