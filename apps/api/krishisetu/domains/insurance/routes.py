"""Insurance routes.

Endpoints:
Public (no auth):
- GET /insurance/products                — List insurance products
- GET /insurance/products/{id}           — Get product detail

Farmer-facing (require auth + ownership):
- GET  /insurance/products/for-plot/{id} — Find products available for a plot
- GET  /insurance/products/{id}/estimate — Estimate premium for a plot
- POST /insurance/policies               — Enroll in a policy
- GET  /insurance/policies               — List own policies
- GET  /insurance/policies/{id}          — Get policy detail
- POST /insurance/policies/{id}/pay      — Mark premium as paid (stub)
- POST /insurance/claims                 — Create a claim (draft)
- GET  /insurance/claims                 — List own claims
- GET  /insurance/claims/{id}            — Get claim detail
- PATCH /insurance/claims/{id}           — Update draft claim
- POST /insurance/claims/{id}/submit     — Submit claim for review
- POST /insurance/claims/{id}/withdraw   — Withdraw a claim
- GET  /insurance/stats                  — Summary stats

Insurer:
- GET  /insurer/claims                   — List claims for review
- PATCH /insurer/claims/{id}/review      — Review a claim
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, status

from krishisetu.core.dependencies import CurrentUser, DBSession, require_permissions
from krishisetu.core.logging import get_logger
from krishisetu.domains.identity.permissions import (
    PERM_INSURANCE_APPLY,
    PERM_INSURANCE_CLAIM_FILE,
    PERM_INSURANCE_CLAIM_REVIEW,
    PERM_INSURANCE_READ_OWN,
)
from krishisetu.domains.insurance import services
from krishisetu.domains.insurance.models import ClaimStatus, PolicyStatus
from krishisetu.domains.insurance.schemas import (
    ClaimCreateRequest,
    ClaimListResponse,
    ClaimResponse,
    ClaimSubmitRequest,
    ClaimUpdateRequest,
    InsurerClaimListResponse,
    InsurerReviewRequest,
    InsuranceProductListResponse,
    InsuranceProductPremiumEstimate,
    InsuranceStatsResponse,
    PolicyCreateRequest,
    PolicyListResponse,
    PolicyPremiumPaymentRequest,
    PolicyResponse,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Public product routes
# ---------------------------------------------------------------------------

products_router = APIRouter(prefix="/insurance/products", tags=["insurance"])


@products_router.get("", response_model=InsuranceProductListResponse)
async def list_products(
    db: DBSession,
    state: str | None = Query(default=None, description="Filter by state"),
    crop: str | None = Query(default=None, description="Filter by crop slug"),
    season: str | None = Query(default=None, description="Filter by season (kharif, rabi, zaid)"),
    season_year: int | None = Query(default=None, description="Filter by season year"),
    product_type: str | None = Query(default=None, description="Filter by type (pmfby, rwbcis, etc.)"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> InsuranceProductListResponse:
    """List available insurance products (public — no auth required)."""
    return await services.list_products(
        db,
        state=state,
        crop_slug=crop,
        season=season,
        season_year=season_year,
        product_type=product_type,
        page=page,
        page_size=page_size,
    )


@products_router.get(
    "/for-plot/{plot_id}",
    response_model=InsuranceProductListResponse,
    dependencies=[Depends(require_permissions(PERM_INSURANCE_READ_OWN))],
)
async def get_products_for_plot(
    plot_id: Annotated[UUID, Path()],
    current_user: CurrentUser,
    db: DBSession,
    crop: str | None = Query(default=None, description="Filter by crop slug"),
) -> InsuranceProductListResponse:
    """Find insurance products available for a specific plot.

    Filters by the plot's state. If the plot is in Maharashtra, only
    Maharashtra products are returned.
    """
    return await services.get_products_for_plot(
        db, plot_id, current_user.id, crop_slug=crop
    )


@products_router.get(
    "/{product_id}/estimate",
    response_model=InsuranceProductPremiumEstimate,
    dependencies=[Depends(require_permissions(PERM_INSURANCE_APPLY))],
)
async def estimate_premium(
    product_id: Annotated[UUID, Path()],
    current_user: CurrentUser,
    db: DBSession,
    plot_id: UUID = Query(..., description="Plot ID to estimate for"),
) -> InsuranceProductPremiumEstimate:
    """Estimate premium for a plot+product combination.

    Returns:
    - sum_insured: Total coverage amount (sum_insured_per_ha × area)
    - premium_amount: Premium the farmer must pay
    - premium_rate: Rate applied (e.g., 0.02 for 2%)
    """
    return await services.estimate_premium(
        db, product_id, plot_id, current_user.id
    )


# ---------------------------------------------------------------------------
# Farmer policy routes
# ---------------------------------------------------------------------------

policies_router = APIRouter(
    prefix="/insurance/policies",
    tags=["insurance"],
    dependencies=[Depends(require_permissions(PERM_INSURANCE_READ_OWN))],
)


@policies_router.post(
    "",
    response_model=PolicyResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions(PERM_INSURANCE_APPLY))],
)
async def enroll_policy(
    payload: PolicyCreateRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> PolicyResponse:
    """Enroll in an insurance policy.

    Creates a policy with status=pending. The farmer must then pay the
    premium via POST /insurance/policies/{id}/pay to activate the policy.

    The sum insured is computed as: sum_insured_per_ha × plot_area
    The premium is computed as: sum_insured × farmer_premium_rate

    Bank account details can be provided now or at claim filing time.
    """
    return await services.enroll_policy(db, current_user.id, payload)


@policies_router.get("", response_model=PolicyListResponse)
async def list_my_policies(
    current_user: CurrentUser,
    db: DBSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: PolicyStatus | None = Query(
        default=None, alias="status", description="Filter by status"
    ),
) -> PolicyListResponse:
    """List the farmer's insurance policies."""
    return await services.list_my_policies(
        db, current_user.id, status=status_filter, page=page, page_size=page_size
    )


@policies_router.get("/stats", response_model=InsuranceStatsResponse)
async def get_insurance_stats(
    current_user: CurrentUser,
    db: DBSession,
) -> InsuranceStatsResponse:
    """Get summary stats for the farmer's insurance (policies + claims)."""
    return await services.get_insurance_stats(db, current_user.id)


@policies_router.get("/{policy_id}", response_model=PolicyResponse)
async def get_policy(
    policy_id: Annotated[UUID, Path()],
    current_user: CurrentUser,
    db: DBSession,
) -> PolicyResponse:
    """Get a policy by ID with product info."""
    return await services.get_policy(db, policy_id, current_user.id)


@policies_router.post(
    "/{policy_id}/pay",
    response_model=PolicyResponse,
    dependencies=[Depends(require_permissions(PERM_INSURANCE_APPLY))],
)
async def pay_premium(
    policy_id: Annotated[UUID, Path()],
    payload: PolicyPremiumPaymentRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> PolicyResponse:
    """Mark premium as paid (stub for payment gateway integration).

    In production, this endpoint would:
    1. Verify the payment with the payment gateway (UPI/Razorpay)
    2. Capture the payment
    3. Update policy status to active

    For now, it accepts a payment_reference and activates the policy.
    """
    return await services.pay_premium(db, policy_id, current_user.id, payload)


# ---------------------------------------------------------------------------
# Farmer claim routes
# ---------------------------------------------------------------------------

claims_router = APIRouter(
    prefix="/insurance/claims",
    tags=["insurance"],
    dependencies=[Depends(require_permissions(PERM_INSURANCE_READ_OWN))],
)


@claims_router.post(
    "",
    response_model=ClaimResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions(PERM_INSURANCE_CLAIM_FILE))],
)
async def create_claim(
    payload: ClaimCreateRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> ClaimResponse:
    """Create a new insurance claim (draft).

    The claim is created with status=draft. The platform automatically
    attaches evidence from:
    - NDVI anomaly alerts on the insured plot (last 30 days)
    - Disease reports on the insured plot (last 30 days)
    - Weather alerts for the plot's district (last 30 days)

    The farmer can review the auto-attached evidence, add manual photo
    evidence, then submit via POST /insurance/claims/{id}/submit.

    The claimed_amount is computed as: sum_insured × (estimated_loss_pct / 100)
    """
    return await services.create_claim(db, current_user.id, payload)


@claims_router.get("", response_model=ClaimListResponse)
async def list_my_claims(
    current_user: CurrentUser,
    db: DBSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: ClaimStatus | None = Query(
        default=None, alias="status", description="Filter by status"
    ),
) -> ClaimListResponse:
    """List the farmer's insurance claims."""
    return await services.list_my_claims(
        db, current_user.id, status=status_filter, page=page, page_size=page_size
    )


@claims_router.get("/{claim_id}", response_model=ClaimResponse)
async def get_claim(
    claim_id: Annotated[UUID, Path()],
    current_user: CurrentUser,
    db: DBSession,
) -> ClaimResponse:
    """Get a claim by ID with evidence and policy info."""
    return await services.get_claim(db, claim_id, current_user.id)


@claims_router.patch(
    "/{claim_id}",
    response_model=ClaimResponse,
    dependencies=[Depends(require_permissions(PERM_INSURANCE_CLAIM_FILE))],
)
async def update_claim(
    claim_id: Annotated[UUID, Path()],
    payload: ClaimUpdateRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> ClaimResponse:
    """Update a draft claim.

    Only claims in 'draft' status can be edited. Once submitted, the claim
    cannot be modified (withdraw and refile if needed).
    """
    return await services.update_claim(db, claim_id, current_user.id, payload)


@claims_router.post(
    "/{claim_id}/submit",
    response_model=ClaimResponse,
    dependencies=[Depends(require_permissions(PERM_INSURANCE_CLAIM_FILE))],
)
async def submit_claim(
    claim_id: Annotated[UUID, Path()],
    payload: ClaimSubmitRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> ClaimResponse:
    """Submit a draft claim for insurer review.

    Compiles the auto-evidence summary and changes status to 'submitted'.
    Bank account details (for payout) are required at this stage.
    """
    return await services.submit_claim(db, claim_id, current_user.id, payload)


@claims_router.post(
    "/{claim_id}/withdraw",
    response_model=ClaimResponse,
    dependencies=[Depends(require_permissions(PERM_INSURANCE_CLAIM_FILE))],
)
async def withdraw_claim(
    claim_id: Annotated[UUID, Path()],
    current_user: CurrentUser,
    db: DBSession,
) -> ClaimResponse:
    """Withdraw a claim.

    Can only withdraw claims that are in draft/submitted/under_review/
    evidence_requested status. Approved/disbursed claims cannot be withdrawn.
    """
    return await services.withdraw_claim(db, claim_id, current_user.id)


# ---------------------------------------------------------------------------
# Insurer routes
# ---------------------------------------------------------------------------

insurer_router = APIRouter(
    prefix="/insurer/claims",
    tags=["insurer"],
    dependencies=[Depends(require_permissions(PERM_INSURANCE_CLAIM_REVIEW))],
)


@insurer_router.get("", response_model=InsurerClaimListResponse)
async def insurer_list_claims(
    current_user: CurrentUser,
    db: DBSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: ClaimStatus | None = Query(
        default=None, alias="status", description="Filter by status"
    ),
) -> InsurerClaimListResponse:
    """List claims for insurer review.

    Returns claims in submitted/under_review/evidence_requested status,
    ordered by submission date (oldest first).
    """
    return await services.insurer_list_claims(
        db, current_user, status=status_filter, page=page, page_size=page_size
    )


@insurer_router.patch(
    "/{claim_id}/review",
    response_model=ClaimResponse,
)
async def insurer_review_claim(
    claim_id: Annotated[UUID, Path()],
    payload: InsurerReviewRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> ClaimResponse:
    """Review a claim (approve, reject, or request more evidence).

    - approve: Sets approved_amount and status=approved. Payout processing
      happens separately (Phase 2 bank integration).
    - reject: Sets rejection_reason and status=rejected.
    - request_evidence: Sets evidence_request_notes and status=evidence_requested.
      The farmer will be notified to provide additional evidence.
    """
    return await services.insurer_review_claim(
        db, claim_id, current_user, payload
    )
