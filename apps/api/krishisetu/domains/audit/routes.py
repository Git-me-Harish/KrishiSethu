"""Audit domain — admin query API for audit logs.

Audit logs are stored in audit.audit_logs (written by core.audit_logger).
This module provides read-only query endpoints for:
- Admin incident response (search by actor, resource, action, time range)
- DPDP compliance reporting (who accessed whose PII, when, why)
- Security monitoring (failed logins, permission denials, CSRF violations)

All endpoints require the admin:audit:read permission (admin role only).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from krishisetu.core.database import get_db
from krishisetu.core.dependencies import CurrentUser, require_permissions
from krishisetu.core.logging import get_logger
from krishisetu.domains.identity.permissions import PERM_ADMIN_AUDIT_LOG_READ

logger = get_logger(__name__)

router = APIRouter(prefix="/audit", tags=["audit"])


# Common dependency: requires admin audit-log read permission
_audit_admin = Depends(require_permissions(PERM_ADMIN_AUDIT_LOG_READ))


@router.get("/logs")
async def search_audit_logs(
    _: Annotated[CurrentUser, _audit_admin],
    db: Annotated[AsyncSession, Depends(get_db)],
    actor_id: Annotated[UUID | None, Query()] = None,
    action: Annotated[str | None, Query()] = None,
    resource_type: Annotated[str | None, Query()] = None,
    resource_id: Annotated[UUID | None, Query()] = None,
    start: Annotated[datetime | None, Query()] = None,
    end: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    """Search audit logs with filters.

    All filters are optional; combining multiple filters is AND logic.
    Results are sorted by occurred_at DESC (newest first).
    """
    conditions: list[str] = []
    params: dict = {"limit": limit, "offset": offset}

    if actor_id is not None:
        conditions.append("actor_id = :actor_id")
        params["actor_id"] = str(actor_id)
    if action is not None:
        conditions.append("action = :action")
        params["action"] = action
    if resource_type is not None:
        conditions.append("resource_type = :resource_type")
        params["resource_type"] = resource_type
    if resource_id is not None:
        conditions.append("resource_id = :resource_id")
        params["resource_id"] = str(resource_id)
    if start is not None:
        conditions.append("occurred_at >= :start")
        params["start"] = start
    if end is not None:
        conditions.append("occurred_at <= :end")
        params["end"] = end

    where_clause = (" WHERE " + " AND ".join(conditions)) if conditions else ""

    # where_clause only concatenates fixed "column = :param" fragments from the
    # conditions list above; all actual values are bound via params (no
    # user-controlled string ever reaches the SQL text itself).
    sql = text(f"""
        SELECT id, action, outcome, actor_id, actor_role,
               resource_type, resource_id, details,
               ip_address, user_agent, request_id, occurred_at
        FROM audit.audit_logs{where_clause}
        ORDER BY occurred_at DESC
        LIMIT :limit OFFSET :offset
    """)

    count_sql = text(f"SELECT COUNT(*) FROM audit.audit_logs{where_clause}")  # noqa: S608

    result = await db.execute(sql, params)
    rows = result.mappings().all()

    count_result = await db.execute(count_sql, params)
    total = count_result.scalar() or 0

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "logs": [_row_to_dict(row) for row in rows],
    }


@router.get("/logs/{log_id}")
async def get_audit_log(
    log_id: Annotated[UUID, Path()],
    _: Annotated[CurrentUser, _audit_admin],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Get a single audit log entry by ID."""
    sql = text("""
        SELECT id, action, outcome, actor_id, actor_role,
               resource_type, resource_id, details,
               ip_address, user_agent, request_id, occurred_at
        FROM audit.audit_logs
        WHERE id = :id
    """)
    result = await db.execute(sql, {"id": str(log_id)})
    row = result.mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Audit log not found")
    return _row_to_dict(row)


@router.get("/stats")
async def audit_stats(
    _: Annotated[CurrentUser, _audit_admin],
    db: Annotated[AsyncSession, Depends(get_db)],
    hours: Annotated[int, Query(ge=1, le=720)] = 24,
) -> dict:
    """Get aggregate audit statistics for the last N hours.

    Used by the admin dashboard for security monitoring:
    - Total events grouped by action and outcome
    - Useful for spotting anomalies (spike in permission.denied, etc.)
    """
    # hours is validated as int by Query(ge=1, le=720) — safe to interpolate
    safe_hours = int(hours)
    sql = text(f"""
        SELECT action, outcome, COUNT(*) AS event_count
        FROM audit.audit_logs
        WHERE occurred_at >= NOW() - INTERVAL '{safe_hours} hours'
        GROUP BY action, outcome
        ORDER BY event_count DESC
    """)  # noqa: S608

    result = await db.execute(sql)
    rows = result.mappings().all()

    by_action: dict[str, int] = {}
    by_action_outcome: dict[str, dict[str, int]] = {}
    for row in rows:
        a = row["action"]
        o = row["outcome"]
        c = row["event_count"]
        by_action[a] = by_action.get(a, 0) + c
        by_action_outcome.setdefault(a, {})[o] = c

    return {
        "hours": safe_hours,
        "total_events": sum(by_action.values()),
        "by_action": by_action,
        "by_action_outcome": by_action_outcome,
    }


def _row_to_dict(row) -> dict:
    """Convert a SQLAlchemy Row mapping to a JSON-serializable dict."""
    return {
        "id": str(row["id"]),
        "action": row["action"],
        "outcome": row["outcome"],
        "actor_id": str(row["actor_id"]) if row["actor_id"] else None,
        "actor_role": row["actor_role"],
        "resource_type": row["resource_type"],
        "resource_id": str(row["resource_id"]) if row["resource_id"] else None,
        "details": row["details"],
        "ip_address": row["ip_address"],
        "user_agent": row["user_agent"],
        "request_id": row["request_id"],
        "occurred_at": row["occurred_at"].isoformat() if row["occurred_at"] else None,
    }


__all__ = ["router"]
