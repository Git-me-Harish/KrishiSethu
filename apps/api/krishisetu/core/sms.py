"""SMS gateway abstraction.

Provides a unified interface for sending SMS messages, with pluggable
backends:
- ConsoleSMSBackend (default in development) — logs to stdout
- MSG91SMSBackend (production) — calls MSG91 REST API
- KarixSMSBackend (alternative production) — calls Karix REST API

The backend is selected at startup based on the ENV setting and availability
of API keys. Switching backends does not require code changes — only
environment variable updates.

SMS delivery is async and best-effort. Failures are logged but do not block
the requesting operation; the OTP is still stored in Redis and the user can
retry.
"""

from __future__ import annotations

import abc
import asyncio

import httpx

from krishisetu.core.config import settings
from krishisetu.core.logging import get_logger

logger = get_logger(__name__)


class SMSBackend(abc.ABC):
    """Abstract SMS backend interface."""

    @abc.abstractmethod
    async def send_otp(self, phone: str, otp: str, purpose: str = "login") -> bool:
        """Send an OTP to the given phone number.

        Returns True if the SMS was accepted by the gateway (does not guarantee
        delivery — that requires DLR callbacks which we don't implement yet).
        Returns False if the gateway rejected the request.
        """
        ...

    @abc.abstractmethod
    async def send_sms(self, phone: str, message: str) -> bool:
        """Send a plain SMS message."""
        ...


class ConsoleSMSBackend(SMSBackend):
    """Development backend that logs SMS to stdout.

    Used in development and CI. No real SMS is sent. The OTP appears in the
    API logs, which is convenient for testing.
    """

    async def send_otp(self, phone: str, otp: str, purpose: str = "login") -> bool:
        # Simulate small network latency
        await asyncio.sleep(0.05)
        print(f"\n{'=' * 60}")
        print(f"SMS to {phone} | Purpose: {purpose}")
        print(f"OTP: {otp}")
        print(f"{'=' * 60}\n")
        logger.info("sms.otp.sent.console", phone=phone, purpose=purpose)
        return True

    async def send_sms(self, phone: str, message: str) -> bool:
        await asyncio.sleep(0.05)
        print(f"\n{'=' * 60}")
        print(f"SMS to {phone}")
        print(f"Message: {message}")
        print(f"{'=' * 60}\n")
        logger.info("sms.sent.console", phone=phone)
        return True


class MSG91SMSBackend(SMSBackend):
    """Production backend using MSG91 (https://msg91.com).

    MSG91 is one of the most widely used SMS gateways in India, supporting:
    - Transactional, promotional, and OTP routes
    - DLR (delivery reports) via webhook
    - Unicode (for Indic script SMS, future use)
    - Template-based messaging (required by TRAI for transactional SMS)

    The MSG91 auth key is loaded from settings.MSG91_AUTH_KEY.
    """

    BASE_URL = "https://api.msg91.com/api/v5"

    def __init__(self) -> None:
        self.auth_key = settings().MSG91_AUTH_KEY
        if not self.auth_key:
            raise RuntimeError("MSG91_AUTH_KEY not configured")
        # Sender ID (6-character alphanumeric, registered with TRAI)
        self.sender_id = "KRSHST"
        # MSG91 OTP flow ID (configured in MSG91 dashboard)
        self.otp_template_id = "65f3a1b2d6fc050123456789"  # Replace with real template ID

    async def send_otp(self, phone: str, otp: str, purpose: str = "login") -> bool:
        # MSG91's /otp endpoint sends a pre-templated OTP SMS
        # We use the send-sms endpoint with our own template for flexibility
        url = f"{self.BASE_URL}/flow"
        headers = {
            "authkey": self.auth_key.get_secret_value(),
            "content-type": "application/json",
        }
        # Phone must include country code for MSG91
        full_phone = f"91{phone}"
        payload = {
            "template_id": self.otp_template_id,
            "sender": self.sender_id,
            "short_url": "0",  # Don't shorten URLs in SMS
            "mobiles": full_phone,
            "otp": otp,
            "purpose": purpose,
        }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload, headers=headers)

            if response.status_code == 200:
                data = response.json()
                if data.get("type") == "success":
                    logger.info(
                        "sms.otp.sent.msg91",
                        phone=phone,
                        purpose=purpose,
                        msg91_id=data.get("message"),
                    )
                    return True
                logger.error(
                    "sms.otp.failed.msg91",
                    phone=phone,
                    response=data,
                )
                return False
            logger.error(
                "sms.otp.http_error.msg91",
                phone=phone,
                status=response.status_code,
                body=response.text,
            )
            return False
        except httpx.HTTPError as e:
            logger.error("sms.otp.network_error.msg91", phone=phone, error=str(e))
            return False

    async def send_sms(self, phone: str, message: str) -> bool:
        url = f"{self.BASE_URL}/sms"
        headers = {
            "authkey": self.auth_key.get_secret_value(),
            "content-type": "application/json",
        }
        payload = {
            "sender": self.sender_id,
            "route": "4",  # Transactional route
            "country": "91",
            "sms": [{"message": message, "to": [f"91{phone}"]}],
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(url, json=payload, headers=headers)
            return response.status_code == 200
        except httpx.HTTPError as e:
            logger.error("sms.network_error.msg91", phone=phone, error=str(e))
            return False


class KarixSMSBackend(SMSBackend):
    """Alternative production backend using Karix (now Tanla).

    Used as a fallback when MSG91 is unavailable or for redundancy.
    Implementation deferred — same interface as MSG91SMSBackend.
    """

    async def send_otp(self, phone: str, otp: str, purpose: str = "login") -> bool:
        raise NotImplementedError("Karix backend not yet implemented")

    async def send_sms(self, phone: str, message: str) -> bool:
        raise NotImplementedError("Karix backend not yet implemented")


# ---------------------------------------------------------------------------
# Backend selection (singleton)
# ---------------------------------------------------------------------------

_backend: SMSBackend | None = None


def get_sms_backend() -> SMSBackend:
    """Get the configured SMS backend (singleton).

    Selection logic:
    1. If ENV=development, use ConsoleSMSBackend (regardless of MSG91 key)
    2. If MSG91_AUTH_KEY is set, use MSG91SMSBackend
    3. Otherwise, fall back to ConsoleSMSBackend with a warning
    """
    global _backend
    if _backend is not None:
        return _backend

    cfg = settings()

    if cfg.is_development:
        _backend = ConsoleSMSBackend()
        logger.info("sms.backend.selected", backend="console", reason="development_env")
        return _backend

    if cfg.MSG91_AUTH_KEY:
        try:
            _backend = MSG91SMSBackend()
            logger.info("sms.backend.selected", backend="msg91")
            return _backend
        except Exception as e:
            logger.error("sms.backend.init_failed", backend="msg91", error=str(e))

    # Fallback: console with warning
    _backend = ConsoleSMSBackend()
    logger.warning(
        "sms.backend.fallback_to_console",
        reason="no_production_backend_configured",
    )
    return _backend


async def close_sms_backend() -> None:
    """Cleanup any backend resources (e.g., HTTP client pools)."""
    global _backend
    _backend = None
