"""SQLAlchemy ORM models for the payment domain.

Tables:
- payments        — All payment transactions (orders, premiums, refunds)
- payment_webhooks — Webhook event log (for idempotency and audit)

Payment types:
- marketplace_order — Payment for marketplace order (escrow)
- insurance_premium — Insurance premium payment (direct)
- insurance_payout  — Insurance claim payout (DBT to farmer)
- refund            — Refund for cancelled order/rejected claim

Payment providers:
- razorpay — Razorpay payment gateway (UPI, cards, netbanking, wallets)
- upi_direct — Direct UPI (for future, without gateway)
- cod — Cash on delivery (limited)
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from krishisetu.core.database import Base


class PaymentType(str, Enum):
    """Type of payment transaction."""

    MARKETPLACE_ORDER = "marketplace_order"
    INSURANCE_PREMIUM = "insurance_premium"
    INSURANCE_PAYOUT = "insurance_payout"
    SCHEME_FEE = "scheme_fee"
    REFUND = "refund"


class PaymentStatus(str, Enum):
    """Status of a payment transaction.

    Lifecycle:
    - created: Payment record created, awaiting farmer action
    - pending: Razorpay order created, farmer redirected to payment
    - authorized: Payment authorized but not captured
    - captured: Payment captured (held in escrow for marketplace)
    - failed: Payment failed
    - refunded: Full refund processed
    - partially_refunded: Partial refund processed
    - released: Escrow released to supplier/insurer
    - cancelled: Payment cancelled before completion
    """

    CREATED = "created"
    PENDING = "pending"
    AUTHORIZED = "authorized"
    CAPTURED = "captured"
    FAILED = "failed"
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"
    RELEASED = "released"
    CANCELLED = "cancelled"


class PaymentProvider(str, Enum):
    """Payment service provider."""

    RAZORPAY = "razorpay"
    UPI_DIRECT = "upi_direct"
    COD = "cod"
    DBT = "dbt"  # Direct Benefit Transfer (for insurance payouts)


class PaymentMethod(str, Enum):
    """Specific payment method used by the farmer."""

    UPI = "upi"
    CARD = "card"
    NETBANKING = "netbanking"
    WALLET = "wallet"
    EMI = "emi"
    COD = "cod"
    BANK_TRANSFER = "bank_transfer"


class Payment(Base):
    """A payment transaction on the platform.

    Each payment is linked to either:
    - An order (marketplace_order type)
    - An insurance policy (insurance_premium type)
    - An insurance claim (insurance_payout type)

    For marketplace orders, the payment is held in escrow (captured but
    not released) until delivery confirmation.
    """

    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("payment_number", name="payments_number_unique"),
        {"schema": "commerce"},
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        server_default=func.gen_random_uuid(),
        primary_key=True,
        nullable=False,
    )
    payment_number: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True,
        comment="Platform-generated payment number: KS-PAY-YYYYMMDD-XXXXXXXX",
    )

    # Ownership
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("identity.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Payment type and linked entity
    payment_type: Mapped[PaymentType] = mapped_column(
        String(30), nullable=False, index=True,
    )
    reference_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=False,
        index=True,
        comment="FK to orders.id, insurance_policies.id, or insurance_claims.id",
    )
    reference_type: Mapped[str] = mapped_column(
        String(30), nullable=False,
        comment="order, insurance_policy, insurance_claim",
    )

    # Amount
    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False,
        comment="Payment amount in ₹",
    )
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="INR",
    )
    amount_refunded: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), server_default=func.text("0"), nullable=False, default=Decimal("0"),
    )

    # Status
    status: Mapped[PaymentStatus] = mapped_column(
        String(30),
        server_default=func.text("'created'"),
        nullable=False,
        default=PaymentStatus.CREATED,
        index=True,
    )

    # Provider
    provider: Mapped[PaymentProvider] = mapped_column(
        String(20), nullable=False, default=PaymentProvider.RAZORPAY,
    )
    payment_method: Mapped[PaymentMethod | None] = mapped_column(
        String(20), nullable=True,
        comment="UPI, card, netbanking, etc. (filled after payment)",
    )

    # Razorpay references
    provider_order_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
        comment="Razorpay order ID (order_XXXXX)",
    )
    provider_payment_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
        comment="Razorpay payment ID (pay_XXXXX)",
    )
    provider_signature: Mapped[str | None] = mapped_column(
        String(256), nullable=True,
        comment="Razorpay signature for verification",
    )

    # UPI details (for UPI payments)
    upi_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
        comment="UPI ID used for payment (e.g., farmer@upi)",
    )
    upi_intent_url: Mapped[str | None] = mapped_column(
        String(512), nullable=True,
        comment="UPI deep link URL for mobile apps",
    )

    # Escrow
    is_escrow: Mapped[bool] = mapped_column(
        Boolean, server_default=func.text("false"), nullable=False, default=False,
        comment="True if payment held in escrow (marketplace orders)",
    )
    escrow_released_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    released_to_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("identity.users.id", ondelete="SET NULL"),
        nullable=True,
        comment="User (supplier/insurer) who received the released funds",
    )

    # Bank details (for DBT payouts)
    bank_account_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    bank_ifsc: Mapped[str | None] = mapped_column(String(15), nullable=True)
    bank_payout_reference: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
        comment="Bank transfer reference for DBT payouts",
    )

    # Refund
    refund_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    refunded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # Metadata
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    raw_provider_response: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
        comment="Full provider response for audit",
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.NOW(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.NOW(), nullable=False,
    )
    paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    @property
    def is_paid(self) -> bool:
        """Whether the money has actually been taken.

        AUTHORIZED is deliberately excluded: an authorized payment has funds
        reserved, not captured, so treating it as paid would credit money the
        platform does not hold.
        """
        return self.status in (
            PaymentStatus.CAPTURED,
            PaymentStatus.RELEASED,
        )

    @property
    def is_refundable(self) -> bool:
        return self.status in (
            PaymentStatus.CAPTURED,
            PaymentStatus.RELEASED,
            PaymentStatus.PARTIALLY_REFUNDED,
        )

    @property
    def refundable_amount(self) -> Decimal:
        return self.amount - self.amount_refunded

    def __repr__(self) -> str:
        return (
            f"<Payment number={self.payment_number} type={self.payment_type} "
            f"amount={self.amount} status={self.status}>"
        )


class PaymentWebhook(Base):
    """Webhook event log from payment provider (Razorpay).

    Used for:
    - Idempotency: Don't process the same webhook twice
    - Audit trail: Full record of all provider events
    - Debugging: Raw payload stored for investigation
    """

    __tablename__ = "payment_webhooks"
    __table_args__ = (
        UniqueConstraint("provider", "event_id", name="payment_webhooks_event_unique"),
        {"schema": "commerce"},
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        server_default=func.gen_random_uuid(),
        primary_key=True,
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    event_id: Mapped[str] = mapped_column(
        String(100), nullable=False,
        comment="Provider's unique event ID",
    )
    event_type: Mapped[str] = mapped_column(
        String(50), nullable=False,
        comment="payment.captured, payment.failed, refund.processed, etc.",
    )

    # Linked payment
    payment_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("commerce.payments.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Verification
    signature_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False,
    )
    processed: Mapped[bool] = mapped_column(
        Boolean, server_default=func.text("false"), nullable=False, default=False,
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # Raw data
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    headers: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.NOW(), nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<PaymentWebhook provider={self.provider} event={self.event_type} "
            f"processed={self.processed}>"
        )
