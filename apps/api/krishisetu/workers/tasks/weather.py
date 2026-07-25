"""Weather & soil Celery tasks.

Scheduled tasks:
- sync_all_districts_weather: Every hour, sync weather for all districts with plots
- check_and_dispatch_alerts: Every 3 hours, check forecasts for extreme weather
- expire_old_alerts: Every hour, mark expired alerts as expired

The tasks use async DB sessions via asyncio.run() (Celery is sync).
"""

from __future__ import annotations

import asyncio
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from krishisetu.core.database import AsyncSessionLocal
from krishisetu.core.logging import get_logger
from krishisetu.domains.soil_weather import repository as repo
from krishisetu.domains.soil_weather import services
from krishisetu.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(
    name="krishisetu.workers.tasks.weather.sync_all_districts_weather",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
)
def sync_all_districts_weather(self) -> dict[str, Any]:
    """Sync weather for all districts with registered plots.

    Runs every hour via Celery Beat. For each district:
    1. Fetch current weather from IMD (or OWM fallback)
    2. Fetch 7-day forecast
    3. Upsert into the database

    Returns a summary of the sync operation.
    """
    logger.info("weather.sync_all.started", task_id=self.request.id)

    try:
        result = asyncio.run(_sync_all_districts_async())
        logger.info(
            "weather.sync_all.completed",
            districts_synced=result["districts_synced"],
            districts_failed=result["districts_failed"],
            observations_stored=result["observations_stored"],
        )
        return result
    except Exception as exc:
        logger.error("weather.sync_all.failed", error=str(exc))
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=300 * (2 ** self.request.retries))
        raise


async def _sync_all_districts_async() -> dict[str, Any]:
    """Async implementation of the weather sync task."""
    async with AsyncSessionLocal() as db:
        districts = await repo.list_districts_with_plots(db)

    if not districts:
        logger.info("weather.sync_all.no_districts")
        return {
            "status": "success",
            "districts_synced": 0,
            "districts_failed": 0,
            "observations_stored": 0,
        }

    synced = 0
    failed = 0
    observations = 0

    # Sync each district in its own session (avoid long-running transactions)
    for district, state in districts:
        try:
            async with AsyncSessionLocal() as db:
                result = await services.sync_district_weather(db, district, state)
                await db.commit()
                if result.get("status") == "success":
                    synced += 1
                    observations += result.get("forecasts_stored", 0) + 1
                else:
                    failed += 1
        except Exception as e:
            logger.warning(
                "weather.sync.district_failed",
                district=district,
                state=state,
                error=str(e),
            )
            failed += 1

    return {
        "status": "success",
        "districts_synced": synced,
        "districts_failed": failed,
        "observations_stored": observations,
        "total_districts": len(districts),
    }


# ---------------------------------------------------------------------------
# Alert check task
# ---------------------------------------------------------------------------


@celery_app.task(
    name="krishisetu.workers.tasks.weather.check_and_dispatch_alerts",
    bind=True,
    max_retries=2,
    default_retry_delay=180,
)
def check_and_dispatch_alerts(self) -> dict[str, Any]:
    """Check forecasts for all districts and generate alerts.

    Runs every 3 hours via Celery Beat. For each district with plots:
    1. Fetch the latest 3-day forecast
    2. Check against alert thresholds (heat wave, heavy rain, frost, high wind)
    3. Create alerts for threshold exceedances (deduped)
    4. Expire old alerts

    Returns a summary of alerts generated.
    """
    logger.info("weather.alert_check.started", task_id=self.request.id)

    try:
        result = asyncio.run(_check_alerts_async())
        logger.info(
            "weather.alert_check.completed",
            alerts_generated=result["alerts_generated"],
            districts_checked=result["districts_checked"],
        )
        return result
    except Exception as exc:
        logger.error("weather.alert_check.failed", error=str(exc))
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=180 * (2 ** self.request.retries))
        raise


async def _check_alerts_async() -> dict[str, Any]:
    """Async implementation of the alert check task."""
    async with AsyncSessionLocal() as db:
        districts = await repo.list_districts_with_plots(db)

    if not districts:
        return {"alerts_generated": 0, "districts_checked": 0}

    async with AsyncSessionLocal() as db:
        alerts = await services.check_and_generate_alerts(db, districts=districts)
        await db.commit()

    # TODO: Dispatch notifications for new alerts (Phase 2)
    # - Push notification via FCM to all farmers with plots in the affected district
    # - SMS via MSG91 for severe/critical alerts
    # - Voice advisory via TTS for critical alerts (in farmer's preferred language)

    return {
        "alerts_generated": len(alerts),
        "districts_checked": len(districts),
        "alert_types": list({a.alert_type.value for a in alerts}),
    }


# ---------------------------------------------------------------------------
# Alert expiry task (lightweight, runs every hour)
# ---------------------------------------------------------------------------


@celery_app.task(
    name="krishisetu.workers.tasks.weather.expire_old_alerts",
)
def expire_old_alerts() -> dict[str, Any]:
    """Mark alerts as expired if their expiry time has passed.

    Runs every hour via Celery Beat.
    """
    logger.info("weather.expire_alerts.started")

    try:
        count = asyncio.run(_expire_alerts_async())
        logger.info("weather.expire_alerts.completed", expired=count)
        return {"expired": count}
    except Exception as exc:
        logger.error("weather.expire_alerts.failed", error=str(exc))
        raise


async def _expire_alerts_async() -> int:
    async with AsyncSessionLocal() as db:
        count = await repo.expire_old_alerts(db)
        await db.commit()
    return count
