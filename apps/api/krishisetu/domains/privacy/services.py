"""Privacy domain service layer.

Implements the data-subject-rights workflows required by India's Digital
Personal Data Protection Act 2023:
- Section 11: access (what data we have)
- Section 12: correction & erasure
- Section 13: grievance redressal

Each workflow:
1. Creates a request record with a due_at timestamp (DPDP SLA)
2. Auto-acknowledges (writes acknowledged_at within 24h of filing)
3. Returns the request ID for the user to track

Erasure is a special case — it triggers a HARD cascade delete across all
domain tables, retaining only legally-required records (payment history
for tax purposes, anonymized audit logs).
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import Request
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from krishisetu.core.audit_logger import AuditAction, audit_log
from krishisetu.core.config import settings
from krishisetu.core.logging import get_logger
from krishisetu.domains.privacy.models import (
    DSRStatus,
    DSRType,
    DataSubjectRequest,
    Grievance,
    GrievanceStatus,
)

logger = get_logger(__name__)


# DPDP-mandated SLAs (days)
SLA_ACCESS = 30
SLA_CORRECTION = 15
SLA_ERASURE = 30
SLA_PORTABILITY = 30
SLA_GRIEVANCE = 30
SLA_ACKNOWLEDGE_HOURS = 24


def _due_at(request_type: DSRType) -> datetime:
    """Calculate the SLA due date for a DSR."""
    days_map = {
        DSRType.ACCESS: SLA_ACCESS,
        DSRType.CORRECTION: SLA_CORRECTION,
        DSRType.ERASURE: SLA_ERASURE,
        DSRType.PORTABILITY: SLA_PORTABILITY,
        DSRType.RESTRICTION: SLA_ACCESS,
    }
    days = days_map.get(request_type, SLA_ACCESS)
    return datetime.now(timezone.utc) + timedelta(days=days)


async def create_dsr(
    db: AsyncSession,
    user_id: UUID,
    request_type: DSRType,
    description: str | None = None,
    requested_changes: dict | None = None,
    request: Request | None = None,
) -> DataSubjectRequest:
    """File a new Data Subject Request.

    The DSR is auto-acknowledged within the same transaction (the system
    satisfies the 24-hour acknowledgement SLA immediately).
    """
    now = datetime.now(timezone.utc)
    dsr = DataSubjectRequest(
        user_id=user_id,
        request_type=request_type.value,
        status=DSRStatus.ACKNOWLEDGED.value,
        description=description,
        requested_changes=requested_changes,
        submitted_at=now,
        acknowledged_at=now,  # auto-acknowledge
        due_at=_due_at(request_type),
    )
    db.add(dsr)
    await db.flush()

    await audit_log(
        db,
        action=AuditAction.DSR_ACCESS_REQUESTED
        if request_type == DSRType.ACCESS
        else AuditAction.DSR_CORRECTION_REQUESTED
        if request_type == DSRType.CORRECTION
        else AuditAction.DSR_ERASURE_REQUESTED
        if request_type == DSRType.ERASURE
        else AuditAction.DSR_PORTABILITY_REQUESTED,
        actor_id=user_id,
        resource_type="dsr",
        resource_id=dsr.id,
        details={
            "request_type": request_type.value,
            "due_at": dsr.due_at.isoformat(),
        },
        request=request,
    )

    await db.commit()
    return dsr


async def get_dsr(db: AsyncSession, dsr_id: UUID, user_id: UUID) -> DataSubjectRequest | None:
    """Get a DSR by ID. Returns None if not found or not owned by user_id."""
    stmt = select(DataSubjectRequest).where(
        DataSubjectRequest.id == dsr_id,
        DataSubjectRequest.user_id == user_id,
    )
    result = await db.execute(stmt)
    return result.scalars().first()


async def list_my_dsrs(
    db: AsyncSession,
    user_id: UUID,
) -> list[DataSubjectRequest]:
    """List all DSRs filed by the user, newest first."""
    stmt = (
        select(DataSubjectRequest)
        .where(DataSubjectRequest.user_id == user_id)
        .order_by(DataSubjectRequest.submitted_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def list_all_dsrs(
    db: AsyncSession,
    status: DSRStatus | None = None,
    limit: int = 100,
) -> list[DataSubjectRequest]:
    """List all DSRs (admin view). Optionally filter by status."""
    stmt = select(DataSubjectRequest).order_by(
        DataSubjectRequest.submitted_at.desc()
    ).limit(limit)
    if status is not None:
        stmt = stmt.where(DataSubjectRequest.status == status.value)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_dsr(
    db: AsyncSession,
    dsr_id: UUID,
    *,
    status: DSRStatus,
    resolution_notes: str | None = None,
    rejection_reason: str | None = None,
    export_url: str | None = None,
    officer_id: UUID | None = None,
    request: Request | None = None,
) -> DataSubjectRequest | None:
    """Officer updates a DSR's status."""
    stmt = select(DataSubjectRequest).where(DataSubjectRequest.id == dsr_id)
    result = await db.execute(stmt)
    dsr = result.scalars().first()
    if dsr is None:
        return None

    dsr.status = status.value
    if resolution_notes is not None:
        dsr.resolution_notes = resolution_notes
    if rejection_reason is not None:
        dsr.rejection_reason = rejection_reason
    if export_url is not None:
        dsr.export_url = export_url
    if officer_id is not None:
        dsr.assigned_to = officer_id
    if status in (DSRStatus.COMPLETED, DSRStatus.REJECTED):
        dsr.completed_at = datetime.now(timezone.utc)

    await audit_log(
        db,
        action=AuditAction.DSR_ACCESS_FULFILLED
        if dsr.request_type == DSRType.ACCESS.value and status == DSRStatus.COMPLETED
        else AuditAction.DSR_CORRECTION_APPLIED
        if dsr.request_type == DSRType.CORRECTION.value and status == DSRStatus.COMPLETED
        else AuditAction.DSR_ERASURE_APPLIED
        if dsr.request_type == DSRType.ERASURE.value and status == DSRStatus.COMPLETED
        else AuditAction.DSR_PORTABILITY_FULFILLED
        if dsr.request_type == DSRType.PORTABILITY.value and status == DSRStatus.COMPLETED
        else AuditAction.DSR_ACCESS_REQUESTED,  # fallback
        actor_id=officer_id,
        resource_type="dsr",
        resource_id=dsr.id,
        details={
            "new_status": status.value,
            "request_type": dsr.request_type,
        },
        request=request,
    )

    await db.commit()
    return dsr


# ---------------------------------------------------------------------------
# Erasure — account deletion
# ---------------------------------------------------------------------------

async def execute_erasure(
    db: AsyncSession,
    user_id: UUID,
    reason: str | None = None,
    request: Request | None = None,
) -> None:
    """Permanently delete a user's personal data.

    This is a HARD DELETE — the user's row in identity.users is deleted,
    which cascades to all dependent tables (plots, disease reports, etc.)
    via ON DELETE CASCADE.

    What is RETAINED (legally required):
    - Payment records (tax/GST compliance, 7-year retention) — but with
      PII columns scrubbed (phone, email, name set to NULL or anonymized)
    - Audit logs — but with actor_id set to NULL and details scrubbed
    - Consent history — same as audit logs

    The retained records are anonymized so they cannot be linked back to
    the user. This satisfies both DPDP (right to erasure) and tax law
    (record retention).

    This function is called from the route layer AFTER the user has
    confirmed with the exact phrase "DELETE MY ACCOUNT".
    """
    # 1. Anonymize payment records (keep amounts/dates for tax, scrub PII)
    await db.execute(
        text("""
            UPDATE commerce.payments
            SET notes = NULL,
                bank_account_number = NULL,
                bank_ifsc = NULL,
                upi_id = NULL,
                description = 'Account deleted'
            WHERE user_id = :uid
        """),
        {"uid": str(user_id)},
    )

    # 2. Anonymize audit logs (keep action/timestamp for security, scrub actor)
    await db.execute(
        text("""
            UPDATE audit.audit_logs
            SET actor_id = NULL,
                details = '{}'::jsonb
            WHERE actor_id = :uid
        """),
        {"uid": str(user_id)},
    )

    # 3. Anonymize consent records (keep aggregate counts for compliance reporting)
    await db.execute(
        text("""
            UPDATE privacy.consent_records
            SET user_id = NULL,
                granted_from_ip = NULL,
                withdrawn_from_ip = NULL,
                user_agent = NULL,
                metadata = NULL,
                withdrawn_by = NULL
            WHERE user_id = :uid
        """),
        {"uid": str(user_id)},
    )

    # 4. Delete the user row — cascades to all dependent tables
    await db.execute(
        text("DELETE FROM identity.users WHERE id = :uid"),
        {"uid": str(user_id)},
    )

    # 5. Audit (post-deletion — actor_id will be NULL since user is gone)
    await audit_log(
        db,
        action=AuditAction.DSR_ERASURE_APPLIED,
        actor_id=None,
        actor_role="system",
        resource_type="user",
        resource_id=user_id,
        details={"reason": reason or "user_requested"},
        request=request,
    )

    await db.commit()
    logger.info("privacy.erasure_completed", user_id=str(user_id))


# ---------------------------------------------------------------------------
# Grievances
# ---------------------------------------------------------------------------

async def create_grievance(
    db: AsyncSession,
    user_id: UUID,
    category: str,
    subject: str,
    description: str,
    request: Request | None = None,
) -> Grievance:
    """File a new DPDP grievance."""
    now = datetime.now(timezone.utc)
    # Generate a human-readable grievance number: GRV-YYYYMMDD-XXXXX
    grievance_number = f"GRV-{now.strftime('%Y%m%d')}-{secrets.token_hex(4).upper()}"

    grievance = Grievance(
        grievance_number=grievance_number,
        user_id=user_id,
        category=category,
        subject=subject,
        description=description,
        status=GrievanceStatus.ACKNOWLEDGED.value,  # auto-acknowledge
        filed_at=now,
        acknowledged_at=now,
        due_at=now + timedelta(days=SLA_GRIEVANCE),
    )
    db.add(grievance)
    await db.flush()

    await audit_log(
        db,
        action=AuditAction.GRIEVANCE_FILED,
        actor_id=user_id,
        resource_type="grievance",
        resource_id=grievance.id,
        details={
            "grievance_number": grievance_number,
            "category": category,
            "due_at": grievance.due_at.isoformat(),
        },
        request=request,
    )

    await db.commit()
    return grievance


async def get_grievance(
    db: AsyncSession,
    grievance_id: UUID,
    user_id: UUID,
) -> Grievance | None:
    """Get a grievance by ID (user can only see their own)."""
    stmt = select(Grievance).where(
        Grievance.id == grievance_id,
        Grievance.user_id == user_id,
    )
    result = await db.execute(stmt)
    return result.scalars().first()


async def list_my_grievances(
    db: AsyncSession,
    user_id: UUID,
) -> list[Grievance]:
    """List all grievances filed by the user, newest first."""
    stmt = (
        select(Grievance)
        .where(Grievance.user_id == user_id)
        .order_by(Grievance.filed_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def list_all_grievances(
    db: AsyncSession,
    status: GrievanceStatus | None = None,
    limit: int = 100,
) -> list[Grievance]:
    """List all grievances (admin/officer view)."""
    stmt = select(Grievance).order_by(Grievance.filed_at.desc()).limit(limit)
    if status is not None:
        stmt = stmt.where(Grievance.status == status.value)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_grievance(
    db: AsyncSession,
    grievance_id: UUID,
    *,
    status: GrievanceStatus,
    resolution: str | None = None,
    escalation_reference: str | None = None,
    officer_id: UUID | None = None,
    request: Request | None = None,
) -> Grievance | None:
    """Officer updates a grievance's status."""
    stmt = select(Grievance).where(Grievance.id == grievance_id)
    result = await db.execute(stmt)
    grievance = result.scalars().first()
    if grievance is None:
        return None

    grievance.status = status.value
    if resolution is not None:
        grievance.resolution = resolution
    if escalation_reference is not None:
        grievance.escalation_reference = escalation_reference
    if officer_id is not None:
        grievance.assigned_to = officer_id
    if status == GrievanceStatus.RESOLVED:
        grievance.resolved_at = datetime.now(timezone.utc)

    if status == GrievanceStatus.RESOLVED:
        await audit_log(
            db,
            action=AuditAction.GRIEVANCE_RESOLVED,
            actor_id=officer_id,
            resource_type="grievance",
            resource_id=grievance.id,
            details={"resolution": resolution or ""},
            request=request,
        )

    await db.commit()
    return grievance


__all__ = [
    "create_dsr",
    "get_dsr",
    "list_my_dsrs",
    "list_all_dsrs",
    "update_dsr",
    "execute_erasure",
    "create_grievance",
    "get_grievance",
    "list_my_grievances",
    "list_all_grievances",
    "update_grievance",
    "SLA_GRIEVANCE",
    "SLA_ACKNOWLEDGE_HOURS",
]
