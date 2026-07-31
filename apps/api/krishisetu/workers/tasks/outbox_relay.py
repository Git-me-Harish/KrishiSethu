"""Outbox relay — drains pending outbox events and dispatches them to Celery.

This task runs every 10 seconds via Celery Beat. It:
1. SELECTs up to 50 pending outbox rows (status='pending', attempts < max_attempts)
2. For each row, looks up the Celery task name via TASK_REGISTRY
3. Calls task.delay(**payload)
4. Marks the row as dispatched (or increments attempts on failure)

If Redis is down, step 3 raises and the row stays pending — it will be
retried on the next relay cycle. This is the key property of the
transactional outbox: the event is persisted in Postgres (durable) and
only removed from the pending state when Celery confirms receipt.

Idempotency: if the relay crashes between dispatching the Celery task
and marking the row as dispatched, the task may run twice. Celery tasks
must therefore be idempotent (check if the work is already done before
proceeding). This is already the case for:
- disease.predict_disease (checks if report.status == COMPLETED)
- ndvi.refresh_plot_ndvi_task (checks if observation is < 12h old)
- soil.fetch_soil_data (overwrites soil data — idempotent by nature)
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from celery import Task
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from krishisetu.core.database import AsyncSessionLocal
from krishisetu.core.logging import get_logger
from krishisetu.core.outbox import TASK_REGISTRY
from krishisetu.workers.celery_app import celery_app

logger = get_logger(__name__)

# How many events to dispatch per relay cycle
BATCH_SIZE = 50


@celery_app.task(
    name="krishisetu.workers.tasks.outbox_relay.drain_outbox",
    bind=True,
    max_retries=None,  # This task should never retry — it's a periodic drain
    time_limit=60,  # 1 minute hard limit (must finish before next beat cycle)
    soft_time_limit=45,
)
def drain_outbox(self: Task) -> dict[str, Any]:
    """Drain pending outbox events and dispatch them to Celery.

    Runs every 10 seconds via Celery Beat. Returns a summary of
    dispatched/failed counts for logging.
    """
    return asyncio.run(_drain_outbox_async())


async def _drain_outbox_async() -> dict[str, Any]:
    """Async implementation of the outbox drain."""
    dispatched = 0
    failed = 0
    skipped = 0

    async with AsyncSessionLocal() as db:
        # Fetch pending events
        events = await _fetch_pending_events(db, limit=BATCH_SIZE)

        if not events:
            return {"dispatched": 0, "failed": 0, "skipped": 0, "total": 0}

        for event in events:
            result = await _dispatch_one(db, event)
            if result == "dispatched":
                dispatched += 1
            elif result == "failed":
                failed += 1
            else:
                skipped += 1

        await db.commit()

    logger.info(
        "outbox.relay_completed",
        dispatched=dispatched,
        failed=failed,
        skipped=skipped,
        total=len(events),
    )

    return {
        "dispatched": dispatched,
        "failed": failed,
        "skipped": skipped,
        "total": len(events),
    }


async def _fetch_pending_events(
    db: AsyncSession, limit: int = BATCH_SIZE
) -> list[dict[str, Any]]:
    """Fetch pending outbox events, ordered by creation time (oldest first)."""
    query = text("""
        SELECT id, event_type, payload, attempts, max_attempts
        FROM system.outbox_events
        WHERE status = 'pending' AND attempts < max_attempts
        ORDER BY created_at ASC
        LIMIT :limit
        FOR UPDATE SKIP LOCKED
    """)

    result = await db.execute(query, {"limit": limit})
    rows = result.fetchall()

    return [
        {
            "id": row[0],
            "event_type": row[1],
            "payload": row[2] if isinstance(row[2], dict) else json.loads(row[2]),
            "attempts": row[3],
            "max_attempts": row[4],
        }
        for row in rows
    ]


async def _dispatch_one(
    db: AsyncSession, event: dict[str, Any]
) -> str:
    """Dispatch a single outbox event to its Celery task.

    Returns "dispatched", "failed", or "skipped".
    """
    event_id = event["id"]
    event_type = event["event_type"]
    payload = event["payload"]

    task_name = TASK_REGISTRY.get(event_type)
    if not task_name:
        # Unknown event type — mark as failed permanently
        await _mark_failed(db, event_id, f"Unknown event_type: {event_type}")
        return "failed"

    try:
        # Look up the Celery task by name and dispatch it
        # celery_app.tasks is a dict of all registered tasks
        task = celery_app.tasks.get(task_name)
        if task is None:
            await _mark_failed(db, event_id, f"Celery task not registered: {task_name}")
            return "failed"

        # Dispatch the task with the payload as kwargs
        task.delay(**payload)

        await _mark_dispatched(db, event_id)
        return "dispatched"

    except Exception as e:
        # Redis might be down, or the task might reject the payload
        error_msg = f"{type(e).__name__}: {e}"
        new_attempts = event["attempts"] + 1

        if new_attempts >= event["max_attempts"]:
            await _mark_failed(db, event_id, error_msg)
            return "failed"
        else:
            await _increment_attempts(db, event_id, new_attempts, error_msg)
            logger.warning(
                "outbox.dispatch_retry",
                event_id=str(event_id),
                event_type=event_type,
                attempts=new_attempts,
                max_attempts=event["max_attempts"],
                error=error_msg,
            )
            return "skipped"


async def _mark_dispatched(db: AsyncSession, event_id: UUID) -> None:
    """Mark an outbox event as successfully dispatched."""
    await db.execute(
        text("""
            UPDATE system.outbox_events
            SET status = 'dispatched', dispatched_at = NOW()
            WHERE id = :id
        """),
        {"id": str(event_id)},
    )


async def _mark_failed(db: AsyncSession, event_id: UUID, error: str) -> None:
    """Mark an outbox event as permanently failed."""
    await db.execute(
        text("""
            UPDATE system.outbox_events
            SET status = 'failed', last_error = :error, dispatched_at = NOW()
            WHERE id = :id
        """),
        {"id": str(event_id), "error": error[:2000]},
    )
    logger.error(
        "outbox.event_failed",
        event_id=str(event_id),
        error=error,
    )


async def _increment_attempts(
    db: AsyncSession, event_id: UUID, attempts: int, error: str
) -> None:
    """Increment the attempt counter for a pending outbox event."""
    await db.execute(
        text("""
            UPDATE system.outbox_events
            SET attempts = :attempts, last_error = :error
            WHERE id = :id
        """),
        {"id": str(event_id), "attempts": attempts, "error": error[:2000]},
    )
