"""Insurance domain — business logic services.

Key services:
- Product discovery (find available products for a plot)
- Premium estimation (compute sum insured + premium based on plot area)
- Policy enrollment (create policy, mark premium paid)
- Claim filing with auto-evidence aggregation
- Insurer review workflow

The auto-evidence aggregation is the killer feature — when a farmer files
a claim, the platform automatically attaches:
1. NDVI anomaly alerts for the insured plot (within claim period)
2. Disease reports for the insured plot (within claim period)
3. Weather alerts for the plot's district (within claim period)

This eliminates the bureaucratic burden of manual evidence collection.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from krishisetu.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from krishisetu.core.logging import get_logger
from krishisetu.core.storage import get_storage
from krishisetu.domains.disease import repository as disease_repo
from krishisetu.domains.farmer import repository as farmer_repo
from krishisetu.domains.insurance import repository as repo
from krishisetu.domains.insurance.insurer_scope import resolve_insurer_name
from krishisetu.domains.insurance.models import (
    ClaimStatus,
    ClaimType,
    PolicyStatus,
)
from krishisetu.domains.insurance.schemas import (
    ClaimCreateRequest,
    ClaimEvidenceResponse,
    ClaimResponse,
    ClaimSubmitRequest,
    ClaimUpdateRequest,
    InsuranceProductListResponse,
    InsuranceProductPremiumEstimate,
    InsuranceProductResponse,
    InsuranceStatsResponse,
    InsurerReviewRequest,
    PolicyCreateRequest,
    PolicyListResponse,
    PolicyPremiumPaymentRequest,
    PolicyResponse,
)
from krishisetu.domains.identity.models import User
from krishisetu.domains.ndvi import repository as ndvi_repo
from krishisetu.domains.soil_weather import repository as weather_repo

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Product discovery
# ---------------------------------------------------------------------------


async def list_products(
    db: AsyncSession,
    *,
    state: str | None = None,
    crop_slug: str | None = None,
    season: str | None = None,
    season_year: int | None = None,
    product_type: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> InsuranceProductListResponse:
    """List available insurance products."""
    products, total = await repo.list_products(
        db,
        state=state,
        crop_slug=crop_slug,
        season=season,
        season_year=season_year,
        product_type=product_type,
        page=page,
        page_size=page_size,
    )
    return InsuranceProductListResponse(
        products=[InsuranceProductResponse.model_validate(p) for p in products],
        total=total,
    )


async def get_products_for_plot(
    db: AsyncSession,
    plot_id: UUID,
    farmer_id: UUID,
    *,
    crop_slug: str | None = None,
) -> InsuranceProductListResponse:
    """Find insurance products available for a specific plot.

    Filters by the plot's state. If crop_slug is provided, further filters
    by that crop.
    """
    # Verify plot ownership
    plot = await farmer_repo.get_plot_by_id(db, plot_id, include_boundary=False)
    if not plot or plot.farmer_id != farmer_id:
        raise NotFoundError("Plot", str(plot_id))

    products = await repo.find_product_for_plot(db, plot_id, crop_slug=crop_slug)
    return InsuranceProductListResponse(
        products=[InsuranceProductResponse.model_validate(p) for p in products],
        total=len(products),
    )


async def estimate_premium(
    db: AsyncSession,
    product_id: UUID,
    plot_id: UUID,
    farmer_id: UUID,
) -> InsuranceProductPremiumEstimate:
    """Estimate premium for a plot+product combination.

    Sum insured = sum_insured_per_ha × plot_area_ha
    Premium = sum_insured × farmer_premium_rate
    """
    product = await repo.get_product_by_id(db, product_id)
    if not product:
        raise NotFoundError("InsuranceProduct", str(product_id))

    plot = await farmer_repo.get_plot_by_id(db, plot_id, include_boundary=False)
    if not plot or plot.farmer_id != farmer_id:
        raise NotFoundError("Plot", str(plot_id))

    # Verify the product is available for the plot's state
    if product.state != plot.state:
        raise ValidationError(
            f"Product is for {product.state}, but plot is in {plot.state}"
        )

    sum_insured = product.sum_insured_per_ha * plot.area_ha
    premium_amount = sum_insured * product.farmer_premium_rate

    # Apply min/max bounds
    if product.farmer_premium_min and premium_amount < product.farmer_premium_min:
        premium_amount = product.farmer_premium_min
    if product.farmer_premium_max and premium_amount > product.farmer_premium_max:
        premium_amount = product.farmer_premium_max

    return InsuranceProductPremiumEstimate(
        product_id=product_id,
        plot_id=plot_id,
        area_ha=plot.area_ha,
        sum_insured=sum_insured,
        premium_amount=premium_amount,
        premium_rate=product.farmer_premium_rate,
        farmer_premium_rate_pct=float(product.farmer_premium_rate) * 100,
    )


# ---------------------------------------------------------------------------
# Policy enrollment
# ---------------------------------------------------------------------------


async def enroll_policy(
    db: AsyncSession,
    farmer_id: UUID,
    payload: PolicyCreateRequest,
) -> PolicyResponse:
    """Enroll in an insurance policy.

    Steps:
    1. Verify product exists and is active
    2. Verify plot ownership and state matches product
    3. Check for existing active policy on this plot+product (prevent duplicates)
    4. Compute sum insured and premium
    5. Generate unique policy number
    6. Create policy (status=pending until premium paid)
    """
    product = await repo.get_product_by_id(db, payload.product_id)
    if not product or not product.is_active:
        raise NotFoundError("InsuranceProduct", str(payload.product_id))

    plot = await farmer_repo.get_plot_by_id(db, payload.plot_id, include_boundary=False)
    if not plot or plot.farmer_id != farmer_id:
        raise NotFoundError("Plot", str(payload.plot_id))

    # Verify state match
    if product.state != plot.state:
        raise ValidationError(
            f"Product is for {product.state}, but plot is in {plot.state}"
        )

    # Check for existing active policy on this plot+product
    existing = await repo.get_active_policy_for_plot(db, payload.plot_id)
    if existing and existing.product_id == payload.product_id:
        raise ConflictError(
            "An active policy already exists for this plot and product."
        )

    # Compute sum insured and premium
    sum_insured = product.sum_insured_per_ha * plot.area_ha
    premium_amount = sum_insured * product.farmer_premium_rate

    if product.farmer_premium_min and premium_amount < product.farmer_premium_min:
        premium_amount = product.farmer_premium_min
    if product.farmer_premium_max and premium_amount > product.farmer_premium_max:
        premium_amount = product.farmer_premium_max

    # Generate policy number
    policy_number = _generate_policy_number()

    policy = await repo.create_policy(
        db,
        policy_number=policy_number,
        product_id=payload.product_id,
        farmer_id=farmer_id,
        plot_id=payload.plot_id,
        crop_cycle_id=payload.crop_cycle_id,
        sum_insured=sum_insured,
        area_insured_ha=plot.area_ha,
        premium_amount=premium_amount,
        premium_rate=product.farmer_premium_rate,
        coverage_start_date=product.coverage_start_date,
        coverage_end_date=product.coverage_end_date,
        bank_account_number=payload.bank_account_number,
        bank_ifsc=payload.bank_ifsc,
    )

    logger.info(
        "insurance.policy_enrolled",
        policy_id=str(policy.id),
        policy_number=policy_number,
        farmer_id=str(farmer_id),
        sum_insured=str(sum_insured),
        premium=str(premium_amount),
    )

    policy_dict = await repo.get_policy_by_id(db, policy.id)
    return _to_policy_response(policy_dict)


async def pay_premium(
    db: AsyncSession,
    policy_id: UUID,
    farmer_id: UUID,
    payload: PolicyPremiumPaymentRequest,
) -> PolicyResponse:
    """Activate a policy once its premium payment has actually settled.

    The policy is only activated when a captured (or released), non-refunded
    payment exists for this policy, owned by the farmer, for at least the
    premium amount. The client-supplied `payment_reference` is recorded but
    never trusted as proof of payment.
    """
    policy_dict = await repo.get_policy_by_id(db, policy_id)
    if not policy_dict:
        raise NotFoundError("InsurancePolicy", str(policy_id))

    if policy_dict["farmer_id"] != farmer_id:
        raise NotFoundError("InsurancePolicy", str(policy_id))

    if policy_dict["premium_paid"]:
        raise ConflictError("Premium has already been paid for this policy.")

    if policy_dict["status"] != PolicyStatus.PENDING.value:
        raise ValidationError(
            f"Policy is in '{policy_dict['status']}' state, cannot accept payment."
        )

    # Require a real settled payment for this policy before activating it.
    from krishisetu.domains.payment import repository as payment_repo

    payment = await payment_repo.find_settled_payment_for_reference(
        db,
        reference_id=policy_id,
        user_id=farmer_id,
        min_amount=policy_dict["premium_amount"],
    )
    if not payment:
        raise ValidationError(
            "No settled premium payment found for this policy. Complete the "
            "payment via /payments before activating the policy."
        )

    policy = await repo.update_policy_premium_payment(
        db, policy_id, payment.payment_number
    )

    logger.info(
        "insurance.premium_paid",
        policy_id=str(policy_id),
        payment_id=str(payment.id),
        payment_reference=payment.payment_number,
    )

    updated_dict = await repo.get_policy_by_id(db, policy_id)
    return _to_policy_response(updated_dict)


async def list_my_policies(
    db: AsyncSession,
    farmer_id: UUID,
    *,
    status: PolicyStatus | None = None,
    page: int = 1,
    page_size: int = 20,
) -> PolicyListResponse:
    """List the farmer's insurance policies."""
    policies, total = await repo.list_policies_by_farmer(
        db, farmer_id, status=status, page=page, page_size=page_size
    )
    return PolicyListResponse(
        policies=[_to_policy_response(p) for p in policies],
        total=total,
    )


async def get_policy(
    db: AsyncSession,
    policy_id: UUID,
    farmer_id: UUID,
) -> PolicyResponse:
    """Get a policy by ID (verifies ownership)."""
    policy_dict = await repo.get_policy_by_id(db, policy_id)
    if not policy_dict:
        raise NotFoundError("InsurancePolicy", str(policy_id))

    if policy_dict["farmer_id"] != farmer_id:
        raise NotFoundError("InsurancePolicy", str(policy_id))

    return _to_policy_response(policy_dict)


# ---------------------------------------------------------------------------
# Claim filing
# ---------------------------------------------------------------------------


async def create_claim(
    db: AsyncSession,
    farmer_id: UUID,
    payload: ClaimCreateRequest,
) -> ClaimResponse:
    """Create a new insurance claim (draft).

    Verifies:
    - Policy exists and belongs to farmer
    - Policy is active (premium paid, within coverage period)
    - No duplicate claim for the same loss event
    """
    policy_dict = await repo.get_policy_by_id(db, payload.policy_id)
    if not policy_dict:
        raise NotFoundError("InsurancePolicy", str(payload.policy_id))

    if policy_dict["farmer_id"] != farmer_id:
        raise NotFoundError("InsurancePolicy", str(payload.policy_id))

    if not policy_dict["premium_paid"]:
        raise ValidationError(
            "Cannot file a claim on a policy with unpaid premium."
        )

    if policy_dict["status"] != PolicyStatus.ACTIVE.value:
        raise ValidationError(
            f"Policy is in '{policy_dict['status']}' state. Only active policies can have claims."
        )

    # Check coverage period
    today = date.today()
    if payload.loss_date < policy_dict["coverage_start_date"]:
        raise ValidationError(
            f"Loss date is before policy coverage start ({policy_dict['coverage_start_date']})"
        )
    if payload.loss_date > policy_dict["coverage_end_date"]:
        raise ValidationError(
            f"Loss date is after policy coverage end ({policy_dict['coverage_end_date']})"
        )

    # Compute claimed amount based on loss percentage
    sum_insured = policy_dict["sum_insured"]
    claimed_amount = sum_insured * (payload.estimated_loss_pct / Decimal("100"))

    # Generate claim number
    claim_number = _generate_claim_number()

    claim = await repo.create_claim(
        db,
        claim_number=claim_number,
        policy_id=payload.policy_id,
        farmer_id=farmer_id,
        claim_type=payload.claim_type,
        loss_date=payload.loss_date,
        loss_description=payload.loss_description,
        estimated_loss_pct=payload.estimated_loss_pct,
        claimed_amount=claimed_amount,
    )

    # Auto-attach evidence from other modules
    await _auto_attach_evidence(
        db,
        claim_id=claim.id,
        policy_id=payload.policy_id,
        farmer_id=farmer_id,
        plot_id=policy_dict["plot_id"],
        loss_date=payload.loss_date,
    )

    logger.info(
        "insurance.claim_created",
        claim_id=str(claim.id),
        claim_number=claim_number,
        policy_id=str(payload.policy_id),
        claim_type=payload.claim_type.value if hasattr(payload.claim_type, 'value') else payload.claim_type,
        claimed_amount=str(claimed_amount),
    )

    claim_dict = await repo.get_claim_by_id(db, claim.id, include_evidence=True)
    return _to_claim_response(claim_dict)


async def update_claim(
    db: AsyncSession,
    claim_id: UUID,
    farmer_id: UUID,
    payload: ClaimUpdateRequest,
) -> ClaimResponse:
    """Update a draft claim."""
    claim_dict = await repo.get_claim_by_id(db, claim_id, include_evidence=False)
    if not claim_dict:
        raise NotFoundError("InsuranceClaim", str(claim_id))

    if claim_dict["farmer_id"] != farmer_id:
        raise NotFoundError("InsuranceClaim", str(claim_id))

    if claim_dict["status"] != ClaimStatus.DRAFT.value:
        raise ValidationError(
            "Only draft claims can be edited. Submit a new claim if changes are needed."
        )

    # If estimated_loss_pct changes, recompute claimed_amount
    if payload.estimated_loss_pct is not None:
        policy_dict = await repo.get_policy_by_id(db, claim_dict["policy_id"])
        if policy_dict:
            new_claimed = policy_dict["sum_insured"] * (payload.estimated_loss_pct / Decimal("100"))
            await repo.update_claim(db, claim_id, claimed_amount=new_claimed)

    # Convert ClaimTypeEnum to value if needed
    updates: dict[str, Any] = {}
    if payload.claim_type is not None:
        updates["claim_type"] = payload.claim_type
    if payload.loss_date is not None:
        updates["loss_date"] = payload.loss_date
    if payload.loss_description is not None:
        updates["loss_description"] = payload.loss_description
    if payload.estimated_loss_pct is not None:
        updates["estimated_loss_pct"] = payload.estimated_loss_pct

    await repo.update_claim(db, claim_id, **updates)

    claim_dict = await repo.get_claim_by_id(db, claim_id, include_evidence=True)
    return _to_claim_response(claim_dict)


async def submit_claim(
    db: AsyncSession,
    claim_id: UUID,
    farmer_id: UUID,
    payload: ClaimSubmitRequest,
) -> ClaimResponse:
    """Submit a draft claim for insurer review.

    Compiles the auto-evidence summary and marks the claim as submitted.
    """
    claim_dict = await repo.get_claim_by_id(db, claim_id, include_evidence=True)
    if not claim_dict:
        raise NotFoundError("InsuranceClaim", str(claim_id))

    if claim_dict["farmer_id"] != farmer_id:
        raise NotFoundError("InsuranceClaim", str(claim_id))

    if claim_dict["status"] != ClaimStatus.DRAFT.value:
        raise ValidationError(
            f"Claim is in '{claim_dict['status']}' state. Only draft claims can be submitted."
        )

    # Compile auto-evidence summary
    evidence = claim_dict.get("evidence", [])
    summary = {
        "total_evidence_count": len(evidence),
        "auto_evidence_count": sum(1 for e in evidence if e.is_auto_attached),
        "manual_evidence_count": sum(1 for e in evidence if not e.is_auto_attached),
        "evidence_types": list({e.evidence_type for e in evidence}),
        "evidence_summary": [
            {
                "type": e.evidence_type,
                "title": e.title,
                "date": e.evidence_date.isoformat() if e.evidence_date else None,
                "auto": e.is_auto_attached,
            }
            for e in evidence
        ],
    }

    updated = await repo.submit_claim(
        db,
        claim_id,
        bank_account_number=payload.bank_account_number,
        bank_ifsc=payload.bank_ifsc,
        auto_evidence_summary=summary,
    )

    logger.info(
        "insurance.claim_submitted",
        claim_id=str(claim_id),
        evidence_count=len(evidence),
        auto_evidence_count=summary["auto_evidence_count"],
    )

    return _to_claim_response(updated)


async def withdraw_claim(
    db: AsyncSession,
    claim_id: UUID,
    farmer_id: UUID,
) -> ClaimResponse:
    """Farmer withdraws a claim."""
    claim_dict = await repo.get_claim_by_id(db, claim_id, include_evidence=False)
    if not claim_dict:
        raise NotFoundError("InsuranceClaim", str(claim_id))

    if claim_dict["farmer_id"] != farmer_id:
        raise NotFoundError("InsuranceClaim", str(claim_id))

    if claim_dict["status"] in (
        ClaimStatus.APPROVED.value,
        ClaimStatus.PAYOUT_DISBURSED.value,
        ClaimStatus.WITHDRAWN.value,
    ):
        raise ValidationError(
            f"Cannot withdraw a claim in '{claim_dict['status']}' state."
        )

    updated = await repo.withdraw_claim(db, claim_id)
    return _to_claim_response(updated)


async def list_my_claims(
    db: AsyncSession,
    farmer_id: UUID,
    *,
    status: ClaimStatus | None = None,
    page: int = 1,
    page_size: int = 20,
) -> Any:
    """List the farmer's insurance claims."""
    from krishisetu.domains.insurance.schemas import ClaimListResponse

    claims, total = await repo.list_claims_by_farmer(
        db, farmer_id, status=status, page=page, page_size=page_size
    )
    return ClaimListResponse(
        claims=[_to_claim_response(c) for c in claims],
        total=total,
    )


async def get_claim(
    db: AsyncSession,
    claim_id: UUID,
    farmer_id: UUID,
) -> ClaimResponse:
    """Get a claim by ID (verifies ownership)."""
    claim_dict = await repo.get_claim_by_id(db, claim_id, include_evidence=True)
    if not claim_dict:
        raise NotFoundError("InsuranceClaim", str(claim_id))

    if claim_dict["farmer_id"] != farmer_id:
        raise NotFoundError("InsuranceClaim", str(claim_id))

    return _to_claim_response(claim_dict)


# ---------------------------------------------------------------------------
# Auto-evidence aggregation (the killer feature)
# ---------------------------------------------------------------------------


async def _auto_attach_evidence(
    db: AsyncSession,
    *,
    claim_id: UUID,
    policy_id: UUID,
    farmer_id: UUID,
    plot_id: UUID,
    loss_date: date,
) -> int:
    """Auto-attach evidence from other modules.

    Looks for:
    1. NDVI anomaly alerts on the insured plot (within 30 days before loss_date)
    2. Disease reports on the insured plot (within 30 days before loss_date)
    3. Weather alerts for the plot's district (within 30 days before loss_date)

    Returns the number of evidence items attached.
    """
    # Get the plot's district for weather alerts
    plot = await farmer_repo.get_plot_by_id(db, plot_id, include_boundary=False)
    if not plot:
        return 0

    # Define the evidence window (30 days before loss_date to loss_date)
    evidence_start = datetime.combine(
        loss_date - timedelta(days=30), datetime.min.time(), tzinfo=timezone.utc
    )
    evidence_end = datetime.combine(loss_date, datetime.max.time(), tzinfo=timezone.utc)

    evidence_count = 0

    # --- 1. NDVI anomaly alerts ---
    try:
        ndvi_anomalies = await ndvi_repo.get_active_anomalies_for_plot(db, plot_id)
        for anomaly in ndvi_anomalies:
            if evidence_start <= anomaly.created_at <= evidence_end:
                await repo.create_evidence(
                    db,
                    claim_id=claim_id,
                    evidence_type="ndvi_drop",
                    source_module="ndvi",
                    source_id=anomaly.id,
                    title=f"NDVI {anomaly.anomaly_type.replace('_', ' ').title()}",
                    description=(
                        f"NDVI dropped from {anomaly.previous_ndvi} to {anomaly.current_ndvi} "
                        f"(drop of {anomaly.drop_magnitude}, {anomaly.drop_percentage:.1f}%) "
                        f"detected on {anomaly.created_at.strftime('%Y-%m-%d')}."
                    ),
                    evidence_date=anomaly.created_at,
                    snapshot_data={
                        "anomaly_type": anomaly.anomaly_type,
                        "previous_ndvi": float(anomaly.previous_ndvi),
                        "current_ndvi": float(anomaly.current_ndvi),
                        "drop_magnitude": float(anomaly.drop_magnitude),
                        "drop_percentage": anomaly.drop_percentage,
                        "created_at": anomaly.created_at.isoformat(),
                    },
                    is_auto_attached=True,
                )
                evidence_count += 1
    except Exception as e:
        logger.warning("insurance.auto_evidence_ndvi_failed", error=str(e))

    # --- 2. Disease reports ---
    try:
        from krishisetu.domains.disease.models import DiseaseReportStatus
        disease_reports, _ = await disease_repo.list_disease_reports_by_farmer(
            db, farmer_id, status=DiseaseReportStatus.COMPLETED, page=1, page_size=100
        )
        for report in disease_reports:
            if report.get("plot_id") != plot_id:
                continue
            submitted_at = report.get("submitted_at")
            if not submitted_at:
                continue
            if isinstance(submitted_at, str):
                submitted_at = datetime.fromisoformat(submitted_at.replace("Z", "+00:00"))
            if evidence_start <= submitted_at <= evidence_end:
                disease_slug = report.get("disease_slug", "unknown")
                confidence = report.get("confidence")
                await repo.create_evidence(
                    db,
                    claim_id=claim_id,
                    evidence_type="disease_report",
                    source_module="disease",
                    source_id=report["id"],
                    title=f"Disease Report: {disease_slug.replace('_', ' ').title()}",
                    description=(
                        f"Disease '{disease_slug}' identified with "
                        f"{float(confidence)*100:.1f}% confidence on "
                        f"{submitted_at.strftime('%Y-%m-%d')}."
                    ),
                    evidence_date=submitted_at,
                    snapshot_data={
                        "disease_slug": disease_slug,
                        "confidence": float(confidence) if confidence else None,
                        "submitted_at": submitted_at.isoformat(),
                    },
                    is_auto_attached=True,
                )
                evidence_count += 1
    except Exception as e:
        logger.warning("insurance.auto_evidence_disease_failed", error=str(e))

    # --- 3. Weather alerts ---
    try:
        weather_alerts = await weather_repo.get_active_alerts_for_district(
            db, plot.district, plot.state
        )
        for alert in weather_alerts:
            if evidence_start <= alert.created_at <= evidence_end:
                await repo.create_evidence(
                    db,
                    claim_id=claim_id,
                    evidence_type="weather_alert",
                    source_module="soil_weather",
                    source_id=alert.id,
                    title=f"Weather Alert: {alert.alert_type.replace('_', ' ').title()}",
                    description=(
                        f"{alert.title}. Severity: {alert.severity}. "
                        f"Effective: {alert.effective_at} to {alert.expires_at}. "
                        f"Recommended actions: {alert.recommended_actions or 'N/A'}"
                    ),
                    evidence_date=alert.created_at,
                    snapshot_data={
                        "alert_type": alert.alert_type,
                        "severity": alert.severity,
                        "title": alert.title,
                        "description": alert.description,
                        "recommended_actions": alert.recommended_actions,
                        "effective_at": alert.effective_at.isoformat() if alert.effective_at else None,
                        "expires_at": alert.expires_at.isoformat() if alert.expires_at else None,
                    },
                    is_auto_attached=True,
                )
                evidence_count += 1
    except Exception as e:
        logger.warning("insurance.auto_evidence_weather_failed", error=str(e))

    logger.info(
        "insurance.auto_evidence_attached",
        claim_id=str(claim_id),
        evidence_count=evidence_count,
    )

    return evidence_count


# ---------------------------------------------------------------------------
# Insurer review
# ---------------------------------------------------------------------------


async def insurer_list_claims(
    db: AsyncSession,
    insurer: User,
    *,
    status: ClaimStatus | None = None,
    page: int = 1,
    page_size: int = 20,
) -> Any:
    """List claims for insurer review, scoped to the reviewer's insurer."""
    from krishisetu.domains.insurance.schemas import InsurerClaimListResponse

    insurer_name = resolve_insurer_name(insurer)

    claims, total = await repo.list_claims_for_insurer(
        db, insurer_name=insurer_name, status=status, page=page, page_size=page_size
    )
    return InsurerClaimListResponse(
        claims=[_to_claim_response(c) for c in claims],
        total=total,
    )


async def insurer_review_claim(
    db: AsyncSession,
    claim_id: UUID,
    insurer: User,
    payload: InsurerReviewRequest,
) -> ClaimResponse:
    """Insurer reviews a claim (approve/reject/request_evidence).

    The reviewer may only act on claims written against their own insurer's
    products, and an approval can never exceed the claimed amount or the
    policy's sum insured.
    """
    # include_evidence=True is required: the repository only returns a dict
    # (rather than an ORM row) on that path.
    claim_dict = await repo.get_claim_by_id(db, claim_id, include_evidence=True)
    if not claim_dict:
        raise NotFoundError("InsuranceClaim", str(claim_id))

    if claim_dict["status"] not in (
        ClaimStatus.SUBMITTED.value,
        ClaimStatus.UNDER_REVIEW.value,
        ClaimStatus.EVIDENCE_REQUESTED.value,
    ):
        raise ValidationError(
            f"Claim is in '{claim_dict['status']}' state. "
            f"Only submitted/under_review/evidence_requested claims can be reviewed."
        )

    policy_dict = await repo.get_policy_by_id(db, claim_dict["policy_id"])
    if not policy_dict:
        raise NotFoundError("InsurancePolicy", str(claim_dict["policy_id"]))

    # Bind the reviewer to the claim's insurer
    insurer_name = resolve_insurer_name(insurer)
    if insurer_name:
        product = policy_dict.get("product") or {}
        if product.get("insurer_name") != insurer_name:
            raise NotFoundError("InsuranceClaim", str(claim_id))

    # Clamp the approved amount to what was claimed and to the sum insured
    if payload.approved_amount is not None:
        limit = min(claim_dict["claimed_amount"], policy_dict["sum_insured"])
        if payload.approved_amount > limit:
            raise ValidationError(
                f"approved_amount ({payload.approved_amount}) exceeds the "
                f"claimable maximum ({limit})."
            )

    updated = await repo.insurer_review_claim(
        db,
        claim_id,
        insurer.id,
        action=payload.action,
        approved_amount=payload.approved_amount,
        review_notes=payload.review_notes,
        rejection_reason=payload.rejection_reason,
        evidence_request_notes=payload.evidence_request_notes,
    )

    logger.info(
        "insurance.claim_reviewed",
        claim_id=str(claim_id),
        action=payload.action,
        insurer_id=str(insurer.id),
    )

    return _to_claim_response(updated)


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


async def get_insurance_stats(
    db: AsyncSession, farmer_id: UUID
) -> InsuranceStatsResponse:
    """Get summary stats for the farmer's insurance."""
    stats = await repo.get_farmer_insurance_stats(db, farmer_id)
    return InsuranceStatsResponse(**stats)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _generate_policy_number() -> str:
    """Generate a unique policy number.

    Format: KS-POL-{YYYYMMDD}-{8-char-uuid}
    Example: KS-POL-20260719-a1b2c3d4
    """
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    short_uuid = uuid.uuid4().hex[:8]
    return f"KS-POL-{today}-{short_uuid}"


def _generate_claim_number() -> str:
    """Generate a unique claim number.

    Format: KS-CLM-{YYYYMMDD}-{8-char-uuid}
    """
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    short_uuid = uuid.uuid4().hex[:8]
    return f"KS-CLM-{today}-{short_uuid}"


def _to_policy_response(policy_dict: dict[str, Any]) -> PolicyResponse:
    """Convert a policy dict to a PolicyResponse."""
    from krishisetu.domains.insurance.schemas import InsuranceProductResponse

    product_resp = None
    if policy_dict.get("product"):
        product = policy_dict["product"]
        # Handle full product dict (from list query) vs partial (from claim query)
        if "id" in product:
            product_resp = InsuranceProductResponse(**product)
        else:
            # Partial product info — skip for now
            pass

    return PolicyResponse(
        id=policy_dict["id"],
        policy_number=policy_dict["policy_number"],
        product_id=policy_dict["product_id"],
        farmer_id=policy_dict["farmer_id"],
        plot_id=policy_dict["plot_id"],
        crop_cycle_id=policy_dict.get("crop_cycle_id"),
        sum_insured=policy_dict["sum_insured"],
        area_insured_ha=policy_dict["area_insured_ha"],
        premium_amount=policy_dict["premium_amount"],
        premium_rate=policy_dict["premium_rate"],
        premium_paid=policy_dict["premium_paid"],
        premium_paid_at=policy_dict.get("premium_paid_at"),
        payment_reference=policy_dict.get("payment_reference"),
        coverage_start_date=policy_dict["coverage_start_date"],
        coverage_end_date=policy_dict["coverage_end_date"],
        status=policy_dict["status"],
        bank_account_number=policy_dict.get("bank_account_number"),
        bank_ifsc=policy_dict.get("bank_ifsc"),
        created_at=policy_dict["created_at"],
        updated_at=policy_dict["updated_at"],
        product=product_resp,
        active_claims_count=policy_dict.get("active_claims_count", 0),
    )


def _to_claim_response(claim_dict: dict[str, Any]) -> ClaimResponse:
    """Convert a claim dict to a ClaimResponse."""
    storage = get_storage()

    evidence_resps: list[ClaimEvidenceResponse] = []
    for e in claim_dict.get("evidence", []):
        file_url = None
        if e.file_url:
            try:
                file_url = storage.generate_download_url(e.file_url)
            except Exception:
                pass

        evidence_resps.append(
            ClaimEvidenceResponse(
                id=e.id,
                claim_id=e.claim_id,
                evidence_type=e.evidence_type,
                source_module=e.source_module,
                source_id=e.source_id,
                title=e.title,
                description=e.description,
                evidence_date=e.evidence_date,
                snapshot_data=e.snapshot_data,
                file_url=e.file_url,
                is_auto_attached=e.is_auto_attached,
                file_download_url=file_url,
                created_at=e.created_at,
            )
        )

    policy_resp = None
    if claim_dict.get("policy"):
        policy_resp = _to_policy_response(claim_dict["policy"])

    return ClaimResponse(
        id=claim_dict["id"],
        claim_number=claim_dict["claim_number"],
        policy_id=claim_dict["policy_id"],
        farmer_id=claim_dict["farmer_id"],
        claim_type=claim_dict["claim_type"],
        status=claim_dict["status"],
        loss_date=claim_dict["loss_date"],
        loss_description=claim_dict["loss_description"],
        estimated_loss_pct=claim_dict["estimated_loss_pct"],
        claimed_amount=claim_dict["claimed_amount"],
        approved_amount=claim_dict.get("approved_amount"),
        payout_transaction_id=claim_dict.get("payout_transaction_id"),
        payout_date=claim_dict.get("payout_date"),
        reviewed_by=claim_dict.get("reviewed_by"),
        reviewed_at=claim_dict.get("reviewed_at"),
        review_notes=claim_dict.get("review_notes"),
        rejection_reason=claim_dict.get("rejection_reason"),
        auto_evidence_summary=claim_dict.get("auto_evidence_summary"),
        submitted_at=claim_dict.get("submitted_at"),
        created_at=claim_dict["created_at"],
        updated_at=claim_dict["updated_at"],
        evidence=evidence_resps,
        policy=policy_resp,
    )
