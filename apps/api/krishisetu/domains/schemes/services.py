"""Schemes service — eligibility checking, application workflow, officer review."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from krishisetu.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from krishisetu.core.logging import get_logger
from krishisetu.domains.farmer import repository as farmer_repo
from krishisetu.domains.farmer.officer_scope import resolve_officer_jurisdiction
from krishisetu.domains.identity.models import User
from krishisetu.domains.schemes import repository as repo
from krishisetu.domains.schemes.eligibility import evaluate_eligibility
from krishisetu.domains.schemes.models import ApplicationStatus
from krishisetu.domains.schemes.schemas import (
    OfficerReviewRequest,
    SchemeApplicationCreate,
    SchemeApplicationListResponse,
    SchemeApplicationResponse,
    SchemeApplicationSubmit,
    SchemeListResponse,
    SchemeResponse,
    SchemeStatsResponse,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Scheme catalog
# ---------------------------------------------------------------------------


async def list_schemes(
    db: AsyncSession,
    farmer_id: UUID | None = None,
    *,
    category: str | None = None,
    state: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> SchemeListResponse:
    """List available government schemes.

    If farmer_id is provided, evaluates eligibility for each scheme and
    annotates the response with is_eligible and eligibility_reasons.
    """
    schemes, total = await repo.list_schemes(
        db, category=category, state=state, page=page, page_size=page_size
    )

    # If farmer is authenticated, check eligibility for each scheme
    farmer_data = None
    existing_apps = {}
    if farmer_id:
        farmer_data = await _compile_farmer_data(db, farmer_id)
        # Get existing applications for this farmer
        apps, _ = await repo.list_applications_by_farmer(db, farmer_id, page=1, page_size=100)
        for app in apps:
            existing_apps[app["scheme_id"]] = app

    scheme_responses: list[SchemeResponse] = []
    eligible_count = 0

    for scheme in schemes:
        resp = SchemeResponse.model_validate(scheme)

        if farmer_data:
            result = evaluate_eligibility(scheme.eligibility_rules, farmer_data)
            resp.is_eligible = result["eligible"]
            resp.eligibility_reasons = [
                c["label"] for c in result["failed_conditions"]
            ] if not result["eligible"] else None

            if result["eligible"]:
                eligible_count += 1

            # Check if farmer has applied
            existing = existing_apps.get(scheme.id)
            if existing:
                resp.has_applied = True
                resp.application_status = existing["status"]

        scheme_responses.append(resp)

    return SchemeListResponse(
        schemes=scheme_responses,
        total=total,
        eligible_count=eligible_count if farmer_id else None,
    )


async def get_scheme(
    db: AsyncSession,
    scheme_id: UUID,
    farmer_id: UUID | None = None,
) -> SchemeResponse:
    """Get a scheme by ID with eligibility check (if farmer authenticated)."""
    scheme = await repo.get_scheme_by_id(db, scheme_id)
    if not scheme:
        raise NotFoundError("Scheme", str(scheme_id))

    resp = SchemeResponse.model_validate(scheme)

    if farmer_id:
        farmer_data = await _compile_farmer_data(db, farmer_id)
        result = evaluate_eligibility(scheme.eligibility_rules, farmer_data)
        resp.is_eligible = result["eligible"]
        resp.eligibility_reasons = [
            c["label"] for c in result["failed_conditions"]
        ] if not result["eligible"] else None

        # Check existing application
        existing = await repo.find_existing_application(db, scheme_id, farmer_id)
        if existing:
            resp.has_applied = True
            resp.application_status = existing.status

    return resp


# ---------------------------------------------------------------------------
# Application workflow
# ---------------------------------------------------------------------------


async def create_application(
    db: AsyncSession,
    farmer_id: UUID,
    payload: SchemeApplicationCreate,
) -> SchemeApplicationResponse:
    """Create a new scheme application (draft).

    Steps:
    1. Verify scheme exists and is active
    2. Check for existing non-withdrawn application (prevent duplicates)
    3. Compile farmer data snapshot
    4. Evaluate eligibility (store result)
    5. Create application with status=draft
    """
    scheme = await repo.get_scheme_by_id(db, payload.scheme_id)
    if not scheme or not scheme.is_active:
        raise NotFoundError("Scheme", str(payload.scheme_id))

    # Check for existing application
    existing = await repo.find_existing_application(db, payload.scheme_id, farmer_id)
    if existing:
        raise ConflictError(
            f"You already have an application ({existing.application_number}) "
            f"for this scheme with status: {existing.status}."
        )

    # Compile farmer data and evaluate eligibility
    farmer_data = await _compile_farmer_data(db, farmer_id)
    eligibility_result = evaluate_eligibility(scheme.eligibility_rules, farmer_data)

    # Build submitted_data snapshot
    submitted_data = {
        **farmer_data,
        **(payload.additional_data or {}),
    }

    # Generate application number
    app_number = _generate_application_number()

    app = await repo.create_application(
        db,
        application_number=app_number,
        scheme_id=payload.scheme_id,
        farmer_id=farmer_id,
        submitted_data=submitted_data,
        eligibility_result=eligibility_result,
    )

    logger.info(
        "schemes.application_created",
        app_id=str(app.id),
        app_number=app_number,
        scheme=scheme.code,
        farmer_id=str(farmer_id),
        eligible=eligibility_result["eligible"],
    )

    app_dict = await repo.get_application_by_id(db, app.id)
    return SchemeApplicationResponse(**app_dict)


async def submit_application(
    db: AsyncSession,
    app_id: UUID,
    farmer_id: UUID,
    payload: SchemeApplicationSubmit,
) -> SchemeApplicationResponse:
    """Submit a draft application for review."""
    app_dict = await repo.get_application_by_id(db, app_id)
    if not app_dict:
        raise NotFoundError("SchemeApplication", str(app_id))

    if app_dict["farmer_id"] != farmer_id:
        raise NotFoundError("SchemeApplication", str(app_id))

    if app_dict["status"] != ApplicationStatus.DRAFT.value:
        raise ValidationError(
            f"Application is in '{app_dict['status']}' state. "
            "Only draft applications can be submitted."
        )

    # Merge additional data
    submitted_data = app_dict.get("submitted_data", {})
    if payload.additional_data:
        submitted_data.update(payload.additional_data)

    # Re-evaluate eligibility (farmer data may have changed since draft creation)
    scheme = await repo.get_scheme_by_id(db, app_dict["scheme_id"])
    farmer_data = await _compile_farmer_data(db, farmer_id)
    eligibility_result = evaluate_eligibility(scheme.eligibility_rules, farmer_data)

    updated = await repo.submit_application(
        db,
        app_id,
        submitted_data=submitted_data,
        eligibility_result=eligibility_result,
        submitted_documents=payload.submitted_documents,
    )

    logger.info(
        "schemes.application_submitted",
        app_id=str(app_id),
        eligible=eligibility_result["eligible"],
    )

    return SchemeApplicationResponse(**updated)


async def list_my_applications(
    db: AsyncSession,
    farmer_id: UUID,
    *,
    status: ApplicationStatus | None = None,
) -> SchemeApplicationListResponse:
    """List the farmer's scheme applications."""
    apps, total = await repo.list_applications_by_farmer(
        db, farmer_id, status=status
    )
    return SchemeApplicationListResponse(
        applications=[SchemeApplicationResponse(**a) for a in apps],
        total=total,
    )


async def get_application(
    db: AsyncSession,
    app_id: UUID,
    farmer_id: UUID,
) -> SchemeApplicationResponse:
    """Get an application by ID (verifies ownership)."""
    app_dict = await repo.get_application_by_id(db, app_id)
    if not app_dict:
        raise NotFoundError("SchemeApplication", str(app_id))

    if app_dict["farmer_id"] != farmer_id:
        raise NotFoundError("SchemeApplication", str(app_id))

    return SchemeApplicationResponse(**app_dict)


async def withdraw_application(
    db: AsyncSession,
    app_id: UUID,
    farmer_id: UUID,
) -> SchemeApplicationResponse:
    """Farmer withdraws an application."""
    app_dict = await repo.get_application_by_id(db, app_id)
    if not app_dict:
        raise NotFoundError("SchemeApplication", str(app_id))

    if app_dict["farmer_id"] != farmer_id:
        raise NotFoundError("SchemeApplication", str(app_id))

    if app_dict["status"] in (
        ApplicationStatus.APPROVED.value,
        ApplicationStatus.BENEFIT_DISBURSED.value,
        ApplicationStatus.WITHDRAWN.value,
    ):
        raise ValidationError(
            f"Cannot withdraw application in '{app_dict['status']}' state."
        )

    updated = await repo.withdraw_application(db, app_id)
    return SchemeApplicationResponse(**updated)


# ---------------------------------------------------------------------------
# Officer review
# ---------------------------------------------------------------------------


async def officer_list_applications(
    db: AsyncSession,
    officer: User,
    *,
    status: ApplicationStatus | None = None,
    page: int = 1,
    page_size: int = 20,
) -> SchemeApplicationListResponse:
    """List applications for officer review, scoped to the officer's district."""
    jurisdiction = resolve_officer_jurisdiction(officer)

    apps, total = await repo.list_applications_for_review(
        db,
        district=jurisdiction.district if jurisdiction else None,
        state=jurisdiction.state if jurisdiction else None,
        status=status,
        page=page,
        page_size=page_size,
    )
    return SchemeApplicationListResponse(
        applications=[SchemeApplicationResponse(**a) for a in apps],
        total=total,
    )


async def officer_review_application(
    db: AsyncSession,
    app_id: UUID,
    officer: User,
    payload: OfficerReviewRequest,
) -> SchemeApplicationResponse:
    """Officer reviews a scheme application from their own district."""
    officer_id = officer.id
    app_dict = await repo.get_application_by_id(db, app_id)
    if not app_dict:
        raise NotFoundError("SchemeApplication", str(app_id))

    jurisdiction = resolve_officer_jurisdiction(officer)
    if jurisdiction is not None:
        in_district = await farmer_repo.farmer_has_plot_in_district(
            db,
            app_dict["farmer_id"],
            jurisdiction.district,
            jurisdiction.state,
        )
        if not in_district:
            raise NotFoundError("SchemeApplication", str(app_id))

    if app_dict["status"] not in (
        ApplicationStatus.SUBMITTED.value,
        ApplicationStatus.UNDER_REVIEW.value,
        ApplicationStatus.RESUBMISSION_REQUESTED.value,
    ):
        raise ValidationError(
            f"Application is in '{app_dict['status']}' state. "
            f"Only submitted/under_review applications can be reviewed."
        )

    if payload.action == "reject" and not payload.rejection_reason:
        raise ValidationError("rejection_reason is required when action=reject")

    updated = await repo.officer_review_application(
        db,
        app_id,
        officer_id,
        action=payload.action,
        review_notes=payload.review_notes,
        rejection_reason=payload.rejection_reason,
        benefit_reference=payload.benefit_reference,
    )

    logger.info(
        "schemes.application_reviewed",
        app_id=str(app_id),
        action=payload.action,
        officer_id=str(officer_id),
    )

    return SchemeApplicationResponse(**updated)


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


async def get_scheme_stats(
    db: AsyncSession, farmer_id: UUID
) -> SchemeStatsResponse:
    """Get scheme application stats for a farmer."""
    stats = await repo.get_farmer_scheme_stats(db, farmer_id)

    # Count eligible schemes
    farmer_data = await _compile_farmer_data(db, farmer_id)
    schemes, _ = await repo.list_schemes(db, page=1, page_size=200)
    eligible = sum(
        1 for s in schemes
        if evaluate_eligibility(s.eligibility_rules, farmer_data)["eligible"]
    )
    stats["eligible_schemes"] = eligible

    return SchemeStatsResponse(**stats)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _compile_farmer_data(db: AsyncSession, farmer_id: UUID) -> dict[str, Any]:
    """Compile farmer profile data for eligibility evaluation.

    Gathers data from:
    - identity.users (role, aadhaar_verified, preferred_language)
    - farmer.plots (total_land_holding_ha, state, district, irrigation_source)
    - farmer.crop_cycles (has_active_crop_cycle)
    - insurance.policies (bank_account_number)
    """
    from krishisetu.domains.farmer.repository import check_active_crop_cycle, list_plots_by_farmer
    from krishisetu.domains.identity import repository as identity_repo

    user = await identity_repo.get_user_by_id(db, farmer_id)

    data: dict[str, Any] = {
        "role": user.role.value if user else "unknown",
        "aadhaar_verified": user.aadhaar_verified if user else False,
        "state": None,
        "district": None,
        "total_land_holding_ha": 0,
        "irrigation_source": [],
        "has_active_crop_cycle": False,
        "bank_account_number": None,
        "occupation_category": "farmer",  # Default — future: add to profile
    }

    if not user:
        return data

    # Get plots
    plots, _ = await list_plots_by_farmer(db, farmer_id, page=1, page_size=100)

    if plots:
        total_area = sum(float(p.get("area_ha", 0)) for p in plots)
        data["total_land_holding_ha"] = total_area
        data["state"] = plots[0].get("state")
        data["district"] = plots[0].get("district")

        # Collect irrigation sources
        irrigation_sources = set()
        for p in plots:
            src = p.get("irrigation_source")
            if src:
                irrigation_sources.add(src)
        data["irrigation_source"] = list(irrigation_sources) if irrigation_sources else []

        # Check for active crop cycle
        for p in plots:
            plot_id = p.get("id")
            if plot_id:
                has_cycle = await check_active_crop_cycle(db, plot_id)
                if has_cycle:
                    data["has_active_crop_cycle"] = True
                    break

    # Check for bank account (from insurance policies)
    from krishisetu.domains.insurance.repository import list_policies_by_farmer
    policies, _ = await list_policies_by_farmer(db, farmer_id, page=1, page_size=1)
    if policies:
        data["bank_account_number"] = policies[0].get("bank_account_number")

    return data


def _generate_application_number() -> str:
    """Generate unique application number: KS-SCH-YYYYMMDD-8hex"""
    today = datetime.now(UTC).strftime("%Y%m%d")
    short_uuid = uuid.uuid4().hex[:8]
    return f"KS-SCH-{today}-{short_uuid}"
