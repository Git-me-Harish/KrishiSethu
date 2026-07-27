"""Pydantic schemas for the payment domain."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PaymentTypeEnum(str, Enum):
    MARKETPLACE_ORDER = "marketplace_order"
    INSURANCE_PREMIUM = "insurance_premium"
    INSURANCE_PAYOUT = "insurance_payout"
    REFUND = "refund"


class PaymentStatusEnum(str, Enum):
    CREATED = "created"
    PENDING = "pending"
    CAPTURED = "captured"
    FAILED = "failed"
    REFUNDED = "refunded"
    RELEASED = "released"
    CANCELLED = "cancelled"


class PaymentProviderEnum(str, Enum):
    RAZORPAY = "razorpay"
    UPI_DIRECT = "upi_direct"
    COD = "cod"


class CreatePaymentRequest(BaseModel):
    """Request to create a new payment.

    The amount is NOT accepted from the client — it is derived server-side
    from the referenced marketplace order / insurance policy.
    """

    payment_type: PaymentTypeEnum
    reference_id: UUID
    reference_type: str = Field(..., description="order, insurance_policy")
    description: str | None = None


class CreatePaymentResponse(BaseModel):
    """Response after creating a payment — includes Razorpay checkout details."""

    payment_id: UUID
    payment_number: str
    amount: Decimal
    currency: str = "INR"
    status: str

    # Razorpay checkout
    provider: str
    provider_order_id: str | None = None
    razorpay_key: str | None = None
    checkout_options: dict | None = None

    # UPI
    upi_intent_url: str | None = None

    # For frontend redirect
    checkout_url: str | None = None


class VerifyPaymentRequest(BaseModel):
    """Request to verify a completed payment (from Razorpay callback)."""

    payment_id: UUID
    provider_payment_id: str = Field(
        ...,
        pattern=r"^pay_[A-Za-z0-9]+$",
        max_length=64,
        description="Razorpay payment ID (pay_XXXXX)",
    )
    provider_order_id: str = Field(..., description="Razorpay order ID (order_XXXXX)")
    provider_signature: str = Field(..., description="Razorpay signature")
    payment_method: str | None = Field(default=None, description="upi, card, netbanking")
    upi_id: str | None = None


class PaymentResponse(BaseModel):
    """Full payment details."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    payment_number: str
    user_id: UUID
    payment_type: str
    reference_id: UUID
    reference_type: str
    amount: Decimal
    currency: str
    amount_refunded: Decimal
    status: str
    provider: str
    payment_method: str | None
    provider_order_id: str | None
    provider_payment_id: str | None
    is_escrow: bool
    escrow_released_at: datetime | None
    released_to_user_id: UUID | None
    refund_reason: str | None
    refunded_at: datetime | None
    description: str | None
    created_at: datetime
    paid_at: datetime | None


class RefundRequest(BaseModel):
    """Request to process a refund."""

    payment_id: UUID
    amount: Decimal | None = Field(default=None, gt=0, description="Partial refund amount. If None, full refund.")
    reason: str = Field(..., min_length=5, max_length=500)


class ReleaseEscrowRequest(BaseModel):
    """Request to release escrow to supplier.

    `released_to_user_id` is accepted for backwards compatibility only — the
    payee is always derived server-side from the order's supplier.
    """

    payment_id: UUID
    released_to_user_id: UUID | None = None


class WebhookPayload(BaseModel):
    """Razorpay webhook payload (raw, for signature verification)."""

    raw_body: str
    signature: str
    event_id: str | None = None
