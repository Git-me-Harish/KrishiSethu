"""Payment routes.

Endpoints:
- POST /payments                 — Create payment (get Razorpay checkout)
- POST /payments/{id}/verify     — Verify payment (from Razorpay callback)
- GET  /payments                 — List own payments
- GET  /payments/{id}            — Get payment details
- POST /payments/{id}/refund     — Process refund
- POST /payments/webhook         — Razorpay webhook handler
- POST /payments/{id}/release    — Release escrow (admin/supplier only)

FIX (T3): release_escrow was previously gated by PERM_MARKETPLACE_ORDER —
a farmer permission — meaning any farmer could release their own escrowed
payment to themselves (or any UUID) before delivery. It is now gated by
require_role(UserRole.ADMIN, UserRole.SUPPLIER) and the service layer
verifies that the released_to_user_id actually owns an item in the order
being released.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request, status
from pydantic import BaseModel, Field

from krishisetu.core.dependencies import CurrentUser, DBSession, require_role
from krishisetu.core.logging import get_logger
from krishisetu.domains.identity.models import UserRole
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



# Typed request bodies (replaces the old `payload: BaseModel = Body(...)`)
class ReleaseEscrowRequest(BaseModel):
    """Request body for POST /payments/{id}/release.

    FIX (T3): the old route used `payload: BaseModel = Body(...)` which
    accepted any shape and required `.dict().get("released_to_user_id")`
    to extract the value — no validation, no OpenAPI schema. This typed
    body gives proper validation, error messages, and OpenAPI docs.
    """

    released_to_user_id: UUID = Field(
        ...,
        description=(
            "UUID of the user to release the escrow to (the supplier who "
            "fulfilled the order, or the farmer for an insurance payout). "
            "The service layer verifies this user actually owns an item in "
            "the order — a farmer cannot release escrow to themselves."
        ),
    )


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
    dependencies=[Depends(require_role(UserRole.ADMIN, UserRole.SUPPLIER))],
)
async def release_escrow(
    payment_id: Annotated[UUID, Path()],
    payload: ReleaseEscrowRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> PaymentResponse:
    """Release escrowed payment to supplier or farmer.

    Authorization: ADMIN or SUPPLIER role only.
    - SUPPLIER releases escrow to themselves after fulfilling an order.
      The service verifies the released_to_user_id matches the supplier's
      own user_id AND that the supplier owns an item in the order.
    - ADMIN can release escrow to any legitimate recipient (the service
      still verifies the recipient owns an item in the order).

    Body: {"released_to_user_id": "uuid"}

    Called when:
    - Marketplace order delivered → release to supplier
    - Insurance claim approved → release payout to farmer
    """
    return await services.release_escrow(
        db,
        payment_id,
        payload.released_to_user_id,
        released_by=current_user,
    )


@router.get(
    "",
    response_model=list[PaymentResponse] | dict,
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


# Webhook (no auth — called by Razorpay)
@router.post("/webhook", status_code=status.HTTP_200_OK)
async def razorpay_webhook(
    request: Request,
    db: DBSession,
    x_razorpay_signature: str | None = None,
    x_razorpay_event_id: str | None = None,
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
