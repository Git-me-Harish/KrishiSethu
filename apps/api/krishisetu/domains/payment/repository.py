"""Database access layer for the payment domain."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import and_, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from krishisetu.domains.payment.models import (
    Payment,
    PaymentProvider,
    PaymentStatus,
    PaymentType,
    PaymentWebhook,
)


async def create_payment(
    db: AsyncSession,
    *,
    payment_number: str,
    user_id: UUID,
    payment_type: PaymentType,
    reference_id: UUID,
    reference_type: str,
    amount: Decimal,
    provider: PaymentProvider = PaymentProvider.RAZORPAY,
    is_escrow: bool = False,
    description: str | None = None,
    notes: dict | None = None,
) -> Payment:
    """Create a new payment record (status=created)."""
    payment = Payment(
        payment_number=payment_number,
        user_id=user_id,
        payment_type=payment_type.value,
        reference_id=reference_id,
        reference_type=reference_type,
        amount=amount,
        provider=provider.value,
        is_escrow=is_escrow,
        description=description,
        notes=notes,
    )
    db.add(payment)
    await db.flush()
    await db.refresh(payment)
    return payment


async def get_payment_by_id(db: AsyncSession, payment_id: UUID) -> Payment | None:
    result = await db.execute(select(Payment).where(Payment.id == payment_id))
    return result.scalar_one_or_none()


async def get_payment_by_number(db: AsyncSession, payment_number: str) -> Payment | None:
    result = await db.execute(
        select(Payment).where(Payment.payment_number == payment_number)
    )
    return result.scalar_one_or_none()


async def get_payment_by_reference(
    db: AsyncSession, reference_id: UUID, reference_type: str
) -> Payment | None:
    """Get the most recent payment for a reference (order/policy)."""
    result = await db.execute(
        select(Payment)
        .where(
            and_(
                Payment.reference_id == reference_id,
                Payment.reference_type == reference_type,
            )
        )
        .order_by(desc(Payment.created_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def find_settled_payment_for_reference(
    db: AsyncSession,
    *,
    reference_id: UUID,
    user_id: UUID,
    min_amount: Decimal,
) -> Payment | None:
    """Find a captured/released, non-refunded payment covering a reference.

    Used to prove a real payment exists before a policy/order is activated —
    a client-supplied payment reference is never sufficient.
    """
    result = await db.execute(
        select(Payment)
        .where(
            and_(
                Payment.reference_id == reference_id,
                Payment.user_id == user_id,
                Payment.status.in_(
                    [PaymentStatus.CAPTURED.value, PaymentStatus.RELEASED.value]
                ),
                Payment.amount_refunded == Decimal("0"),
                Payment.amount >= min_amount,
            )
        )
        .order_by(desc(Payment.created_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_payment_by_provider_order_id(
    db: AsyncSession, provider_order_id: str
) -> Payment | None:
    """Get the payment that owns a provider (Razorpay) order id.

    This is the join key for webhook reconciliation — the webhook payload
    carries the provider's order id, not ours.
    """
    result = await db.execute(
        select(Payment).where(Payment.provider_order_id == provider_order_id)
    )
    return result.scalar_one_or_none()


async def get_payment_by_provider_payment_id(
    db: AsyncSession, provider_payment_id: str
) -> Payment | None:
    """Get a payment by the provider's payment id (fallback webhook join key)."""
    result = await db.execute(
        select(Payment).where(Payment.provider_payment_id == provider_payment_id)
    )
    return result.scalar_one_or_none()


async def list_payments_by_user(
    db: AsyncSession,
    user_id: UUID,
    *,
    status: PaymentStatus | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Payment], int]:
    """List a user's payments."""
    count_query = select(func.count(Payment.id)).where(Payment.user_id == user_id)
    if status:
        count_query = count_query.where(Payment.status == status)
    total = (await db.execute(count_query)).scalar_one()

    offset = (page - 1) * page_size
    query = (
        select(Payment)
        .where(Payment.user_id == user_id)
        .order_by(desc(Payment.created_at))
        .offset(offset)
        .limit(page_size)
    )
    if status:
        query = query.where(Payment.status == status)
    result = await db.execute(query)
    return list(result.scalars().all()), total


async def update_payment(
    db: AsyncSession,
    payment_id: UUID,
    **fields: Any,
) -> Payment | None:
    """Update payment fields."""
    if not fields:
        result = await db.execute(select(Payment).where(Payment.id == payment_id))
        return result.scalar_one_or_none()

    await db.execute(
        update(Payment).where(Payment.id == payment_id).values(**fields)
    )
    await db.flush()
    result = await db.execute(select(Payment).where(Payment.id == payment_id))
    return result.scalar_one_or_none()


async def mark_payment_pending(
    db: AsyncSession,
    payment_id: UUID,
    provider_order_id: str,
    upi_intent_url: str | None = None,
) -> Payment | None:
    """Mark payment as pending (Razorpay order created)."""
    return await update_payment(
        db,
        payment_id,
        status=PaymentStatus.PENDING.value,
        provider_order_id=provider_order_id,
        upi_intent_url=upi_intent_url,
        updated_at=datetime.now(UTC),
    )


async def mark_payment_captured_if_pending(
    db: AsyncSession,
    payment_id: UUID,
    provider_payment_id: str,
    provider_signature: str | None = None,
    payment_method: str | None = None,
    upi_id: str | None = None,
    raw_response: dict | None = None,
) -> tuple[Payment | None, bool]:
    """Atomically capture a payment that is still created/pending.

    Compare-and-set: the UPDATE only matches rows still in created/pending, so
    when the Razorpay JS callback and the webhook race for the same payment,
    exactly one of them transitions it. Returns (payment, transitioned) — a
    False means someone else already captured it, which is not an error.

    Scope boundary: `authorized` is intentionally NOT matched. Nothing in the
    codebase sets that status today, so widening the CAS now would be
    speculative. Whoever adds an authorize-then-capture flow (Razorpay's
    payment.authorized event, or manual capture) must revisit this function —
    and must also ensure an authorize-only payment does NOT trigger the
    non-escrow auto-release in services._capture_payment, since no money has
    moved at that point.
    """
    now = datetime.now(UTC)
    result = await db.execute(
        update(Payment)
        .where(
            and_(
                Payment.id == payment_id,
                Payment.status.in_(
                    [PaymentStatus.CREATED.value, PaymentStatus.PENDING.value]
                ),
            )
        )
        .values(
            status=PaymentStatus.CAPTURED.value,
            provider_payment_id=provider_payment_id,
            provider_signature=provider_signature,
            payment_method=payment_method,
            upi_id=upi_id,
            raw_provider_response=raw_response,
            paid_at=now,
            updated_at=now,
        )
    )
    await db.flush()
    transitioned = result.rowcount > 0
    return await get_payment_by_id(db, payment_id), transitioned


async def mark_payment_failed(
    db: AsyncSession,
    payment_id: UUID,
    reason: str | None = None,
) -> Payment | None:
    """Mark payment as failed."""
    return await update_payment(
        db,
        payment_id,
        status=PaymentStatus.FAILED.value,
        notes={"failure_reason": reason} if reason else None,
        updated_at=datetime.now(UTC),
    )


async def release_escrow(
    db: AsyncSession,
    payment_id: UUID,
    released_to_user_id: UUID,
) -> Payment | None:
    """Release a captured payment to supplier/insurer.

    Compare-and-set on `captured`, so a payment can only ever be released
    once even if two callers race (webhook + JS callback).
    """
    now = datetime.now(UTC)
    await db.execute(
        update(Payment)
        .where(
            and_(
                Payment.id == payment_id,
                Payment.status == PaymentStatus.CAPTURED.value,
            )
        )
        .values(
            status=PaymentStatus.RELEASED.value,
            escrow_released_at=now,
            released_to_user_id=released_to_user_id,
            updated_at=now,
        )
    )
    await db.flush()
    return await get_payment_by_id(db, payment_id)


async def process_refund(
    db: AsyncSession,
    payment_id: UUID,
    refund_amount: Decimal,
    reason: str,
) -> Payment | None:
    """Process a refund for a payment."""
    payment = await get_payment_by_id(db, payment_id)
    if not payment:
        return None

    new_refunded = payment.amount_refunded + refund_amount
    new_status = (
        PaymentStatus.REFUNDED.value
        if new_refunded >= payment.amount
        else PaymentStatus.PARTIALLY_REFUNDED.value
    )

    return await update_payment(
        db,
        payment_id,
        status=new_status,
        amount_refunded=new_refunded,
        refund_reason=reason,
        refunded_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


# ---------------------------------------------------------------------------
# Webhook queries
# ---------------------------------------------------------------------------


async def create_webhook(
    db: AsyncSession,
    *,
    provider: str,
    event_id: str,
    event_type: str,
    payment_id: UUID | None,
    raw_payload: dict,
    headers: dict | None,
    signature_verified: bool,
) -> PaymentWebhook:
    """Record a webhook event."""
    webhook = PaymentWebhook(
        provider=provider,
        event_id=event_id,
        event_type=event_type,
        payment_id=payment_id,
        raw_payload=raw_payload,
        headers=headers,
        signature_verified=signature_verified,
    )
    db.add(webhook)
    await db.flush()
    await db.refresh(webhook)
    return webhook


async def webhook_exists(db: AsyncSession, provider: str, event_id: str) -> bool:
    """Check if a webhook has already been processed (idempotency)."""
    result = await db.execute(
        select(func.count(PaymentWebhook.id)).where(
            and_(
                PaymentWebhook.provider == provider,
                PaymentWebhook.event_id == event_id,
            )
        )
    )
    return result.scalar_one() > 0


async def link_webhook_payment(
    db: AsyncSession, webhook_id: UUID, payment_id: UUID
) -> None:
    """Attach a resolved payment to a recorded webhook (audit trail)."""
    await db.execute(
        update(PaymentWebhook)
        .where(PaymentWebhook.id == webhook_id)
        .values(payment_id=payment_id)
    )
    await db.flush()


async def mark_webhook_processed(db: AsyncSession, webhook_id: UUID) -> None:
    """Mark a webhook as processed."""
    await db.execute(
        update(PaymentWebhook)
        .where(PaymentWebhook.id == webhook_id)
        .values(processed=True, processed_at=datetime.now(UTC))
    )
    await db.flush()
