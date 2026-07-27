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
from krishisetu.integrations.razorpay import RUPEE_TO_PAISE, get_razorpay_client

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

    The amount is never taken from the request — it is resolved from the
    referenced order/policy, which must belong to the caller.
    """
    is_escrow = payload.payment_type == PaymentType.MARKETPLACE_ORDER

    amount = await _resolve_payment_amount(db, user_id, payload)

    payment_number = _generate_payment_number()
    payment = await repo.create_payment(
        db,
        payment_number=payment_number,
        user_id=user_id,
        payment_type=payload.payment_type,
        reference_id=payload.reference_id,
        reference_type=payload.reference_type,
        amount=amount,
        is_escrow=is_escrow,
        description=payload.description,
    )

    # Create Razorpay order
    razorpay = get_razorpay_client()
    order = await razorpay.create_order(
        amount=amount,
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
        amount=str(amount),
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
        amount=amount,
        status="pending",
        provider="razorpay",
        provider_order_id=order.order_id,
        razorpay_key=razorpay.razorpay_key,
        checkout_options=checkout_options,
        upi_intent_url=upi_url,
    )


_ORDER_REFERENCE_TYPES = {"order", "marketplace_order"}
_POLICY_REFERENCE_TYPES = {"insurance_policy", "policy"}


async def _expected_amount_for_reference(
    db: AsyncSession,
    user_id: UUID,
    payment_type: Any,
    reference_id: UUID,
    reference_type: str | None,
) -> Decimal:
    """The single source of truth for what a payment should cost.

    Used both when creating a payment and when reconciling a webhook, so the
    two can never disagree about the expected amount.
    """
    normalized = (reference_type or "").strip().lower()

    if payment_type == PaymentType.MARKETPLACE_ORDER:
        if normalized not in _ORDER_REFERENCE_TYPES:
            raise ValidationError(
                f"reference_type '{reference_type}' is not valid for a "
                f"marketplace order payment."
            )
        from krishisetu.domains.marketplace import repository as marketplace_repo

        order = await marketplace_repo.get_order_by_id(
            db, reference_id, include_items=False
        )
        if not order or order["farmer_id"] != user_id:
            raise ValidationError("Order not found for this user")
        return Decimal(str(order["total_amount"]))

    if payment_type == PaymentType.INSURANCE_PREMIUM:
        if normalized not in _POLICY_REFERENCE_TYPES:
            raise ValidationError(
                f"reference_type '{reference_type}' is not valid for an "
                f"insurance premium payment."
            )
        from krishisetu.domains.insurance import repository as insurance_repo

        policy = await insurance_repo.get_policy_by_id(db, reference_id)
        if not policy or policy["farmer_id"] != user_id:
            raise ValidationError("Insurance policy not found for this user")
        return Decimal(str(policy["premium_amount"]))

    # Payouts and refunds are initiated by the platform, never by a client.
    raise ValidationError(
        f"Payment type '{getattr(payment_type, 'value', payment_type)}' "
        f"cannot be created by a client."
    )


async def _resolve_payment_amount(
    db: AsyncSession,
    user_id: UUID,
    payload: CreatePaymentRequest,
) -> Decimal:
    """Resolve the payable amount server-side from the referenced entity.

    The client may only name *what* it is paying for; the amount always comes
    from the marketplace order / insurance policy row, and the reference must
    belong to the caller.
    """
    return await _expected_amount_for_reference(
        db,
        user_id,
        payload.payment_type,
        payload.reference_id,
        payload.reference_type,
    )


async def _capture_payment(
    db: AsyncSession,
    payment: Any,
    *,
    provider_payment_id: str,
    provider_signature: str | None,
    payment_method: str | None,
    upi_id: str | None,
    raw_response: dict[str, Any] | None,
    source: str,
) -> Any:
    """Transition a pending payment to captured, releasing it if non-escrow.

    Shared by the in-page verify callback and webhook reconciliation so both
    routes produce identical state. Idempotent: the capture is a
    compare-and-set, and the non-escrow release only runs for the caller that
    actually performed the transition, so at most one release happens.
    """
    updated, transitioned = await repo.mark_payment_captured_if_pending(
        db,
        payment.id,
        provider_payment_id=provider_payment_id,
        provider_signature=provider_signature,
        payment_method=payment_method,
        upi_id=upi_id,
        raw_response=raw_response,
    )

    if not transitioned:
        logger.info(
            "payment.capture_noop",
            payment_id=str(payment.id),
            status=updated.status if updated else None,
            source=source,
        )
        return updated

    # If not escrow (insurance premium), release immediately.
    if updated and not updated.is_escrow:
        # For insurance, release to insurer (reference_id is policy_id).
        # The insurer_id would need to be fetched from the policy.
        # For now, mark as released without a specific user.
        await repo.release_escrow(db, payment.id, payment.user_id)  # placeholder
        updated = await repo.get_payment_by_id(db, payment.id)

    logger.info(
        "payment.captured",
        payment_id=str(payment.id),
        status=updated.status if updated else None,
        is_escrow=updated.is_escrow if updated else None,
        source=source,
    )
    return updated


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

    The webhook may have reconciled this payment first (it always does for the
    UPI deep-link flow). In that case the signature is still checked, and a
    matching provider_payment_id returns the already-captured payment rather
    than a conflict — both orderings converge on one captured payment.
    """
    payment = await repo.get_payment_by_id(db, payload.payment_id)
    if not payment:
        raise NotFoundError("Payment", str(payload.payment_id))

    if payment.user_id != user_id:
        raise NotFoundError("Payment", str(payload.payment_id))

    already_settled = payment.status in (
        PaymentStatus.CAPTURED.value,
        PaymentStatus.RELEASED.value,
    )
    if not already_settled and payment.status not in (
        PaymentStatus.PENDING.value,
        PaymentStatus.CREATED.value,
    ):
        raise ConflictError(
            f"Payment is already in '{payment.status}' state. Cannot verify again."
        )

    # Verify Razorpay signature (always — never short-circuited by state)
    razorpay = get_razorpay_client()
    is_valid = razorpay.verify_payment_signature(
        order_id=payload.provider_order_id,
        payment_id=payload.provider_payment_id,
        signature=payload.provider_signature,
    )

    if not is_valid:
        if not already_settled:
            await repo.mark_payment_failed(db, payment.id, "Invalid signature")
        raise ValidationError("Payment signature verification failed")

    if already_settled:
        if payment.provider_payment_id != payload.provider_payment_id:
            raise ConflictError(
                f"Payment is already in '{payment.status}' state for a different "
                f"provider payment id."
            )
        logger.info(
            "payment.verify_already_settled",
            payment_id=str(payment.id),
            status=payment.status,
        )
        return PaymentResponse.model_validate(payment)

    # Fetch payment details from Razorpay
    try:
        rp_payment = await razorpay.fetch_payment(payload.provider_payment_id)
    except RuntimeError:
        # In dev mode, this is simulated
        rp_payment = None

    updated = await _capture_payment(
        db,
        payment,
        provider_payment_id=payload.provider_payment_id,
        provider_signature=payload.provider_signature,
        payment_method=payload.payment_method,
        upi_id=payload.upi_id,
        raw_response=rp_payment.raw_response if rp_payment else None,
        source="verify_callback",
    )

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
    released_by_user_id: UUID,
) -> PaymentResponse:
    """Release escrowed payment to the supplier of the referenced order.

    Called when a marketplace order is delivered. The payee is derived from
    the order's supplier — never from the request body — and the caller must
    be an admin (enforced on the route).
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

    released_to_user_id = await _resolve_escrow_payee(db, payment)

    updated = await repo.release_escrow(db, payment_id, released_to_user_id)

    logger.info(
        "payment.escrow_released",
        payment_id=str(payment_id),
        released_to=str(released_to_user_id),
        released_by=str(released_by_user_id),
        amount=str(payment.amount),
    )

    return PaymentResponse.model_validate(updated)


async def _resolve_escrow_payee(db: AsyncSession, payment: Any) -> UUID:
    """Determine who an escrowed payment is released to.

    Marketplace escrow is released to the supplier that fulfils the order.
    Orders spanning multiple suppliers cannot be released as a single payout.
    """
    if (payment.reference_type or "").strip().lower() not in _ORDER_REFERENCE_TYPES:
        raise ValidationError(
            f"Escrow release is not supported for reference_type "
            f"'{payment.reference_type}'."
        )

    from krishisetu.domains.marketplace import repository as marketplace_repo

    order = await marketplace_repo.get_order_by_id(
        db, payment.reference_id, include_items=True
    )
    if not order:
        raise NotFoundError("Order", str(payment.reference_id))

    supplier_ids = {
        item["supplier_id"] for item in order.get("items", []) if item.get("supplier_id")
    }
    if not supplier_ids:
        raise ValidationError("Order has no supplier to release escrow to")
    if len(supplier_ids) > 1:
        raise ValidationError(
            "Order spans multiple suppliers; escrow cannot be released as a "
            "single payout."
        )

    supplier = await marketplace_repo.get_supplier_by_id(db, supplier_ids.pop())
    if not supplier:
        raise NotFoundError("Supplier", str(payment.reference_id))

    return supplier.user_id


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

    if payment.user_id != user_id:
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
    # Razorpay names the event type "event" in the payload; the route only
    # injects "event_id". Reading just "event_type" left this always empty,
    # so every branch below was unreachable.
    event_type = event_data.get("event_type") or event_data.get("event", "")

    # Process event
    payment_entity = event_data.get("payload", {}).get("payment", {}).get("entity", {})

    # Fall back to a deterministic id keyed on the payment, so a retry without
    # the X-Razorpay-Event-Id header still dedupes against its own event
    # rather than every id-less webhook collapsing onto one empty key.
    event_id = event_data.get("event_id") or ""
    if not event_id and payment_entity.get("id"):
        event_id = f"{event_type}:{payment_entity['id']}"

    # Check idempotency
    if event_id and await repo.webhook_exists(db, "razorpay", event_id):
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

    if event_type == "payment.captured":
        result = await _reconcile_captured_webhook(db, webhook.id, payment_entity)
        await repo.mark_webhook_processed(db, webhook.id)
        return {
            "status": "processed",
            "event_id": event_id,
            "event_type": event_type,
            **result,
        }

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


async def _reconcile_captured_webhook(
    db: AsyncSession,
    webhook_id: UUID,
    payment_entity: dict[str, Any],
) -> dict[str, Any]:
    """Reconcile a signature-verified `payment.captured` event.

    This is the only thing that settles a payment whose in-page callback never
    fired — the UPI deep-link flow (the user leaves the page entirely), a
    browser crash mid-checkout, or a closed tab. Without it those payments are
    captured at Razorpay and left pending forever.

    Amount is checked against the server-derived expected amount before the
    payment is marked captured; a mismatch refuses and logs loudly.
    """
    provider_order_id = payment_entity.get("order_id")
    provider_payment_id = payment_entity.get("id")
    amount_paise = payment_entity.get("amount", 0)

    payment = None
    if provider_order_id:
        payment = await repo.get_payment_by_provider_order_id(db, provider_order_id)
    if payment is None and provider_payment_id:
        payment = await repo.get_payment_by_provider_payment_id(
            db, provider_payment_id
        )

    if payment is None:
        logger.warning(
            "payment.webhook.payment_not_found",
            provider_order_id=provider_order_id,
            provider_payment_id=provider_payment_id,
        )
        return {"reconciled": False, "reason": "payment_not_found"}

    await repo.link_webhook_payment(db, webhook_id, payment.id)

    # Amount check — same source of truth as payment creation.
    try:
        expected = await _expected_amount_for_reference(
            db,
            payment.user_id,
            PaymentType(payment.payment_type),
            payment.reference_id,
            payment.reference_type,
        )
    except (ValidationError, ValueError) as e:
        logger.error(
            "payment.webhook.expected_amount_unresolvable",
            payment_id=str(payment.id),
            payment_type=payment.payment_type,
            error=str(e),
        )
        return {"reconciled": False, "reason": "expected_amount_unresolvable"}

    captured_amount = Decimal(str(amount_paise)) / Decimal(RUPEE_TO_PAISE)
    if captured_amount != expected or expected != payment.amount:
        logger.error(
            "payment.webhook.amount_mismatch",
            payment_id=str(payment.id),
            captured_amount=str(captured_amount),
            expected_amount=str(expected),
            recorded_amount=str(payment.amount),
            provider_payment_id=provider_payment_id,
        )
        return {"reconciled": False, "reason": "amount_mismatch"}

    if not provider_payment_id:
        logger.error(
            "payment.webhook.missing_payment_id", payment_id=str(payment.id)
        )
        return {"reconciled": False, "reason": "missing_provider_payment_id"}

    updated = await _capture_payment(
        db,
        payment,
        provider_payment_id=provider_payment_id,
        # Webhooks are authenticated by the webhook HMAC, not a checkout
        # signature; the route verified it before we got here.
        provider_signature=None,
        payment_method=payment_entity.get("method"),
        upi_id=payment_entity.get("vpa"),
        raw_response=payment_entity,
        source="webhook",
    )

    return {
        "reconciled": True,
        "payment_id": str(payment.id),
        "payment_status": updated.status if updated else None,
    }


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
