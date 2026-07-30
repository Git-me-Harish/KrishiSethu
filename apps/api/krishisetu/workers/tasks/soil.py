"""Soil data fetch Celery task.

This task is dispatched when a farmer registers a new plot. It queries
the ISRIC SoilGrids REST API with the plot's centroid to fetch soil
properties (pH, organic carbon), then updates the plot row with the
results. """

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx
from celery import Task
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from krishisetu.core.database import AsyncSessionLocal
from krishisetu.core.logging import get_logger
from krishisetu.workers.celery_app import celery_app

logger = get_logger(__name__)


# ISRIC SoilGrids API endpoint
ISRIC_API_URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"

# Celery task (sync entry point — bridges to async with asyncio.run)
@celery_app.task(
    name="krishisetu.workers.tasks.soil.fetch_soil_data",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,
)
def fetch_soil_data(
    self: Task,
    plot_id: str,
    lon: float,
    lat: float,
) -> dict[str, Any]:
    """Fetch soil data from ISRIC SoilGrids and update the plot.

    Args:
        plot_id: UUID of the plot (as string for JSON serialization)
        lon: Longitude of the plot centroid
        lat: Latitude of the plot centroid

    Returns:
        Dict with status, plot_id, and soil data (or error).
    """
    try:
        return asyncio.run(_fetch_soil_data_async(UUID(plot_id), lon, lat))
    except Exception as exc:
        logger.error(
            "soil.task.failed",
            plot_id=plot_id,
            error=str(exc),
            error_type=type(exc).__name__,
        )
        # Retry with exponential backoff for transient failures
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


# Async implementation
async def _fetch_soil_data_async(
    plot_id: UUID,
    lon: float,
    lat: float,
) -> dict[str, Any]:
    """Async implementation of the soil data fetch task.

    Steps:
    1. Call ISRIC SoilGrids API with the plot centroid
    2. Parse the response (pH, soil organic carbon)
    3. Update the plot row with soil_type and soil_ph
    """
    # --- 1. Call ISRIC API ---
    soil_data = await _call_isric_api(lon, lat)
    if not soil_data:
        logger.info("soil.task.no_data", plot_id=str(plot_id))
        return {
            "status": "no_data",
            "plot_id": str(plot_id),
            "message": "ISRIC API returned no soil data for this location",
        }

    # --- 2. Update the plot row ---
    async with AsyncSessionLocal() as db:
        await _update_plot_soil(
            db,
            plot_id,
            soil_type=soil_data.get("soil_type"),
            soil_ph=soil_data.get("ph"),
        )
        await db.commit()

    logger.info(
        "soil.task.completed",
        plot_id=str(plot_id),
        soil_ph=str(soil_data.get("ph")) if soil_data.get("ph") else "None",
    )

    return {
        "status": "completed",
        "plot_id": str(plot_id),
        "soil_ph": str(soil_data.get("ph")) if soil_data.get("ph") else None,
        "soil_type": soil_data.get("soil_type"),
    }


async def _call_isric_api(lon: float, lat: float) -> dict[str, Any] | None:
    """Call the ISRIC SoilGrids API and return parsed soil data.

    Returns a dict with:
    - soil_type: WRB soil type (currently None — ISRIC doesn't return this
      via the properties endpoint; would need a separate classification query)
    - ph: soil pH (mean of top layer, converted from ISRIC's log scale)

    Returns None on any error (best-effort).
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                ISRIC_API_URL,
                params={
                    "lon": lon,
                    "lat": lat,
                    "property": ["phh2o", "soc"],  # pH and soil organic carbon
                    "depth": "5-15cm",  # Top layer
                    "value": "mean",
                },
            )
    except httpx.HTTPError as e:
        logger.warning("isric.network_error", error=str(e))
        return None

    if response.status_code != 200:
        logger.warning(
            "isric.api_error",
            status=response.status_code,
            body=response.text[:200],
        )
        return None

    data = response.json()
    properties = data.get("properties", {})
    layers = properties.get("layers", [])

    ph: Decimal | None = None
    for layer in layers:
        if layer.get("name") == "phh2o":
            depths = layer.get("depths", [])
            if depths:
                ph_mean = depths[0].get("values", {}).get("mean")
                if ph_mean is not None:
                    # ISRIC pH is in 10*log10(H+), needs conversion
                    ph = Decimal(str(10 - ph_mean / 10.0)).quantize(Decimal("0.01"))
            break

    return {
        "soil_type": None,  # ISRIC doesn't directly return WRB type via this endpoint
        "ph": ph,
    }


async def _update_plot_soil(
    db: AsyncSession,
    plot_id: UUID,
    *,
    soil_type: str | None,
    soil_ph: Decimal | None,
) -> None:
    """Update the soil_type and soil_ph columns on a plot row."""
    query = text("""
        UPDATE farmer.plots
        SET soil_type = :soil_type,
            soil_ph = :soil_ph,
            updated_at = NOW()
        WHERE id = :plot_id
    """)
    await db.execute(
        query,
        {
            "plot_id": plot_id,
            "soil_type": soil_type,
            "soil_ph": float(soil_ph) if soil_ph else None,
        },
    )