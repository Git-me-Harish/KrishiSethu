"""Database access layer for the insurance domain."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import and_, desc, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from krishisetu.domains.insurance.models import (
    ClaimEvidence,
    ClaimStatus,
    ClaimType,
    InsuranceClaim,
    InsurancePolicy,
    InsuranceProduct,
    PolicyStatus,
)

# ---------------------------------------------------------------------------
# Product queries
# ---------------------------------------------------------------------------


async def list_products(
    db: AsyncSession,
    *,
    state: str | None = None,
    crop_slug: str | None = None,
    season: str | None = None,
    season_year: int | None = None,
    product_type: str | None = None,
    is_active: bool = True,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[InsuranceProduct], int]:
    """List insurance products with optional filters."""
    query = select(InsuranceProduct).where(InsuranceProduct.is_active == is_active)
    count_query = select(func.count(InsuranceProduct.id)).where(
        InsuranceProduct.is_active == is_active
    )

    if state:
        query = query.where(InsuranceProduct.state == state)
        count_query = count_query.where(InsuranceProduct.state == state)
    if crop_slug:
        query = query.where(InsuranceProduct.crop_slug == crop_slug)
        count_query = count_query.where(InsuranceProduct.crop_slug == crop_slug)
    if season:
        query = query.where(InsuranceProduct.season == season)
        count_query = count_query.where(InsuranceProduct.season == season)
    if season_year:
        query = query.where(InsuranceProduct.season_year == season_year)
        count_query = count_query.where(InsuranceProduct.season_year == season_year)
    if product_type:
        query = query.where(InsuranceProduct.product_type == product_type)
        count_query = count_query.where(InsuranceProduct.product_type == product_type)

    total = (await db.execute(count_query)).scalar_one()
    offset = (page - 1) * page_size
    query = (
        query.order_by(InsuranceProduct.state, InsuranceProduct.crop_name)
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(query)
    return list(result.scalars().all()), total


async def get_product_by_id(db: AsyncSession, product_id: UUID) -> InsuranceProduct | None:
    result = await db.execute(
        select(InsuranceProduct).where(InsuranceProduct.id == product_id)
    )
    return result.scalar_one_or_none()


async def find_product_for_plot(
    db: AsyncSession,
    plot_id: UUID,
    crop_slug: str | None = None,
) -> list[InsuranceProduct]:
    """Find insurance products available for a plot (based on plot's state and crop)."""
    from krishisetu.domains.farmer.models import Plot

    # Get plot's state
    plot_result = await db.execute(
        select(Plot.state).where(Plot.id == plot_id)
    )
    plot_state = plot_result.scalar_one_or_none()
    if not plot_state:
        return []

    # Find active products for that state
    query = (
        select(InsuranceProduct)
        .where(
            and_(
                InsuranceProduct.state == plot_state,
                InsuranceProduct.is_active.is_(True),
            )
        )
        .order_by(InsuranceProduct.crop_name)
    )
    if crop_slug:
        query = query.where(InsuranceProduct.crop_slug == crop_slug)

    result = await db.execute(query)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Policy queries
# ---------------------------------------------------------------------------


async def create_policy(
    db: AsyncSession,
    *,
    policy_number: str,
    product_id: UUID,
    farmer_id: UUID,
    plot_id: UUID,
    crop_cycle_id: UUID | None,
    sum_insured: Decimal,
    area_insured_ha: Decimal,
    premium_amount: Decimal,
    premium_rate: Decimal,
    coverage_start_date,
    coverage_end_date,
    bank_account_number: str | None = None,
    bank_ifsc: str | None = None,
) -> InsurancePolicy:
    """Create a new insurance policy (status=pending until premium paid)."""
    policy = InsurancePolicy(
        policy_number=policy_number,
        product_id=product_id,
        farmer_id=farmer_id,
        plot_id=plot_id,
        crop_cycle_id=crop_cycle_id,
        sum_insured=sum_insured,
        area_insured_ha=area_insured_ha,
        premium_amount=premium_amount,
        premium_rate=premium_rate,
        coverage_start_date=coverage_start_date,
        coverage_end_date=coverage_end_date,
        bank_account_number=bank_account_number,
        bank_ifsc=bank_ifsc,
        status=PolicyStatus.PENDING,
    )
    db.add(policy)
    await db.flush()
    await db.refresh(policy)
    return policy


async def get_policy_by_id(
    db: AsyncSession, policy_id: UUID, *, include_product: bool = True
) -> dict[str, Any] | None:
    """Get a policy by ID with product info joined."""
    query = text("""
        SELECT p.*, pr.slug as product_slug, pr.name as product_name,
               pr.product_type, pr.insurer_name, pr.crop_slug, pr.crop_name,
               pr.season as product_season, pr.season_year as product_season_year,
               pr.state as product_state, pr.sum_insured_per_ha,
               pr.farmer_premium_rate, pr.coverage_start_date as product_coverage_start,
               pr.coverage_end_date as product_coverage_end,
               pr.claim_cutoff_yield, pr.description as product_description,
               pr.is_active as product_is_active,
               (SELECT COUNT(*) FROM insurance.insurance_claims c
                WHERE c.policy_id = p.id
                  AND c.status IN ('draft', 'submitted', 'under_review', 'evidence_requested')
               ) as active_claims_count
        FROM insurance.insurance_policies p
        LEFT JOIN insurance.insurance_products pr ON pr.id = p.product_id
        WHERE p.id = :policy_id
    """)
    result = await db.execute(query, {"policy_id": policy_id})
    row = result.fetchone()
    if not row:
        return None
    return _row_to_policy_dict(row)


async def get_policy_by_number(db: AsyncSession, policy_number: str) -> InsurancePolicy | None:
    result = await db.execute(
        select(InsurancePolicy).where(InsurancePolicy.policy_number == policy_number)
    )
    return result.scalar_one_or_none()


async def list_policies_by_farmer(
    db: AsyncSession,
    farmer_id: UUID,
    *,
    status: PolicyStatus | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    """List a farmer's insurance policies with product info."""
    count_query = (
        select(func.count(InsurancePolicy.id))
        .where(InsurancePolicy.farmer_id == farmer_id)
    )
    if status:
        count_query = count_query.where(InsurancePolicy.status == status)
    total = (await db.execute(count_query)).scalar_one()

    offset = (page - 1) * page_size
    query = text("""
        SELECT p.*, pr.slug as product_slug, pr.name as product_name,
               pr.product_type, pr.insurer_name, pr.crop_slug, pr.crop_name,
               pr.season as product_season, pr.season_year as product_season_year,
               pr.state as product_state, pr.sum_insured_per_ha,
               pr.farmer_premium_rate, pr.coverage_start_date as product_coverage_start,
               pr.coverage_end_date as product_coverage_end,
               pr.claim_cutoff_yield, pr.description as product_description,
               pr.is_active as product_is_active,
               (SELECT COUNT(*) FROM insurance.insurance_claims c
                WHERE c.policy_id = p.id
                  AND c.status IN ('draft', 'submitted', 'under_review', 'evidence_requested')
               ) as active_claims_count
        FROM insurance.insurance_policies p
        LEFT JOIN insurance.insurance_products pr ON pr.id = p.product_id
        WHERE p.farmer_id = :farmer_id
        ORDER BY p.created_at DESC
        LIMIT :limit OFFSET :offset
    """)
    params: dict[str, Any] = {"farmer_id": farmer_id, "limit": page_size, "offset": offset}
    if status:
        query = query.replace(
            "WHERE p.farmer_id = :farmer_id",
            "WHERE p.farmer_id = :farmer_id AND p.status = :status",
        )
        params["status"] = status.value

    result = await db.execute(query, params)
    policies = [_row_to_policy_dict(row) for row in result.fetchall()]
    return policies, total


async def update_policy_premium_payment(
    db: AsyncSession,
    policy_id: UUID,
    payment_reference: str,
) -> InsurancePolicy | None:
    """Mark a policy's premium as paid and activate it."""
    await db.execute(
        update(InsurancePolicy)
        .where(InsurancePolicy.id == policy_id)
        .values(
            premium_paid=True,
            premium_paid_at=datetime.now(UTC),
            payment_reference=payment_reference,
            status=PolicyStatus.ACTIVE.value,
            updated_at=datetime.now(UTC),
        )
    )
    await db.flush()
    result = await db.execute(
        select(InsurancePolicy).where(InsurancePolicy.id == policy_id)
    )
    return result.scalar_one_or_none()


async def get_active_policy_for_plot(
    db: AsyncSession, plot_id: UUID
) -> InsurancePolicy | None:
    """Get the active insurance policy for a plot (if any)."""
    result = await db.execute(
        select(InsurancePolicy)
        .where(
            and_(
                InsurancePolicy.plot_id == plot_id,
                InsurancePolicy.status == PolicyStatus.ACTIVE.value,
            )
        )
        .order_by(desc(InsurancePolicy.created_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Claim queries
# ---------------------------------------------------------------------------


async def create_claim(
    db: AsyncSession,
    *,
    claim_number: str,
    policy_id: UUID,
    farmer_id: UUID,
    claim_type: ClaimType,
    loss_date,
    loss_description: str,
    estimated_loss_pct: Decimal,
    claimed_amount: Decimal,
) -> InsuranceClaim:
    """Create a new insurance claim (status=draft)."""
    claim = InsuranceClaim(
        claim_number=claim_number,
        policy_id=policy_id,
        farmer_id=farmer_id,
        claim_type=claim_type,
        loss_date=loss_date,
        loss_description=loss_description,
        estimated_loss_pct=estimated_loss_pct,
        claimed_amount=claimed_amount,
        status=ClaimStatus.DRAFT,
    )
    db.add(claim)
    await db.flush()
    await db.refresh(claim)
    return claim


async def get_claim_by_id(
    db: AsyncSession, claim_id: UUID, *, include_evidence: bool = True
) -> dict[str, Any] | None:
    """Get a claim by ID with evidence joined."""
    if include_evidence:
        query = text("""
            SELECT c.*, p.policy_number, p.sum_insured, p.area_insured_ha,
                   p.premium_amount, p.status as policy_status,
                   p.coverage_start_date, p.coverage_end_date,
                   pr.crop_slug, pr.crop_name, pr.season as product_season,
                   pr.season_year as product_season_year, pr.insurer_name,
                   pl.survey_number, pl.village, pl.district, pl.state as plot_state
            FROM insurance.insurance_claims c
            LEFT JOIN insurance.insurance_policies p ON p.id = c.policy_id
            LEFT JOIN insurance.insurance_products pr ON pr.id = p.product_id
            LEFT JOIN farmer.plots pl ON pl.id = p.plot_id
            WHERE c.id = :claim_id
        """)
        result = await db.execute(query, {"claim_id": claim_id})
        row = result.fetchone()
        if not row:
            return None
        claim_dict = _row_to_claim_dict(row)
        # Fetch evidence separately
        evidence = await list_evidence_by_claim(db, claim_id)
        claim_dict["evidence"] = evidence
        return claim_dict
    else:
        result = await db.execute(
            select(InsuranceClaim).where(InsuranceClaim.id == claim_id)
        )
        claim = result.scalar_one_or_none()
        return claim


async def list_claims_by_farmer(
    db: AsyncSession,
    farmer_id: UUID,
    *,
    status: ClaimStatus | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    """List a farmer's insurance claims."""
    count_query = (
        select(func.count(InsuranceClaim.id))
        .where(InsuranceClaim.farmer_id == farmer_id)
    )
    if status:
        count_query = count_query.where(InsuranceClaim.status == status)
    total = (await db.execute(count_query)).scalar_one()

    offset = (page - 1) * page_size
    query = text("""
        SELECT c.*, p.policy_number, pr.crop_slug, pr.crop_name,
               pr.season as product_season, pr.season_year as product_season_year
        FROM insurance.insurance_claims c
        LEFT JOIN insurance.insurance_policies p ON p.id = c.policy_id
        LEFT JOIN insurance.insurance_products pr ON pr.id = p.product_id
        WHERE c.farmer_id = :farmer_id
        ORDER BY c.created_at DESC
        LIMIT :limit OFFSET :offset
    """)
    params: dict[str, Any] = {"farmer_id": farmer_id, "limit": page_size, "offset": offset}
    if status:
        query = query.replace(
            "WHERE c.farmer_id = :farmer_id",
            "WHERE c.farmer_id = :farmer_id AND c.status = :status",
        )
        params["status"] = status.value

    result = await db.execute(query, params)
    claims = [_row_to_claim_dict(row) for row in result.fetchall()]
    return claims, total


async def list_claims_for_insurer(
    db: AsyncSession,
    *,
    insurer_name: str | None = None,
    status: ClaimStatus | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    """List claims for insurer review (submitted or under_review).

    When `insurer_name` is given, only claims on that insurer's products are
    returned. None means unrestricted (admin).
    """
    base_filter = InsuranceClaim.status.in_([
        ClaimStatus.SUBMITTED.value,
        ClaimStatus.UNDER_REVIEW.value,
        ClaimStatus.EVIDENCE_REQUESTED.value,
    ])

    count_query = select(func.count(InsuranceClaim.id)).where(base_filter)
    if status:
        count_query = count_query.where(InsuranceClaim.status == status)
    if insurer_name:
        count_query = count_query.where(
            InsuranceClaim.policy_id.in_(
                select(InsurancePolicy.id).where(
                    InsurancePolicy.product_id.in_(
                        select(InsuranceProduct.id).where(
                            InsuranceProduct.insurer_name == insurer_name
                        )
                    )
                )
            )
        )
    total = (await db.execute(count_query)).scalar_one()

    offset = (page - 1) * page_size
    insurer_clause = "AND pr.insurer_name = :insurer_name" if insurer_name else ""
    query = text(f"""
        SELECT c.*, p.policy_number, p.sum_insured, p.area_insured_ha,
               pr.crop_slug, pr.crop_name, pr.season as product_season,
               pr.season_year as product_season_year, pr.insurer_name,
               pl.survey_number, pl.village, pl.district, pl.state as plot_state,
               u.full_name as farmer_name, u.phone as farmer_phone
        FROM insurance.insurance_claims c
        LEFT JOIN insurance.insurance_policies p ON p.id = c.policy_id
        LEFT JOIN insurance.insurance_products pr ON pr.id = p.product_id
        LEFT JOIN farmer.plots pl ON pl.id = p.plot_id
        LEFT JOIN identity.users u ON u.id = c.farmer_id
        WHERE c.status IN ('submitted', 'under_review', 'evidence_requested')
        {insurer_clause}
        ORDER BY c.submitted_at ASC
        LIMIT :limit OFFSET :offset
    """)  # noqa: S608 -- insurer_clause is a fixed fragment; value is bound via params
    params: dict[str, Any] = {"limit": page_size, "offset": offset}
    if insurer_name:
        params["insurer_name"] = insurer_name
    result = await db.execute(query, params)
    claims = [_row_to_claim_dict(row) for row in result.fetchall()]
    return claims, total


async def update_claim(
    db: AsyncSession,
    claim_id: UUID,
    **fields: Any,
) -> dict[str, Any] | None:
    """Update a claim's fields."""
    if not fields:
        return await get_claim_by_id(db, claim_id, include_evidence=False)

    # Allowlist
    allowed = {"claim_type", "loss_date", "loss_description", "estimated_loss_pct"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return await get_claim_by_id(db, claim_id, include_evidence=False)

    if "claim_type" in updates and hasattr(updates["claim_type"], "value"):
        updates["claim_type"] = updates["claim_type"].value

    # set_clauses only ever uses keys from `allowed` above; values are bound
    # via params, so no user-controlled string reaches the SQL text.
    set_clauses = ", ".join(f"{k} = :{k}" for k in updates)
    query = text(f"""
        UPDATE insurance.insurance_claims
        SET {set_clauses}, updated_at = NOW()
        WHERE id = :claim_id
    """)  # noqa: S608
    await db.execute(query, {"claim_id": claim_id, **updates})
    await db.flush()
    return await get_claim_by_id(db, claim_id, include_evidence=False)


async def submit_claim(
    db: AsyncSession,
    claim_id: UUID,
    bank_account_number: str,
    bank_ifsc: str,
    auto_evidence_summary: dict[str, Any],
) -> dict[str, Any] | None:
    """Submit a draft claim for insurer review."""
    await db.execute(
        update(InsuranceClaim)
        .where(InsuranceClaim.id == claim_id)
        .values(
            status=ClaimStatus.SUBMITTED.value,
            submitted_at=datetime.now(UTC),
            auto_evidence_summary=auto_evidence_summary,
            updated_at=datetime.now(UTC),
        )
    )
    # Also update bank details on the policy
    claim = await get_claim_by_id(db, claim_id, include_evidence=False)
    if claim:
        await db.execute(
            update(InsurancePolicy)
            .where(InsurancePolicy.id == claim["policy_id"])
            .values(
                bank_account_number=bank_account_number,
                bank_ifsc=bank_ifsc,
                updated_at=datetime.now(UTC),
            )
        )
    await db.flush()
    return await get_claim_by_id(db, claim_id, include_evidence=True)


async def insurer_review_claim(
    db: AsyncSession,
    claim_id: UUID,
    insurer_id: UUID,
    action: str,
    approved_amount: Decimal | None = None,
    review_notes: str | None = None,
    rejection_reason: str | None = None,
    evidence_request_notes: str | None = None,
) -> dict[str, Any] | None:
    """Insurer reviews a claim (approve/reject/request_evidence)."""
    now = datetime.now(UTC)
    new_status = {
        "approve": ClaimStatus.APPROVED,
        "reject": ClaimStatus.REJECTED,
        "request_evidence": ClaimStatus.EVIDENCE_REQUESTED,
    }[action]

    update_values: dict[str, Any] = {
        "status": new_status.value,
        "reviewed_by": insurer_id,
        "reviewed_at": now,
        "updated_at": now,
    }
    if approved_amount is not None:
        update_values["approved_amount"] = approved_amount
    if review_notes:
        update_values["review_notes"] = review_notes
    if rejection_reason:
        update_values["rejection_reason"] = rejection_reason
    if evidence_request_notes:
        update_values["review_notes"] = evidence_request_notes

    await db.execute(
        update(InsuranceClaim)
        .where(InsuranceClaim.id == claim_id)
        .values(**update_values)
    )
    await db.flush()
    return await get_claim_by_id(db, claim_id, include_evidence=True)


async def withdraw_claim(
    db: AsyncSession, claim_id: UUID
) -> dict[str, Any] | None:
    """Farmer withdraws a claim."""
    await db.execute(
        update(InsuranceClaim)
        .where(InsuranceClaim.id == claim_id)
        .values(
            status=ClaimStatus.WITHDRAWN.value,
            updated_at=datetime.now(UTC),
        )
    )
    await db.flush()
    return await get_claim_by_id(db, claim_id, include_evidence=False)


# ---------------------------------------------------------------------------
# Claim evidence queries
# ---------------------------------------------------------------------------


async def create_evidence(
    db: AsyncSession,
    *,
    claim_id: UUID,
    evidence_type: str,
    source_module: str,
    title: str,
    description: str,
    evidence_date: datetime,
    source_id: UUID | None = None,
    snapshot_data: dict[str, Any] | None = None,
    file_url: str | None = None,
    is_auto_attached: bool = False,
) -> ClaimEvidence:
    """Create a new evidence record."""
    evidence = ClaimEvidence(
        claim_id=claim_id,
        evidence_type=evidence_type,
        source_module=source_module,
        source_id=source_id,
        title=title,
        description=description,
        evidence_date=evidence_date,
        snapshot_data=snapshot_data,
        file_url=file_url,
        is_auto_attached=is_auto_attached,
    )
    db.add(evidence)
    await db.flush()
    await db.refresh(evidence)
    return evidence


async def list_evidence_by_claim(
    db: AsyncSession, claim_id: UUID
) -> list[ClaimEvidence]:
    """List all evidence for a claim."""
    result = await db.execute(
        select(ClaimEvidence)
        .where(ClaimEvidence.claim_id == claim_id)
        .order_by(desc(ClaimEvidence.is_auto_attached), ClaimEvidence.evidence_date)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


async def get_farmer_insurance_stats(
    db: AsyncSession, farmer_id: UUID
) -> dict[str, Any]:
    """Get summary stats for a farmer's insurance."""
    query = text("""
        SELECT
            COUNT(*) as total_policies,
            COUNT(*) FILTER (WHERE status = 'active') as active_policies,
            COUNT(*) FILTER (WHERE status = 'expired') as expired_policies,
            COALESCE(SUM(sum_insured), 0) as total_sum_insured,
            COALESCE(SUM(CASE WHEN premium_paid THEN premium_amount ELSE 0 END), 0)
                as total_premium_paid
        FROM insurance.insurance_policies
        WHERE farmer_id = :farmer_id
    """)
    result = await db.execute(query, {"farmer_id": farmer_id})
    row = result.fetchone()

    claim_query = text("""
        SELECT
            COUNT(*) as total_claims,
            COUNT(*) FILTER (
                WHERE status IN ('draft', 'submitted', 'under_review', 'evidence_requested')
            ) as pending_claims,
            COUNT(*) FILTER (WHERE status IN ('approved', 'payout_disbursed')) as approved_claims,
            COALESCE(SUM(claimed_amount), 0) as total_claimed_amount,
            COALESCE(SUM(COALESCE(approved_amount, 0)), 0) as total_approved_amount
        FROM insurance.insurance_claims
        WHERE farmer_id = :farmer_id
    """)
    claim_result = await db.execute(claim_query, {"farmer_id": farmer_id})
    claim_row = claim_result.fetchone()

    return {
        "total_policies": row[0] or 0,
        "active_policies": row[1] or 0,
        "expired_policies": row[2] or 0,
        "total_sum_insured": Decimal(str(row[3] or 0)),
        "total_premium_paid": Decimal(str(row[4] or 0)),
        "total_claims": claim_row[0] or 0,
        "pending_claims": claim_row[1] or 0,
        "approved_claims": claim_row[2] or 0,
        "total_claimed_amount": Decimal(str(claim_row[3] or 0)),
        "total_approved_amount": Decimal(str(claim_row[4] or 0)),
    }


# ---------------------------------------------------------------------------
# Row mappers
# ---------------------------------------------------------------------------


def _row_to_policy_dict(row: Any) -> dict[str, Any]:
    """Convert a row to a policy dict with product info."""
    product_dict = None
    if getattr(row, "product_slug", None):
        product_dict = {
            "id": row.product_id,
            "slug": row.product_slug,
            "name": row.product_name,
            "product_type": row.product_type,
            "insurer_name": row.insurer_name,
            "crop_slug": row.crop_slug,
            "crop_name": row.crop_name,
            "season": row.product_season,
            "season_year": row.product_season_year,
            "state": row.product_state,
            "district": None,
            "sum_insured_per_ha": row.sum_insured_per_ha,
            "farmer_premium_rate": row.farmer_premium_rate,
            "farmer_premium_min": None,
            "farmer_premium_max": None,
            "coverage_start_date": row.product_coverage_start,
            "coverage_end_date": row.product_coverage_end,
            "claim_cutoff_yield": row.claim_cutoff_yield,
            "description": row.product_description,
            "is_active": row.product_is_active,
        }

    return {
        "id": row.id,
        "policy_number": row.policy_number,
        "product_id": row.product_id,
        "farmer_id": row.farmer_id,
        "plot_id": row.plot_id,
        "crop_cycle_id": row.crop_cycle_id,
        "sum_insured": Decimal(str(row.sum_insured)),
        "area_insured_ha": Decimal(str(row.area_insured_ha)),
        "premium_amount": Decimal(str(row.premium_amount)),
        "premium_rate": Decimal(str(row.premium_rate)),
        "premium_paid": row.premium_paid,
        "premium_paid_at": row.premium_paid_at,
        "payment_reference": row.payment_reference,
        "coverage_start_date": row.coverage_start_date,
        "coverage_end_date": row.coverage_end_date,
        "status": row.status,
        "bank_account_number": row.bank_account_number,
        "bank_ifsc": row.bank_ifsc,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "product": product_dict,
        "active_claims_count": getattr(row, "active_claims_count", 0) or 0,
    }


def _row_to_claim_dict(row: Any) -> dict[str, Any]:
    """Convert a row to a claim dict with policy info."""
    policy_dict = None
    if getattr(row, "policy_number", None):
        policy_dict = {
            "id": row.policy_id,
            "policy_number": row.policy_number,
            "product_id": None,
            "farmer_id": row.farmer_id,
            "plot_id": None,
            "crop_cycle_id": None,
            "sum_insured": Decimal(str(row.sum_insured)) if row.sum_insured else None,
            "area_insured_ha": Decimal(str(row.area_insured_ha)) if row.area_insured_ha else None,
            "premium_amount": Decimal(str(row.premium_amount)) if row.premium_amount else None,
            "premium_rate": None,
            "premium_paid": None,
            "premium_paid_at": None,
            "payment_reference": None,
            "coverage_start_date": getattr(row, "coverage_start_date", None),
            "coverage_end_date": getattr(row, "coverage_end_date", None),
            "status": getattr(row, "policy_status", None),
            "bank_account_number": None,
            "bank_ifsc": None,
            "created_at": None,
            "updated_at": None,
            "product": None,
            "active_claims_count": 0,
        }
        # Add crop info if available
        if getattr(row, "crop_slug", None):
            policy_dict["product"] = {
                "crop_slug": row.crop_slug,
                "crop_name": row.crop_name,
                "season": getattr(row, "product_season", None),
                "season_year": getattr(row, "product_season_year", None),
                "insurer_name": getattr(row, "insurer_name", None),
            }

    return {
        "id": row.id,
        "claim_number": row.claim_number,
        "policy_id": row.policy_id,
        "farmer_id": row.farmer_id,
        "claim_type": row.claim_type,
        "status": row.status,
        "loss_date": row.loss_date,
        "loss_description": row.loss_description,
        "estimated_loss_pct": Decimal(str(row.estimated_loss_pct)),
        "claimed_amount": Decimal(str(row.claimed_amount)),
        "approved_amount": Decimal(str(row.approved_amount)) if row.approved_amount else None,
        "payout_transaction_id": row.payout_transaction_id,
        "payout_date": row.payout_date,
        "reviewed_by": row.reviewed_by,
        "reviewed_at": row.reviewed_at,
        "review_notes": row.review_notes,
        "rejection_reason": row.rejection_reason,
        "auto_evidence_summary": row.auto_evidence_summary,
        "submitted_at": row.submitted_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "evidence": [],  # Filled separately if needed
        "policy": policy_dict,
    }
