"""Transactional outbox for reliable async task dispatch.

SOLUTION:
    The transactional outbox pattern:
    1. In the same DB transaction as the business write, insert a row into
       `system.outbox_events` with the task name + payload.
    2. When the transaction commits, the outbox row is persisted atomically
       with the business data — no window for loss.
    3. A separate relay task (Celery beat, every 10s) scans for pending
       outbox rows, dispatches them to Celery, and marks them as
       dispatched. If Redis is still down, the row stays pending and
       will be retried on the next relay cycle.
    4. If the Celery task itself fails, the relay can retry up to
       max_attempts before marking the row as failed (with the error).

USAGE:
    from krishisetu.core.outbox import dispatch_via_outbox

    # Inside a service function, in the same transaction as the DB write:
    await dispatch_via_outbox(
        db,
        event_type="ndvi.refresh_plot",
        payload={"plot_id": str(plot_id), "farmer_id": str(farmer_id)},
    )
    # The outbox row is committed atomically with the service's other writes.
    # The relay will dispatch it to Celery within 10 seconds.

RELAY:
    The relay is a Celery task (`workers.tasks.outbox_relay.drain_outbox`)
    that runs every 10 seconds via Celery Beat. It:
    1. SELECTs pending outbox rows (status='pending', attempts < max)
    2. For each row, looks up the Celery task by event_type → task name mapping
    3. Calls task.delay(**payload)
    4. Marks the row as dispatched (or increments attempts on failure)

    The event_type → task name mapping is defined in TASK_REGISTRY below.
    To add a new outbox-dispatched task, add an entry to TASK_REGISTRY.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from krishisetu.core.logging import get_logger
from krishisetu.core.database import Base
from sqlalchemy import Column, DateTime, Integer, String, text as sa_text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

logger = get_logger(__name__)

# ORM model
class OutboxEvent(Base):
    """A pending async task dispatch, stored in the transactional outbox.

    Maps to: system.outbox_events

    Lifecycle:
        pending → dispatched (relay successfully called task.delay())
        pending → failed (max_attempts exceeded)
    """

    __tablename__ = "outbox_events"
    __table_args__ = {"schema": "system"}

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        server_default=sa_text("gen_random_uuid()"),
        primary_key=True,
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Maps to a Celery task name via TASK_REGISTRY",
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment="JSON kwargs to pass to the Celery task",
    )
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
        index=True,
        comment="pending, dispatched, failed",
    )
    attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=3,
        server_default="3",
    )
    last_error: Mapped[str | None] = mapped_column(
        String(2000),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa_text("NOW()"),
        nullable=False,
    )
    dispatched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


# Event type → Celery task name registry
TASK_REGISTRY: dict[str, str] = {
    "ndvi.refresh_plot": "krishisetu.workers.tasks.ndvi.refresh_plot_ndvi_task",
    "disease.predict": "krishisetu.workers.tasks.disease.predict_disease",
    "soil.fetch": "krishisetu.workers.tasks.soil.fetch_soil_data",
}

# Dispatch helper (called from service layer)
async def dispatch_via_outbox(
    db: AsyncSession,
    *,
    event_type: str,
    payload: dict[str, Any],
    max_attempts: int = 3,
) -> UUID:
    """Write an outbox event in the current transaction.

    This does NOT dispatch the task — it only stages the event. The
    outbox relay (workers.tasks.outbox_relay.drain_outbox) will pick it
    up and dispatch it to Celery within 10 seconds.

    The event is committed atomically with the caller's other writes
    when the transaction commits (via get_db's session-per-request commit).

    Args:
        db: async DB session (the event is staged in this transaction)
        event_type: must be a key in TASK_REGISTRY
        payload: JSON-serializable dict of kwargs for the Celery task
        max_attempts: max retry count before marking as failed

    Returns:
        The UUID of the outbox event (can be used as a task_id for
        client-side polling).
    """
    if event_type not in TASK_REGISTRY:
        raise ValueError(
            f"Unknown event_type '{event_type}'. "
            f"Register it in core/outbox.py TASK_REGISTRY first."
        )

    event_id = uuid4()

    insert_sql = text("""
        INSERT INTO system.outbox_events
            (id, event_type, payload, status, attempts, max_attempts, created_at)
        VALUES
            (:id, :event_type, CAST(:payload AS JSONB), 'pending', 0, :max_attempts, NOW())
        RETURNING id
    """)

    import json
    await db.execute(
        insert_sql,
        {
            "id": str(event_id),
            "event_type": event_type,
            "payload": json.dumps(payload, default=str),
            "max_attempts": max_attempts,
        },
    )

    logger.info(
        "outbox.event_staged",
        event_id=str(event_id),
        event_type=event_type,
    )

    return event_id


__all__ = [
    "OutboxEvent",
    "TASK_REGISTRY",
    "dispatch_via_outbox",
]