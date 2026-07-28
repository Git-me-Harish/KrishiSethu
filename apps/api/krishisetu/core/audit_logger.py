"""Structured audit logging for security-sensitive operations.

The audit log is the authoritative record of WHO did WHAT to WHICH record,
WHEN, and FROM WHERE. It is distinct from the application log (structlog)
in three ways:
1. Audit log entries are stored in the database (audit.audit_logs table),
   not just streamed to stdout — they must survive server restarts.
2. Audit log entries follow a strict schema with required fields; the table
   is append-only (no UPDATE, no DELETE without admin escalation).
3. Audit log entries carry enough context to reconstruct the action for
   regulatory / DPDP compliance audits.

What gets audited:
- Authentication: login success, login failure, logout, token refresh,
  password change, OTP send/verify
- Authorization: permission denied, role escalation, role change
- PII access: any read of Aadhaar, bank account, GSTIN (data-access audit)
- PII modification: any update to identity, farmer profile, KYC
- Consent: grant, withdraw, scope change
- Data subject rights: access request, correction, erasure, export
- Marketplace: order create/cancel, payment capture/refund, escrow release
- Insurance: policy purchase, claim file/approve/reject
- Admin actions: user role change, content moderation, scheme approval

Audit events are written SYNCHRONOUSLY in the request flow (not via Celery)
because they are critical for security monitoring and must be persisted even
if the request fails. For high-volume operations (e.g. paginated list reads),
use audit_log_async() which posts to a background queue.

FIX (T3): audit_log() no longer calls db.commit(). It now only stages the
INSERT via db.execute() and lets the caller's transaction (managed by
get_db()'s session-per-request commit) persist it. This fixes a silent-
data-loss bug where, if audit_log()'s own commit failed, it would rollback
the caller's pending writes (consent grants, DSR filings, grievances) —
the API would return 201 success but the rows would never be persisted.

For the rare case where you WANT the audit entry to commit independently
(e.g. in a background task with no caller transaction), use the new
audit_log_independent() function which preserves the old commit-then-
rollback-on-failure behavior.

Usage:
    from krishisetu.core.audit_logger import audit_log, AuditAction

    await audit_log(
        db,
        action=AuditAction.PII_ACCESSED,
        actor_id=current_user.id,
        actor_role=current_user.role,
        resource_type="farmer_profile",
        resource_id=profile_id,
        request=request,  # to capture IP, UA, request_id
        details={"fields": ["aadhaar_hash", "bank_account_encrypted"]},
    )
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from krishisetu.core.logging import get_logger

logger = get_logger(__name__)


class AuditAction(str, Enum):
    """Enumeration of auditable actions.

    The string values are stored in the DB; renaming a value requires a
    migration because old entries reference the old string.
    """

    # Authentication
    LOGIN_SUCCESS = "login.success"
    LOGIN_FAILED = "login.failed"
    LOGOUT = "logout"
    TOKEN_REFRESHED = "token.refreshed"
    PASSWORD_CHANGED = "password.changed"
    OTP_SENT = "otp.sent"
    OTP_VERIFIED = "otp.verified"
    ACCOUNT_LOCKED = "account.locked"
    ACCOUNT_UNLOCKED = "account.unlocked"

    # Authorization
    PERMISSION_DENIED = "authz.denied"
    ROLE_CHANGED = "role.changed"

    # PII access & modification
    PII_ACCESSED = "pii.accessed"
    PII_UPDATED = "pii.updated"
    AADHAAR_EKYC_INITIATED = "aadhaar.ekyc.initiated"
    AADHAAR_EKYC_COMPLETED = "aadhaar.ekyc.completed"

    # Consent (DPDP)
    CONSENT_GRANTED = "consent.granted"
    CONSENT_WITHDRAWN = "consent.withdrawn"

    # Data Subject Rights (DPDP)
    DSR_ACCESS_REQUESTED = "dsr.access.requested"
    DSR_ACCESS_FULFILLED = "dsr.access.fulfilled"
    DSR_CORRECTION_REQUESTED = "dsr.correction.requested"
    DSR_CORRECTION_APPLIED = "dsr.correction.applied"
    DSR_ERASURE_REQUESTED = "dsr.erasure.requested"
    DSR_ERASURE_APPLIED = "dsr.erasure.applied"
    DSR_PORTABILITY_REQUESTED = "dsr.portability.requested"
    DSR_PORTABILITY_FULFILLED = "dsr.portability.fulfilled"
    GRIEVANCE_FILED = "grievance.filed"
    GRIEVANCE_RESOLVED = "grievance.resolved"

    # Farmer domain
    PLOT_CREATED = "plot.created"
    PLOT_UPDATED = "plot.updated"
    PLOT_VERIFIED = "plot.verified"
    PLOT_DELETED = "plot.deleted"

    # Disease domain
    DISEASE_REPORT_SUBMITTED = "disease.report.submitted"
    DISEASE_REPORT_REVIEWED = "disease.report.reviewed"

    # Insurance domain
    INSURANCE_POLICY_PURCHASED = "insurance.policy.purchased"
    INSURANCE_CLAIM_FILED = "insurance.claim.filed"
    INSURANCE_CLAIM_APPROVED = "insurance.claim.approved"
    INSURANCE_CLAIM_REJECTED = "insurance.claim.rejected"

    # Marketplace & payments
    ORDER_CREATED = "order.created"
    ORDER_CANCELLED = "order.cancelled"
    PAYMENT_INITIATED = "payment.initiated"
    PAYMENT_CAPTURED = "payment.captured"
    PAYMENT_REFUNDED = "payment.refunded"
    ESCROW_RELEASED = "escrow.released"

    # Admin actions
    ADMIN_USER_DEACTIVATED = "admin.user.deactivated"
    ADMIN_USER_REACTIVATED = "admin.user.reactivated"
    ADMIN_CONTENT_REMOVED = "admin.content.removed"
    ADMIN_SCHEME_APPROVED = "admin.scheme.approved"

    # Security events
    SECURITY_CSRF_VIOLATION = "security.csrf.violation"
    SECURITY_RATE_LIMIT_EXCEEDED = "security.rate_limit.exceeded"
    SECURITY_SUSPICIOUS_INPUT = "security.suspicious_input"
    SECURITY_INTEGRATION_FAILURE = "security.integration_failure"


class AuditOutcome(str, Enum):
    """Outcome of the audited action."""

    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"
    ERROR = "error"


# Internal: build + stage the INSERT (no commit)
async def _stage_audit_insert(
    db: AsyncSession,
    *,
    audit_id: UUID,
    action: AuditAction,
    actor_id: UUID | str | None,
    actor_role: str | None,
    resource_type: str | None,
    resource_id: UUID | str | None,
    outcome: AuditOutcome,
    safe_details: dict[str, Any],
    ip_address: str | None,
    user_agent: str | None,
    request_id: str | None,
) -> None:
    """Stage the audit INSERT into the session without committing.

    Called by both audit_log() and audit_log_independent(). The caller
    decides whether to commit (audit_log_independent) or let the
    session-per-request transaction handle it (audit_log).
    """
    insert_sql = text("""
        INSERT INTO audit.audit_logs
            (id, action, outcome, actor_id, actor_role,
             resource_type, resource_id, details,
             ip_address, user_agent, request_id, occurred_at)
        VALUES
            (:id, :action, :outcome, :actor_id, :actor_role,
             :resource_type, :resource_id, CAST(:details AS JSONB),
             :ip_address, :user_agent, :request_id, :occurred_at)
    """)

    params = {
        "id": str(audit_id),
        "action": action.value,
        "outcome": outcome.value,
        "actor_id": str(actor_id) if actor_id is not None else None,
        "actor_role": actor_role,
        "resource_type": resource_type,
        "resource_id": str(resource_id) if resource_id is not None else None,
        "details": json.dumps(safe_details, default=str),
        "ip_address": ip_address,
        "user_agent": user_agent,
        "request_id": request_id,
        "occurred_at": datetime.now(timezone.utc),
    }

    await db.execute(insert_sql, params)


def _sanitize_details(details: dict[str, Any] | None) -> dict[str, Any]:
    """Sanitize the details dict — never allow non-JSON-serializable values."""
    safe: dict[str, Any] = {}
    if not details:
        return safe
    for k, v in details.items():
        if isinstance(v, (str, int, float, bool, type(None), list, dict)):
            safe[k] = v
        else:
            try:
                safe[k] = str(v)
            except Exception:
                safe[k] = "<unrepresentable>"
    return safe


def _extract_request_context(
    request: Request | None,
    ip_address: str | None,
    user_agent: str | None,
    request_id: str | None,
) -> tuple[str | None, str | None, str | None]:
    """Extract IP, UA, request_id from the FastAPI Request if not explicitly given."""
    if request is None:
        return ip_address, user_agent, request_id
    if ip_address is None:
        ip_address = (
            request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            or (request.client.host if request.client else None)
        )
    if user_agent is None:
        user_agent = request.headers.get("user-agent")
    if request_id is None:
        request_id = getattr(request.state, "request_id", None)
    return ip_address, user_agent, request_id


# Public: audit_log() — stages the INSERT, does NOT commit
async def audit_log(
    db: AsyncSession,
    *,
    action: AuditAction,
    actor_id: UUID | str | None,
    actor_role: str | None = None,
    resource_type: str | None = None,
    resource_id: UUID | str | None = None,
    outcome: AuditOutcome = AuditOutcome.SUCCESS,
    details: dict[str, Any] | None = None,
    request: Request | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> UUID:
    """Write an audit log entry WITHOUT committing.

    Args:
        db: async DB session — the INSERT is staged here and committed by
            the caller's transaction (typically get_db()'s session-per-
            request commit). This is the correct behavior because:
            - It keeps the audit entry in the same transaction as the
              business operation it records → atomicity.
            - It avoids the old silent-data-loss bug where audit_log()'s
              own commit-then-rollback-on-failure would roll back the
              caller's pending writes (consent grants, DSRs, grievances).
        action: what happened (AuditAction enum value)
        actor_id: who did it (user ID, or None for system/anonymous)
        actor_role: role of the actor at time of action
        resource_type: what kind of resource was affected
        resource_id: ID of the affected resource
        outcome: success/failure/denied/error
        details: additional structured context (JSONB in DB)
        request: FastAPI Request (used to extract IP, UA, request_id)
        ip_address: explicit IP (overrides request extraction)
        user_agent: explicit UA (overrides request extraction)
        request_id: explicit request_id (overrides request extraction)

    Returns:
        The UUID of the staged audit log entry.

    Notes:
        - This function NEVER raises — audit logging failures are swallowed
          and logged via structlog so the original operation can complete.
          Losing an audit entry is bad but failing the user's request
          because the audit table is full is worse. Monitor the
          "audit.write_failed" log events to detect audit table issues.
        - Because we no longer commit here, a failure to STAGE the INSERT
          (e.g. DB connection lost) is logged but does NOT roll back the
          caller's transaction. The caller's commit will still succeed
          with their business data — only the audit entry is lost.
        - The `details` dict is JSON-serialized; do NOT put binary data or
          non-JSON-serializable objects in it.
        - PII fields should be referenced by name in details, never by value.
          E.g. {"fields_read": ["aadhaar_hash"]} — NOT {"aadhaar": "1234..."}.
    """
    audit_id = uuid4()
    ip_address, user_agent, request_id = _extract_request_context(
        request, ip_address, user_agent, request_id
    )
    safe_details = _sanitize_details(details)

    try:
        await _stage_audit_insert(
            db,
            audit_id=audit_id,
            action=action,
            actor_id=actor_id,
            actor_role=actor_role,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=outcome,
            safe_details=safe_details,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
        )
    except Exception as e:
        # CRITICAL: never let audit failure break the user's request.
        # Log loudly so monitoring catches it.
        # NOTE: we do NOT rollback here — the caller's transaction should
        # still be allowed to commit its business data. A failed audit
        # INSERT only affects the audit row, not the business rows.
        logger.error(
            "audit.write_failed",
            action=action.value,
            actor_id=str(actor_id) if actor_id is not None else None,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            error=str(e),
            error_type=type(e).__name__,
        )

    return audit_id


# Public: audit_log_independent() — stages + commits in its own transaction
async def audit_log_independent(
    db: AsyncSession,
    *,
    action: AuditAction,
    actor_id: UUID | str | None,
    actor_role: str | None = None,
    resource_type: str | None = None,
    resource_id: UUID | str | None = None,
    outcome: AuditOutcome = AuditOutcome.SUCCESS,
    details: dict[str, Any] | None = None,
    request: Request | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> UUID:
    """Write an audit log entry and commit it in its own transaction.

    Use this variant when:
    - You are in a background task (Celery) with no caller transaction
    - You want the audit entry to persist even if a later operation fails
    - You are auditing a security event (CSRF violation, rate limit) that
      must be recorded regardless of what happens next

    DO NOT use this in normal request flow — there, use audit_log() so the
    audit entry commits atomically with the business operation.

    On commit failure, logs the error and rolls back the session so it's
    not in a broken state for subsequent operations.
    """
    audit_id = uuid4()
    ip_address, user_agent, request_id = _extract_request_context(
        request, ip_address, user_agent, request_id
    )
    safe_details = _sanitize_details(details)

    try:
        await _stage_audit_insert(
            db,
            audit_id=audit_id,
            action=action,
            actor_id=actor_id,
            actor_role=actor_role,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=outcome,
            safe_details=safe_details,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
        )
        await db.commit()
    except Exception as e:
        logger.error(
            "audit.write_failed",
            action=action.value,
            actor_id=str(actor_id) if actor_id is not None else None,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            error=str(e),
            error_type=type(e).__name__,
        )
        try:
            await db.rollback()
        except Exception:
            pass

    return audit_id


async def audit_log_pii_access(
    db: AsyncSession,
    *,
    actor_id: UUID | str,
    actor_role: str | None,
    resource_type: str,
    resource_id: UUID | str,
    fields_accessed: list[str],
    purpose: str,
    request: Request | None = None,
) -> None:
    """Convenience wrapper for PII access audits (most common case).

    Args:
        fields_accessed: list of field names accessed (e.g. ["aadhaar_hash",
            "bank_account_encrypted"]) — never the actual values
        purpose: business reason for the access (e.g. "claim_review",
            "kyc_verification")
    """
    await audit_log(
        db,
        action=AuditAction.PII_ACCESSED,
        actor_id=actor_id,
        actor_role=actor_role,
        resource_type=resource_type,
        resource_id=resource_id,
        details={
            "fields": fields_accessed,
            "purpose": purpose,
        },
        request=request,
    )


__all__ = [
    "AuditAction",
    "AuditOutcome",
    "audit_log",
    "audit_log_independent",
    "audit_log_pii_access",
]