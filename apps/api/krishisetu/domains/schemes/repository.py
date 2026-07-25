"""Database access layer for the schemes domain."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, desc, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from krishisetu.domains.schemes.models import (
    ApplicationStatus,
    SchemeApplication,
    SchemeCatalog,
)


# ---------------------------------------------------------------------------
# Scheme catalog queries
# ---------------------------------------------------------------------------


async def list_schemes(
    db: AsyncSession,
    *,
    category: str | None = None,
    state: str | None = None,
    is_active: bool = True,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[SchemeCatalog], int]:
    """List schemes with optional filters."""
    query = select(SchemeCatalog).where(SchemeCatalog.is_active == is_active)
    count_query = select(func.count(SchemeCatalog.id)).where(SchemeCatalog.is_active == is_active)

    if category:
        query = query.where(SchemeCatalog.category == category)
        count_query = count_query.where(SchemeCatalog.category == category)

    # State filter uses JSONB contains
    if state:
        query = query.where(
            or_(
                SchemeCatalog.states.is_(None),  # All states
                SchemeCatalog.states.contains([state]),  # State in list
            )
        )
        count_query = count_query.where(
            or_(
                SchemeCatalog.states.is_(None),
                SchemeCatalog.states.contains([state]),
            )
        )

    total = (await db.execute(count_query)).scalar_one()
    offset = (page - 1) * page_size
    query = query.order_by(desc(SchemeCatalog.is_featured), SchemeCatalog.name).offset(offset).limit(page_size)
    result = await db.execute(query)
    return list(result.scalars().all()), total


async def get_scheme_by_id(db: AsyncSession, scheme_id: UUID) -> SchemeCatalog | None:
    result = await db.execute(
        select(SchemeCatalog).where(SchemeCatalog.id == scheme_id)
    )
    return result.scalar_one_or_none()


async def get_scheme_by_code(db: AsyncSession, code: str) -> SchemeCatalog | None:
    result = await db.execute(
        select(SchemeCatalog).where(SchemeCatalog.code == code)
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Application queries
# ---------------------------------------------------------------------------


async def create_application(
    db: AsyncSession,
    *,
    application_number: str,
    scheme_id: UUID,
    farmer_id: UUID,
    submitted_data: dict[str, Any],
    eligibility_result: dict[str, Any] | None = None,
) -> SchemeApplication:
    """Create a new scheme application (status=draft)."""
    app = SchemeApplication(
        application_number=application_number,
        scheme_id=scheme_id,
        farmer_id=farmer_id,
        submitted_data=submitted_data,
        eligibility_result=eligibility_result,
        status=ApplicationStatus.DRAFT,
    )
    db.add(app)
    await db.flush()
    await db.refresh(app)
    return app


async def get_application_by_id(
    db: AsyncSession, app_id: UUID
) -> dict[str, Any] | None:
    """Get an application by ID with scheme info joined."""
    query = text("""
        SELECT a.*, s.code as scheme_code, s.name as scheme_name
        FROM schemes.scheme_applications a
        LEFT JOIN schemes.scheme_catalog s ON s.id = a.scheme_id
        WHERE a.id = :app_id
    """)
    result = await db.execute(query, {"app_id": app_id})
    row = result.fetchone()
    if not row:
        return None
    return _row_to_application_dict(row)


async def list_applications_by_farmer(
    db: AsyncSession,
    farmer_id: UUID,
    *,
    status: ApplicationStatus | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    """List a farmer's scheme applications."""
    count_query = (
        select(func.count(SchemeApplication.id))
        .where(SchemeApplication.farmer_id == farmer_id)
    )
    if status:
        count_query = count_query.where(SchemeApplication.status == status)
    total = (await db.execute(count_query)).scalar_one()

    offset = (page - 1) * page_size
    query = text("""
        SELECT a.*, s.code as scheme_code, s.name as scheme_name
        FROM schemes.scheme_applications a
        LEFT JOIN schemes.scheme_catalog s ON s.id = a.scheme_id
        WHERE a.farmer_id = :farmer_id
        ORDER BY a.created_at DESC
        LIMIT :limit OFFSET :offset
    """)
    params: dict[str, Any] = {"farmer_id": farmer_id, "limit": page_size, "offset": offset}
    if status:
        query = text(str(query).replace(
            "WHERE a.farmer_id = :farmer_id",
            "WHERE a.farmer_id = :farmer_id AND a.status = :status",
        ))
        params["status"] = status.value

    result = await db.execute(query, params)
    apps = [_row_to_application_dict(row) for row in result.fetchall()]
    return apps, total


async def find_existing_application(
    db: AsyncSession,
    scheme_id: UUID,
    farmer_id: UUID,
) -> SchemeApplication | None:
    """Check if farmer has an existing non-withdrawn application for this scheme."""
    result = await db.execute(
        select(SchemeApplication)
        .where(
            and_(
                SchemeApplication.scheme_id == scheme_id,
                SchemeApplication.farmer_id == farmer_id,
                SchemeApplication.status != ApplicationStatus.WITHDRAWN.value,
            )
        )
        .order_by(desc(SchemeApplication.created_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def submit_application(
    db: AsyncSession,
    app_id: UUID,
    submitted_data: dict[str, Any],
    eligibility_result: dict[str, Any],
    submitted_documents: list[str] | None = None,
) -> dict[str, Any] | None:
    """Submit a draft application for review."""
    now = datetime.now(timezone.utc)
    await db.execute(
        update(SchemeApplication)
        .where(SchemeApplication.id == app_id)
        .values(
            status=ApplicationStatus.SUBMITTED.value,
            submitted_data=submitted_data,
            eligibility_result=eligibility_result,
            submitted_documents=submitted_documents,
            submitted_at=now,
            updated_at=now,
        )
    )
    await db.flush()
    return await get_application_by_id(db, app_id)


async def withdraw_application(
    db: AsyncSession, app_id: UUID
) -> dict[str, Any] | None:
    """Farmer withdraws an application."""
    await db.execute(
        update(SchemeApplication)
        .where(SchemeApplication.id == app_id)
        .values(
            status=ApplicationStatus.WITHDRAWN.value,
            updated_at=datetime.now(timezone.utc),
        )
    )
    await db.flush()
    return await get_application_by_id(db, app_id)


async def officer_review_application(
    db: AsyncSession,
    app_id: UUID,
    officer_id: UUID,
    action: str,
    review_notes: str | None = None,
    rejection_reason: str | None = None,
    benefit_reference: str | None = None,
) -> dict[str, Any] | None:
    """Officer reviews a scheme application."""
    now = datetime.now(timezone.utc)
    new_status = {
        "approve": ApplicationStatus.APPROVED,
        "reject": ApplicationStatus.REJECTED,
        "request_resubmission": ApplicationStatus.RESUBMISSION_REQUESTED,
        "disburse": ApplicationStatus.BENEFIT_DISBURSED,
    }.get(action)

    if not new_status:
        return None

    update_values: dict[str, Any] = {
        "status": new_status.value,
        "reviewed_by": officer_id,
        "reviewed_at": now,
        "updated_at": now,
    }
    if review_notes:
        update_values["review_notes"] = review_notes
    if rejection_reason:
        update_values["rejection_reason"] = rejection_reason
    if benefit_reference:
        update_values["benefit_reference"] = benefit_reference
        update_values["benefit_disbursed_at"] = now

    await db.execute(
        update(SchemeApplication)
        .where(SchemeApplication.id == app_id)
        .values(**update_values)
    )
    await db.flush()
    return await get_application_by_id(db, app_id)


async def list_applications_for_review(
    db: AsyncSession,
    *,
    status: ApplicationStatus | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    """List applications for officer review."""
    base_filter = SchemeApplication.status.in_([
        ApplicationStatus.SUBMITTED.value,
        ApplicationStatus.UNDER_REVIEW.value,
        ApplicationStatus.RESUBMISSION_REQUESTED.value,
    ])

    count_query = select(func.count(SchemeApplication.id)).where(base_filter)
    if status:
        count_query = count_query.where(SchemeApplication.status == status)
    total = (await db.execute(count_query)).scalar_one()

    offset = (page - 1) * page_size
    query = text("""
        SELECT a.*, s.code as scheme_code, s.name as scheme_name,
               u.full_name as farmer_name, u.phone as farmer_phone
        FROM schemes.scheme_applications a
        LEFT JOIN schemes.scheme_catalog s ON s.id = a.scheme_id
        LEFT JOIN identity.users u ON u.id = a.farmer_id
        WHERE a.status IN ('submitted', 'under_review', 'resubmission_requested')
        ORDER BY a.submitted_at ASC
        LIMIT :limit OFFSET :offset
    """)
    result = await db.execute(query, {"limit": page_size, "offset": offset})
    apps = [_row_to_application_dict(row) for row in result.fetchall()]
    return apps, total


async def get_farmer_scheme_stats(
    db: AsyncSession, farmer_id: UUID
) -> dict[str, Any]:
    """Get scheme application stats for a farmer."""
    query = text("""
        SELECT
            COUNT(*) as total_applications,
            COUNT(*) FILTER (WHERE status IN ('draft', 'submitted', 'under_review', 'resubmission_requested')) as pending_applications,
            COUNT(*) FILTER (WHERE status IN ('approved', 'benefit_disbursed')) as approved_applications
        FROM schemes.scheme_applications
        WHERE farmer_id = :farmer_id
    """)
    result = await db.execute(query, {"farmer_id": farmer_id})
    row = result.fetchone()

    # Count total available schemes
    schemes_count = (await db.execute(
        select(func.count(SchemeCatalog.id)).where(SchemeCatalog.is_active == True)
    )).scalar_one()

    return {
        "total_schemes_available": schemes_count,
        "eligible_schemes": 0,  # Computed by service after eligibility check
        "total_applications": row[0] or 0,
        "pending_applications": row[1] or 0,
        "approved_applications": row[2] or 0,
    }


# ---------------------------------------------------------------------------
# Row mapper
# ---------------------------------------------------------------------------


from sqlalchemy import or_  # noqa: E402


def _row_to_application_dict(row: Any) -> dict[str, Any]:
    """Convert a row to an application dict."""
    import json

    submitted_data = row.submitted_data
    if isinstance(submitted_data, str):
        try:
            submitted_data = json.loads(submitted_data)
        except Exception:
            submitted_data = {}

    eligibility_result = row.eligibility_result
    if isinstance(eligibility_result, str):
        try:
            eligibility_result = json.loads(eligibility_result)
        except Exception:
            eligibility_result = None

    submitted_documents = row.submitted_documents
    if isinstance(submitted_documents, str):
        try:
            submitted_documents = json.loads(submitted_documents)
        except Exception:
            submitted_documents = None

    return {
        "id": row.id,
        "application_number": row.application_number,
        "scheme_id": row.scheme_id,
        "farmer_id": row.farmer_id,
        "status": row.status,
        "submitted_data": submitted_data,
        "eligibility_result": eligibility_result,
        "submitted_documents": submitted_documents,
        "reviewed_by": row.reviewed_by,
        "reviewed_at": row.reviewed_at,
        "review_notes": row.review_notes,
        "rejection_reason": row.rejection_reason,
        "benefit_disbursed_at": row.benefit_disbursed_at,
        "benefit_reference": row.benefit_reference,
        "submitted_at": row.submitted_at,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "scheme_code": getattr(row, "scheme_code", None),
        "scheme_name": getattr(row, "scheme_name", None),
        "farmer_name": getattr(row, "farmer_name", None),
        "farmer_phone": getattr(row, "farmer_phone", None),
    }
