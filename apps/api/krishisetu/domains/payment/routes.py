"""Payment routes.

Endpoints:
- POST /payments                 — Create payment (get Razorpay checkout)
- POST /payments/{id}/verify     — Verify payment (from Razorpay callback)
- GET  /payments                 — List own payments
- GET  /payments/{id}            — Get payment details
- POST /payments/{id}/refund     — Process refund
- POST /payments/webhook         — Razorpay webhook handler
- POST /payments/{id}/release    — Release escrow (admin/supplier only)
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Header, Path, Query, Request, status
from pydantic import BaseModel

from krishisetu.core.dependencies import CurrentUser, DBSession, require_permissions
from krishisetu.core.logging import get_logger
from krishisetu.domains.identity.permissions import (
    PERM_MARKETPLACE_ORDER,
    PERM_INSURANCE_APPLY,
    PERM_MARKETPLACE_READ_OWN_ORDERS,
)
from krishisetu.domains.payment import services
from krishisetu.domains.payment.models import PaymentStatus
from krishisetu.domains.payment.schemas import (
    CreatePaymentRequest,
    CreatePaymentResponse,
    PaymentResponse,
    RefundRequest,
    VerifyPaymentRequest,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])


@router.post(
    "",
    response_model=CreatePaymentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_payment(
    payload: CreatePaymentRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> CreatePaymentResponse:
    """Create a new payment and get Razorpay checkout details.

    For marketplace orders: is_escrow=True (held until delivery)
    For insurance premiums: is_escrow=False (released immediately on capture)

    Returns:
    - Razorpay order ID
    - Razorpay public key (for frontend checkout SDK)
    - UPI intent URL (for direct UPI apps)
    - Checkout options (for Razorpay checkout modal)
    """
    return await services.create_payment(db, current_user.id, payload)


@router.post(
    "/{payment_id}/verify",
    response_model=PaymentResponse,
)
async def verify_payment(
    payment_id: Annotated[UUID, Path()],
    payload: VerifyPaymentRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> PaymentResponse:
    """Verify a completed payment from Razorpay callback.

    Called by the frontend after Razorpay checkout completes. Verifies the
    payment signature and updates the payment status.

    For non-escrow payments (insurance premium), the payment is released
    immediately on verification.
    """
    # Ensure the payment_id in path matches the one in payload
    if str(payment_id) != str(payload.payment_id):
        from krishisetu.core.exceptions import ValidationError
        raise ValidationError("Payment ID mismatch between path and body")

    return await services.verify_payment(db, current_user.id, payload)


@router.post(
    "/{payment_id}/refund",
    response_model=PaymentResponse,
)
async def refund_payment(
    payment_id: Annotated[UUID, Path()],
    payload: RefundRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> PaymentResponse:
    """Process a refund for a payment.

    Full or partial refund. Only payments in 'captured' or 'released' state
    can be refunded.
    """
    if str(payment_id) != str(payload.payment_id):
        from krishisetu.core.exceptions import ValidationError
        raise ValidationError("Payment ID mismatch between path and body")

    return await services.process_refund(db, current_user.id, payload)


@router.post(
    "/{payment_id}/release",
    response_model=PaymentResponse,
    dependencies=[Depends(require_permissions(PERM_MARKETPLACE_ORDER))],
)
async def release_escrow(
    payment_id: Annotated[UUID, Path()],
    current_user: CurrentUser,
    db: DBSession,
    payload: BaseModel = Body(...),
) -> PaymentResponse:
    """Release escrowed payment to supplier.

    Called when:
    - Marketplace order delivered → release to supplier
    - Insurance claim approved → release payout to farmer

    Body: {"released_to_user_id": "uuid"}
    """
    released_to = payload.dict().get("released_to_user_id")
    if not released_to:
        from krishisetu.core.exceptions import ValidationError
        raise ValidationError("released_to_user_id is required")

    return await services.release_escrow(
        db, payment_id, UUID(str(released_to))
    )


@router.get(
    "",
)
async def list_my_payments(
    current_user: CurrentUser,
    db: DBSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: PaymentStatus | None = Query(
        default=None, alias="status", description="Filter by status"
    ),
):
    """List the current user's payments."""
    return await services.list_my_payments(
        db, current_user.id, status=status_filter, page=page, page_size=page_size
    )


@router.get(
    "/{payment_id}",
    response_model=PaymentResponse,
)
async def get_payment(
    payment_id: Annotated[UUID, Path()],
    current_user: CurrentUser,
    db: DBSession,
) -> PaymentResponse:
    """Get payment details."""
    return await services.get_payment(db, payment_id, current_user.id)


# ---------------------------------------------------------------------------
# Webhook (no auth — called by Razorpay)
# ---------------------------------------------------------------------------


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def razorpay_webhook(
    request: Request,
    db: DBSession,
    x_razorpay_signature: str | None = Header(default=None),
    x_razorpay_event_id: str | None = Header(default=None),
):
    """Razorpay webhook handler.

    Receives payment events from Razorpay:
    - payment.captured
    - payment.failed
    - refund.processed

    Verifies the webhook signature and processes the event.
    Returns 200 immediately (Razorpay requires fast response).
    """
    body = await request.body()
    body_str = body.decode("utf-8")

    # Parse event data
    import json
    try:
        event_data = json.loads(body_str)
    except json.JSONDecodeError:
        logger.error("payment.webhook.invalid_json")
        return {"status": "error", "message": "Invalid JSON"}

    event_data["event_id"] = x_razorpay_event_id or event_data.get("id", "")

    # Verify signature
    from krishisetu.integrations.razorpay import get_razorpay_client

    razorpay = get_razorpay_client()
    signature = x_razorpay_signature or ""

    if not razorpay.verify_webhook_signature(body_str, signature):
        logger.warning(
            "payment.webhook.signature_invalid",
            event_id=event_data.get("event_id"),
        )
        return {"status": "error", "message": "Invalid signature"}

    # Process webhook
    try:
        result = await services.handle_webhook(
            db, body_str, signature, event_data
        )
        return result
    except Exception as e:
        logger.error("payment.webhook.processing_error", error=str(e))
        return {"status": "error", "message": str(e)}
