"""NDVI Celery tasks.

Scheduled tasks:
- refresh_stale_ndvi: Nightly (2 AM), refreshes NDVI for plots with stale observations (>7 days)
"""

from __future__ import annotations

import asyncio
from typing import Any

from krishisetu.core.logging import get_logger
from krishisetu.domains.ndvi import services
from krishisetu.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(
    name="krishisetu.workers.tasks.ndvi.refresh_stale_ndvi",
    bind=True,
    max_retries=1,
    default_retry_delay=600,
    time_limit=3600,  # 1 hour hard limit
    soft_time_limit=3000,  # 50 min soft limit
)
def refresh_stale_ndvi(self, max_plots: int = 100) -> dict[str, Any]:
    """Refresh NDVI for all plots with stale observations (>7 days old).

    Runs nightly at 2 AM UTC via Celery Beat. For each stale plot:
    1. Fetch plot boundary
    2. Compute bounding box
    3. Fetch Sentinel-2 band data
    4. Compute NDVI statistics
    5. Store observation
    6. Detect anomaly (compare to previous observation)

    Returns summary statistics.
    """
    logger.info("ndvi.refresh_stale.started", task_id=self.request.id, max_plots=max_plots)

    try:
        result = asyncio.run(services.refresh_stale_plots(max_plots=max_plots))
        logger.info(
            "ndvi.refresh_stale.completed",
            refreshed=result["refreshed"],
            skipped=result["skipped"],
            failed=result["failed"],
            total=result["total"],
        )
        return result
    except Exception as exc:
        logger.error("ndvi.refresh_stale.failed", error=str(exc))
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=600)
        raise
