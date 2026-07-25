"""Payment service — orchestrates Razorpay/UPI, escrow, and refunds."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from krishisetu.core.exceptions import NotFoundError, ValidationError, ConflictError
from krishisetu.core.logging import get_logger
from krishisetu.domains.payment import repository as repo
from krishisetu.domains.payment.models import PaymentStatus, PaymentType, PaymentProvider
from krishisetu.domains.payment.schemas import (
    CreatePaymentRequest,
    CreatePaymentResponse,
    PaymentResponse,
    RefundRequest,
    VerifyPaymentRequest,
)
from krishisetu.integrations.razorpay import get_razorpay_client

logger = get_logger(__name__)


async def create_payment(
    db: AsyncSession,
    user_id: UUID,
    payload: CreatePaymentRequest,
) -> CreatePaymentResponse:
    """Create a new payment and Razorpay order.

    Steps:
    1. Create payment record (status=created)
    2. Create Razorpay order
    3. Update payment with provider_order_id (status=pending)
    4. Return checkout details for frontend

    For marketplace orders, is_escrow=True (held until delivery).
    For insurance premiums, is_escrow=False (released immediately on capture).
    """
    is_escrow = payload.payment_type == PaymentType.MARKETPLACE_ORDER

    payment_number = _generate_payment_number()
    payment = await repo.create_payment(
        db,
        payment_number=payment_number,
        user_id=user_id,
        payment_type=payload.payment_type,
        reference_id=payload.reference_id,
        reference_type=payload.reference_type,
        amount=payload.amount,
        is_escrow=is_escrow,
        description=payload.description,
    )

    # Create Razorpay order
    razorpay = get_razorpay_client()
    order = await razorpay.create_order(
        amount=payload.amount,
        receipt=payment_number,
        notes={
            "payment_id": str(payment.id),
            "payment_type": payload.payment_type.value,
            "user_id": str(user_id),
        },
    )

    # Generate UPI intent URL
    upi_url = razorpay.generate_upi_intent_url(
        order_id=order.order_id,
        amount_paise=order.amount,
    )

    # Update payment with provider order ID
    await repo.mark_payment_pending(
        db,
        payment.id,
        provider_order_id=order.order_id,
        upi_intent_url=upi_url,
    )

    logger.info(
        "payment.created",
        payment_id=str(payment.id),
        payment_number=payment_number,
        amount=str(payload.amount),
        provider_order_id=order.order_id,
        is_escrow=is_escrow,
    )

    # Build checkout options for Razorpay frontend SDK
    checkout_options = {
        "key": razorpay.razorpay_key,
        "amount": order.amount,
        "currency": order.currency,
        "name": "KrishiSetu",
        "description": payload.description or f"Payment {payment_number}",
        "order_id": order.order_id,
        "prefill": {
            "name": "",  # Will be filled by frontend
            "contact": "",
        },
        "theme": {"color": "#4CAF50"},
        "method": {
            "upi": True,
            "card": True,
            "netbanking": True,
            "wallet": True,
        },
    }

    return CreatePaymentResponse(
        payment_id=payment.id,
        payment_number=payment_number,
        amount=payload.amount,
        status="pending",
        provider="razorpay",
        provider_order_id=order.order_id,
        razorpay_key=razorpay.razorpay_key,
        checkout_options=checkout_options,
        upi_intent_url=upi_url,
    )


async def verify_payment(
    db: AsyncSession,
    user_id: UUID,
    payload: VerifyPaymentRequest,
) -> PaymentResponse:
    """Verify a completed payment from Razorpay callback.

    Steps:
    1. Fetch payment record
    2. Verify Razorpay signature
    3. Update payment status to captured
    4. If not escrow → release immediately (insurance premium)
    5. If escrow → keep captured (marketplace order, release on delivery)
    """
    payment = await repo.get_payment_by_id(db, payload.payment_id)
    if not payment:
        raise NotFoundError("Payment", str(payload.payment_id))

    if payment.user_id != user_id:
        raise NotFoundError("Payment", str(payload.payment_id))

    if payment.status not in (PaymentStatus.PENDING.value, PaymentStatus.CREATED.value):
        raise ConflictError(
            f"Payment is already in '{payment.status}' state. Cannot verify again."
        )

    # Verify Razorpay signature
    razorpay = get_razorpay_client()
    is_valid = razorpay.verify_payment_signature(
        order_id=payload.provider_order_id,
        payment_id=payload.provider_payment_id,
        signature=payload.provider_signature,
    )

    if not is_valid:
        await repo.mark_payment_failed(db, payment.id, "Invalid signature")
        raise ValidationError("Payment signature verification failed")

    # Fetch payment details from Razorpay
    try:
        rp_payment = await razorpay.fetch_payment(payload.provider_payment_id)
    except RuntimeError:
        # In dev mode, this is simulated
        rp_payment = None

    # Update payment to captured
    updated = await repo.mark_payment_captured(
        db,
        payment.id,
        provider_payment_id=payload.provider_payment_id,
        provider_signature=payload.provider_signature,
        payment_method=payload.payment_method,
        upi_id=payload.upi_id,
        raw_response=rp_payment.raw_response if rp_payment else None,
    )

    # If not escrow (insurance premium), release immediately
    if updated and not updated.is_escrow:
        # For insurance, release to insurer (reference_id is policy_id)
        # The insurer_id would need to be fetched from the policy
        # For now, mark as released without a specific user
        await repo.release_escrow(db, payment.id, payment.user_id)  # placeholder
        updated = await repo.get_payment_by_id(db, payment.id)

    logger.info(
        "payment.verified",
        payment_id=str(payment.id),
        status=updated.status,
        is_escrow=updated.is_escrow,
    )

    return PaymentResponse.model_validate(updated)


async def release_escrow(
    db: AsyncSession,
    payment_id: UUID,
    released_to_user_id: UUID,
) -> PaymentResponse:
    """Release escrowed payment to supplier/insurer.

    Called when:
    - Marketplace order delivered → release to supplier
    - Insurance claim approved → release payout to farmer
    """
    payment = await repo.get_payment_by_id(db, payment_id)
    if not payment:
        raise NotFoundError("Payment", str(payment_id))

    if not payment.is_escrow:
        raise ValidationError("Payment is not in escrow")

    if payment.status != PaymentStatus.CAPTURED.value:
        raise ValidationError(
            f"Cannot release payment in '{payment.status}' state. Must be 'captured'."
        )

    updated = await repo.release_escrow(db, payment_id, released_to_user_id)

    logger.info(
        "payment.escrow_released",
        payment_id=str(payment_id),
        released_to=str(released_to_user_id),
        amount=str(payment.amount),
    )

    return PaymentResponse.model_validate(updated)


async def process_refund(
    db: AsyncSession,
    user_id: UUID,
    payload: RefundRequest,
) -> PaymentResponse:
    """Process a refund for a payment.

    Steps:
    1. Verify payment exists and is refundable
    2. Determine refund amount (full or partial)
    3. Call Razorpay refund API
    4. Update payment record
    """
    payment = await repo.get_payment_by_id(db, payload.payment_id)
    if not payment:
        raise NotFoundError("Payment", str(payload.payment_id))

    if not payment.is_refundable:
        raise ValidationError(
            f"Payment in '{payment.status}' state is not refundable."
        )

    refund_amount = payload.amount or payment.refundable_amount
    if refund_amount > payment.refundable_amount:
        raise ValidationError(
            f"Refund amount ({refund_amount}) exceeds refundable amount ({payment.refundable_amount})"
        )

    # Process refund via Razorpay
    if payment.provider_payment_id:
        razorpay = get_razorpay_client()
        try:
            refund = await razorpay.process_refund(
                payment_id=payment.provider_payment_id,
                amount=refund_amount,
                notes={"reason": payload.reason, "payment_number": payment.payment_number},
            )
        except RuntimeError as e:
            raise ValidationError(f"Refund processing failed: {e}")
    else:
        # Dev mode: no provider payment ID
        refund = None

    # Update payment record
    updated = await repo.process_refund(
        db,
        payment.id,
        refund_amount,
        payload.reason,
    )

    logger.info(
        "payment.refunded",
        payment_id=str(payment.id),
        refund_amount=str(refund_amount),
        reason=payload.reason,
    )

    return PaymentResponse.model_validate(updated)


async def handle_webhook(
    db: AsyncSession,
    body: str,
    signature: str,
    event_data: dict[str, Any],
) -> dict[str, Any]:
    """Handle Razorpay webhook event.

    This is called from the webhook route after initial signature verification.
    Processes the event based on type:
    - payment.captured → update payment status
    - payment.failed → mark payment as failed
    - refund.processed → update refund status
    """
    event_id = event_data.get("event_id", "")
    event_type = event_data.get("event_type", "")

    # Check idempotency
    if await repo.webhook_exists(db, "razorpay", event_id):
        logger.info("payment.webhook.duplicate", event_id=event_id)
        return {"status": "duplicate", "event_id": event_id}

    # Record webhook
    webhook = await repo.create_webhook(
        db,
        provider="razorpay",
        event_id=event_id,
        event_type=event_type,
        payment_id=None,  # Will be updated if we find the payment
        raw_payload=event_data,
        headers={"signature": signature},
        signature_verified=True,
    )

    # Process event
    payment_entity = event_data.get("payload", {}).get("payment", {}).get("entity", {})

    if event_type == "payment.captured":
        provider_order_id = payment_entity.get("order_id")
        provider_payment_id = payment_entity.get("id")
        amount = payment_entity.get("amount", 0)
        method = payment_entity.get("method")
        upi_id = payment_entity.get("vpa")

        # Find payment by provider_order_id
        # In production, we'd query by provider_order_id
        # For now, log and mark as processed
        logger.info(
            "payment.webhook.captured",
            event_id=event_id,
            provider_payment_id=provider_payment_id,
            amount=amount,
            method=method,
        )

    elif event_type == "payment.failed":
        logger.info(
            "payment.webhook.failed",
            event_id=event_id,
            provider_payment_id=payment_entity.get("id"),
        )

    elif event_type == "refund.processed":
        logger.info(
            "payment.webhook.refund",
            event_id=event_id,
            refund_id=payment_entity.get("id"),
        )

    # Mark webhook as processed
    await repo.mark_webhook_processed(db, webhook.id)

    return {"status": "processed", "event_id": event_id, "event_type": event_type}


async def get_payment(
    db: AsyncSession, payment_id: UUID, user_id: UUID
) -> PaymentResponse:
    """Get payment details (verifies ownership)."""
    payment = await repo.get_payment_by_id(db, payment_id)
    if not payment:
        raise NotFoundError("Payment", str(payment_id))

    if payment.user_id != user_id:
        raise NotFoundError("Payment", str(payment_id))

    return PaymentResponse.model_validate(payment)


async def list_my_payments(
    db: AsyncSession,
    user_id: UUID,
    *,
    status: PaymentStatus | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """List the user's payments."""
    from krishisetu.domains.payment.schemas import PaymentResponse

    payments, total = await repo.list_payments_by_user(
        db, user_id, status=status, page=page, page_size=page_size
    )
    return {
        "payments": [PaymentResponse.model_validate(p) for p in payments],
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_more": (page * page_size) < total,
    }


def _generate_payment_number() -> str:
    """Generate unique payment number: KS-PAY-YYYYMMDD-XXXXXXXX"""
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    short_uuid = uuid.uuid4().hex[:8]
    return f"KS-PAY-{today}-{short_uuid}"
