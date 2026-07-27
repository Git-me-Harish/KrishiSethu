"""Consent domain service layer.

Encapsulates the consent lifecycle:
- grant(): create a new consent record, withdraw any prior grant for the
  same purpose first (so there is exactly one active grant per purpose)
- withdraw(): mark an active grant as withdrawn, with audit trail
- get_status(): return a summary of which purposes are currently granted
- list_history(): return the full history (granted + withdrawn) for audit

The service writes to BOTH the consent_records table (for state) and the
audit_logs table (for compliance audit trail).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from krishisetu.core.audit_logger import AuditAction, audit_log
from krishisetu.core.logging import get_logger
from krishisetu.domains.consent.models import (
    Consent,
    ConsentPurpose,
    ConsentStatus,
)
from krishisetu.domains.consent.schemas import (
    ConsentGrantRequest,
    ConsentStatusResponse,
    ConsentWithdrawRequest,
)

logger = get_logger(__name__)

# Current consent notice version — bump when the notice text changes.
# Users must re-consent when the version changes (DPDP requires fresh
# consent for material changes to processing).
CURRENT_NOTICE_VERSION = "2026.07.01"


async def grant_consent(
    db: AsyncSession,
    user_id: UUID,
    payload: ConsentGrantRequest,
    request: Request | None = None,
    actor_id: UUID | None = None,
) -> list[Consent]:
    """Grant consent for one or more purposes.

    For each purpose:
    1. Withdraw any existing active grant (with reason "superseded")
    2. Create a new active grant with the current notice version
    3. Write an audit log entry

    Returns the list of newly created Consent records.
    """
    actor = actor_id or user_id
    ip = (
        request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else None)
    ) if request else None
    ua = request.headers.get("user-agent") if request else None

    created: list[Consent] = []

    for purpose in payload.purposes:
        # 1. Withdraw any existing active grant for this purpose
        existing = await _get_active_consent(db, user_id, purpose)
        if existing is not None:
            existing.status = ConsentStatus.WITHDRAWN.value
            existing.withdrawn_at = datetime.now(UTC)
            existing.withdrawn_by = actor
            existing.withdrawal_reason = "superseded by new grant"
            existing.withdrawn_from_ip = ip
            await db.flush()

        # 2. Create new grant
        consent = Consent(
            user_id=user_id,
            purpose=purpose.value,
            status=ConsentStatus.GRANTED.value,
            notice_version=payload.notice_version or CURRENT_NOTICE_VERSION,
            notice_text_hash=payload.notice_text_hash,
            granted_from_ip=ip,
            user_agent=ua,
            metadata_={"language": payload.language},
        )
        db.add(consent)
        await db.flush()
        created.append(consent)

        # 3. Audit
        await audit_log(
            db,
            action=AuditAction.CONSENT_GRANTED,
            actor_id=actor,
            actor_role=None,  # role filled by route layer if available
            resource_type="consent",
            resource_id=consent.id,
            details={
                "purpose": purpose.value,
                "notice_version": consent.notice_version,
            },
            request=request,
        )

    await db.commit()
    return created


async def withdraw_consent(
    db: AsyncSession,
    user_id: UUID,
    payload: ConsentWithdrawRequest,
    request: Request | None = None,
    actor_id: UUID | None = None,
) -> list[Consent]:
    """Withdraw consent for one or more purposes.

    Marks the active grant as withdrawn. Does NOT delete the record — the
    history must be preserved for DPDP audit. Side effects of withdrawal
    (e.g. disabling ML features that depend on the consent) are handled by
    downstream services that check consent state.
    """
    actor = actor_id or user_id
    ip = (
        request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        or (request.client.host if request.client else None)
    ) if request else None

    withdrawn: list[Consent] = []

    for purpose in payload.purposes:
        active = await _get_active_consent(db, user_id, purpose)
        if active is None:
            # No active consent to withdraw — skip silently (idempotent)
            continue
        active.status = ConsentStatus.WITHDRAWN.value
        active.withdrawn_at = datetime.now(UTC)
        active.withdrawn_by = actor
        active.withdrawal_reason = payload.reason
        active.withdrawn_from_ip = ip
        await db.flush()
        withdrawn.append(active)

        await audit_log(
            db,
            action=AuditAction.CONSENT_WITHDRAWN,
            actor_id=actor,
            resource_type="consent",
            resource_id=active.id,
            details={
                "purpose": purpose.value,
                "reason": payload.reason,
            },
            request=request,
        )

    await db.commit()
    return withdrawn


async def get_consent_status(
    db: AsyncSession,
    user_id: UUID,
) -> ConsentStatusResponse:
    """Return the current consent state for a user across all purposes."""
    # All active (granted) purposes
    stmt_granted = select(Consent.purpose).where(
        Consent.user_id == user_id,
        Consent.status == ConsentStatus.GRANTED.value,
    )
    result = await db.execute(stmt_granted)
    granted_purposes = {ConsentPurpose(p) for p in result.scalars().all()}

    # All withdrawn purposes (any record exists but currently withdrawn)
    stmt_withdrawn = select(Consent.purpose).where(
        Consent.user_id == user_id,
        Consent.status == ConsentStatus.WITHDRAWN.value,
    )
    result = await db.execute(stmt_withdrawn)
    withdrawn_purposes = {ConsentPurpose(p) for p in result.scalars().all()}

    all_purposes = set(ConsentPurpose)
    not_asked = all_purposes - granted_purposes - withdrawn_purposes

    return ConsentStatusResponse(
        granted=sorted(granted_purposes, key=lambda p: p.value),
        withdrawn=sorted(withdrawn_purposes - granted_purposes, key=lambda p: p.value),
        not_yet_asked=sorted(not_asked, key=lambda p: p.value),
    )


async def list_consent_history(
    db: AsyncSession,
    user_id: UUID,
) -> list[Consent]:
    """Return full consent history (granted + withdrawn), newest first."""
    stmt = (
        select(Consent)
        .where(Consent.user_id == user_id)
        .order_by(Consent.granted_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def has_active_consent(
    db: AsyncSession,
    user_id: UUID,
    purpose: ConsentPurpose,
) -> bool:
    """Check whether the user has an active grant for a specific purpose.

    Used by other domains as a hard gate before processing personal data:
        if not await has_active_consent(db, user.id, ConsentPurpose.NDVI_MONITORING):
            raise AuthorizationError("Consent required for NDVI monitoring")
    """
    active = await _get_active_consent(db, user_id, purpose)
    return active is not None


async def _get_active_consent(
    db: AsyncSession,
    user_id: UUID,
    purpose: ConsentPurpose,
) -> Consent | None:
    """Return the active (granted) consent for a user+purpose, or None."""
    stmt = select(Consent).where(
        Consent.user_id == user_id,
        Consent.purpose == purpose.value,
        Consent.status == ConsentStatus.GRANTED.value,
    )
    result = await db.execute(stmt)
    return result.scalars().first()


__all__ = [
    "CURRENT_NOTICE_VERSION",
    "get_consent_status",
    "grant_consent",
    "has_active_consent",
    "list_consent_history",
    "withdraw_consent",
]
