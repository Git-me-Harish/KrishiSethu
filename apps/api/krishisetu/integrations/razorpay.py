"""Razorpay payment gateway client.

Integrates with Razorpay for:
- Creating orders (pre-payment)
- Verifying payment signatures (post-payment)
- Processing refunds
- Handling webhooks

Registration: https://razorpay.com/
Get API keys from: https://dashboard.razorpay.com/app/keys

Configuration:
    RAZORPAY_KEY_ID=rzp_test_XXXXXXXX
    RAZORPAY_KEY_SECRET=XXXXXXXXXXXXXXXX

In development (no keys), the client simulates payments:
- Creates fake order IDs
- Accepts any signature
- Simulates instant capture
- Logs all operations to stdout

Razorpay API docs: https://razorpay.com/docs/api/
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx

from krishisetu.core.config import settings
from krishisetu.core.logging import get_logger

logger = get_logger(__name__)

# Razorpay amounts are in paise (1 ₹ = 100 paise)
RUPEE_TO_PAISE = 100


@dataclass
class RazorpayOrder:
    """Razorpay order response."""

    order_id: str
    amount: int  # In paise
    currency: str
    status: str
    receipt: str | None = None


@dataclass
class RazorpayPayment:
    """Razorpay payment verification result."""

    verified: bool
    payment_id: str
    order_id: str
    amount: int
    status: str
    method: str | None = None
    upi_id: str | None = None
    raw_response: dict[str, Any] | None = None


@dataclass
class RazorpayRefund:
    """Razorpay refund response."""

    refund_id: str
    payment_id: str
    amount: int
    status: str
    raw_response: dict[str, Any] | None = None


class RazorpayClient:
    """Razorpay payment gateway client.

    Production mode: Real API calls to Razorpay servers.
    Development mode: Simulated payments with fake IDs.
    """

    BASE_URL = "https://api.razorpay.com/v1"

    def __init__(self) -> None:
        self.key_id = self._get_key_id()
        self.key_secret = self._get_key_secret()
        self.timeout = 15.0

    def _get_key_id(self) -> str | None:
        """Get Razorpay key ID from settings (env var)."""
        # Add RAZORPAY_KEY_ID to settings if not present
        import os
        return os.environ.get("RAZORPAY_KEY_ID")

    def _get_key_secret(self) -> str | None:
        import os
        secret = os.environ.get("RAZORPAY_KEY_SECRET")
        return secret

    @property
    def is_live(self) -> bool:
        """Whether the client makes real Razorpay API calls."""
        return (
            self.key_id is not None
            and self.key_secret is not None
            and not settings().is_development
        )

    @property
    def razorpay_key(self) -> str:
        """Public key ID for frontend checkout."""
        return self.key_id or "rzp_test_dev_key"

    async def create_order(
        self,
        amount: Decimal,
        receipt: str,
        notes: dict[str, str] | None = None,
    ) -> RazorpayOrder:
        """Create a Razorpay order (pre-payment step).

        Args:
            amount: Amount in ₹ (will be converted to paise)
            receipt: Platform receipt ID (payment number)
            notes: Additional metadata

        Returns:
            RazorpayOrder with order_id
        """
        amount_paise = int(amount * RUPEE_TO_PAISE)

        if not self.is_live:
            # Dev mode: simulate order creation
            fake_order_id = f"order_dev_{secrets.token_hex(12)}"
            logger.info(
                "razorpay.order_created.dev",
                order_id=fake_order_id,
                amount_paise=amount_paise,
                receipt=receipt,
            )
            return RazorpayOrder(
                order_id=fake_order_id,
                amount=amount_paise,
                currency="INR",
                status="created",
                receipt=receipt,
            )

        # Live mode: real API call
        payload = {
            "amount": amount_paise,
            "currency": "INR",
            "receipt": receipt,
            "notes": notes or {},
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.BASE_URL}/orders",
                    json=payload,
                    auth=(self.key_id, self.key_secret),
                )
        except httpx.HTTPError as e:
            logger.error("razorpay.create_order.network_error", error=str(e))
            raise RuntimeError(f"Razorpay API unavailable: {e}")

        if response.status_code != 200:
            error_data = response.json()
            logger.error(
                "razorpay.create_order.api_error",
                status=response.status_code,
                error=error_data,
            )
            raise RuntimeError(f"Razorpay order creation failed: {error_data}")

        data = response.json()
        logger.info(
            "razorpay.order_created",
            order_id=data["id"],
            amount=data["amount"],
            receipt=receipt,
        )

        return RazorpayOrder(
            order_id=data["id"],
            amount=data["amount"],
            currency=data["currency"],
            status=data["status"],
            receipt=data.get("receipt"),
        )

    def verify_payment_signature(
        self,
        order_id: str,
        payment_id: str,
        signature: str,
    ) -> bool:
        """Verify Razorpay payment signature.

        Razorpay signs the payment with HMAC-SHA256 using the key secret.
        The signature is: HMAC-SHA256(order_id + "|" + payment_id, key_secret)

        Args:
            order_id: Razorpay order ID
            payment_id: Razorpay payment ID
            signature: Signature from Razorpay callback

        Returns:
            True if signature is valid
        """
        if not self.is_live:
            # Dev mode: accept any signature
            logger.info("razorpay.signature_verified.dev", order_id=order_id, payment_id=payment_id)
            return True

        # Live mode: verify HMAC-SHA256 signature
        message = f"{order_id}|{payment_id}"
        expected_signature = hmac.new(
            self.key_secret.encode(),
            message.encode(),
            hashlib.sha256,
        ).hexdigest()

        is_valid = hmac.compare_digest(expected_signature, signature)

        if is_valid:
            logger.info("razorpay.signature_verified", order_id=order_id, payment_id=payment_id)
        else:
            logger.warning(
                "razorpay.signature_invalid",
                order_id=order_id,
                payment_id=payment_id,
            )

        return is_valid

    async def fetch_payment(self, payment_id: str) -> RazorpayPayment:
        """Fetch payment details from Razorpay."""
        if not self.is_live:
            return RazorpayPayment(
                verified=True,
                payment_id=payment_id,
                order_id=f"order_dev_{payment_id[-12:]}",
                amount=0,
                status="captured",
                method="upi",
                raw_response={"dev": True},
            )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.BASE_URL}/payments/{payment_id}",
                    auth=(self.key_id, self.key_secret),
                )
        except httpx.HTTPError as e:
            logger.error("razorpay.fetch_payment.network_error", error=str(e))
            raise RuntimeError(f"Razorpay API unavailable: {e}")

        if response.status_code != 200:
            raise RuntimeError(f"Razorpay fetch failed: {response.status_code}")

        data = response.json()
        return RazorpayPayment(
            verified=True,
            payment_id=data["id"],
            order_id=data.get("order_id", ""),
            amount=data["amount"],
            status=data["status"],
            method=data.get("method"),
            upi_id=data.get("vpa"),  # UPI ID
            raw_response=data,
        )

    async def process_refund(
        self,
        payment_id: str,
        amount: Decimal | None = None,
        notes: dict[str, str] | None = None,
    ) -> RazorpayRefund:
        """Process a refund for a captured payment.

        Args:
            payment_id: Razorpay payment ID
            amount: Refund amount (None = full refund)
            notes: Additional metadata

        Returns:
            RazorpayRefund with refund_id
        """
        amount_paise = int(amount * RUPEE_TO_PAISE) if amount else None

        if not self.is_live:
            fake_refund_id = f"rfd_dev_{secrets.token_hex(12)}"
            logger.info(
                "razorpay.refund_processed.dev",
                refund_id=fake_refund_id,
                payment_id=payment_id,
                amount_paise=amount_paise,
            )
            return RazorpayRefund(
                refund_id=fake_refund_id,
                payment_id=payment_id,
                amount=amount_paise or 0,
                status="processed",
                raw_response={"dev": True},
            )

        payload: dict[str, Any] = {"notes": notes or {}}
        if amount_paise:
            payload["amount"] = amount_paise

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.BASE_URL}/payments/{payment_id}/refund",
                    json=payload,
                    auth=(self.key_id, self.key_secret),
                )
        except httpx.HTTPError as e:
            logger.error("razorpay.refund.network_error", error=str(e))
            raise RuntimeError(f"Razorpay API unavailable: {e}")

        if response.status_code != 200:
            error_data = response.json()
            raise RuntimeError(f"Razorpay refund failed: {error_data}")

        data = response.json()
        logger.info(
            "razorpay.refund_processed",
            refund_id=data["id"],
            payment_id=payment_id,
            amount=data["amount"],
        )

        return RazorpayRefund(
            refund_id=data["id"],
            payment_id=payment_id,
            amount=data["amount"],
            status=data["status"],
            raw_response=data,
        )

    def verify_webhook_signature(self, body: str, signature: str) -> bool:
        """Verify Razorpay webhook signature.

        Razorpay signs webhooks with HMAC-SHA256 using the webhook secret.
        """
        if not self.is_live:
            return True

        webhook_secret = os.environ.get("RAZORPAY_WEBHOOK_SECRET", "")
        if not webhook_secret:
            logger.warning("razorpay.webhook_secret_not_set")
            return False

        expected = hmac.new(
            webhook_secret.encode(),
            body.encode(),
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, signature)

    def generate_upi_intent_url(
        self, order_id: str, amount_paise: int, payee_name: str = "KrishiSetu"
    ) -> str:
        """Generate UPI deep link URL for mobile UPI apps.

        Format: upi://pay?pa=PAYEE_VPA&pn=PAYEE_NAME&am=AMOUNT&cu=INR&tn=NOTES
        """
        # In production, use KrishiSetu's merchant VPA
        payee_vpa = os.environ.get("KRISHISETU_UPI_VPA", "krishisetu@razorpay")

        from urllib.parse import urlencode
        params = urlencode({
            "pa": payee_vpa,
            "pn": payee_name,
            "am": f"{amount_paise / 100:.2f}",
            "cu": "INR",
            "tn": f"KrishiSetu Order {order_id}",
        })
        return f"upi://pay?{params}"


# Singleton
_razorpay_client: RazorpayClient | None = None


def get_razorpay_client() -> RazorpayClient:
    global _razorpay_client
    if _razorpay_client is None:
        _razorpay_client = RazorpayClient()
    return _razorpay_client


# Need os import at module level
import os  # noqa: E402
