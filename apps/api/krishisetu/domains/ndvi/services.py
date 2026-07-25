"""NDVI domain — business logic services.

Orchestrates:
- NDVI computation for a plot (fetch bands → compute NDVI → store observation)
- Anomaly detection (compare to previous observation)
- Plot NDVI summary (latest + trend + alerts)
- District heatmap aggregation (for officers)
- Manual refresh (user-triggered)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from krishisetu.core.exceptions import NotFoundError, ValidationError
from krishisetu.core.logging import get_logger
from krishisetu.core.storage import get_storage
from krishisetu.domains.farmer import repository as farmer_repo
from krishisetu.domains.farmer.models import Plot
from krishisetu.domains.ndvi import repository as repo
from krishisetu.domains.ndvi.computation import (
    classify_ndvi_health,
    compute_ndvi_stats,
    detect_ndvi_anomaly,
)
from krishisetu.domains.ndvi.models import (
    NDVIAnomalyAlert,
    NDVIAnomalyType,
    NDVIObservation,
    NDVISource,
)
from krishisetu.domains.ndvi.schemas import (
    DistrictNDVIHeatmapResponse,
    DistrictNDVIStat,
    NDVIAnomalyAcknowledge,
    NDVIAnomalyAlertResponse,
    NDVIAnomalyListResponse,
    NDVIHistoryResponse,
    NDVIObservationResponse,
    NDVIRefreshResponse,
    PlotNDVISummaryResponse,
)
from krishisetu.integrations.sentinel_hub import get_sentinel_client

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maximum plots to refresh per nightly batch
MAX_PLOTS_PER_BATCH = 100

# NDVI observation retention (days) — older observations are archived
OBSERVATION_RETENTION_DAYS = 365

# Raster dimensions for fetched imagery
RASTER_WIDTH = 100
RASTER_HEIGHT = 100


# ---------------------------------------------------------------------------
# NDVI computation
# ---------------------------------------------------------------------------


async def compute_and_store_ndvi(
    db: AsyncSession,
    plot_id: UUID,
) -> dict[str, Any]:
    """Compute NDVI for a plot and store the observation.

    Steps:
    1. Fetch plot (with boundary centroid)
    2. Compute bounding box from plot boundary
    3. Fetch Sentinel-2 band data (Red, NIR, SCL)
    4. Compute NDVI statistics (mean, min, max, stddev, cloud cover)
    5. Store observation in database
    6. Compare to previous observation → create anomaly alert if drop detected
    7. Upload NDVI raster to S3 (if not cloudy)

    Returns dict with observation details and any anomaly created.
    """
    # --- 1. Fetch plot ---
    plot = await farmer_repo.get_plot_by_id(db, plot_id)
    if not plot:
        raise NotFoundError("Plot", str(plot_id))

    # --- 2. Compute bounding box ---
    bbox = _compute_bbox_from_plot(plot)
    if not bbox:
        raise ValidationError("Plot has no boundary — cannot compute NDVI")

    # --- 3. Fetch band data ---
    sentinel = get_sentinel_client()
    band_data = await sentinel.fetch_band_data(
        bbox=bbox,
        plot_id=plot_id,
        max_days_back=14,
        width=RASTER_WIDTH,
        height=RASTER_HEIGHT,
    )

    if not band_data:
        raise ValidationError("No suitable satellite imagery available (cloud cover too high)")

    # --- 4. Compute NDVI statistics ---
    stats = compute_ndvi_stats(band_data)

    # Skip storage if too cloudy (>50%)
    if float(stats.cloud_cover_pct) > 50:
        logger.info(
            "ndvi.skipped_cloudy",
            plot_id=str(plot_id),
            cloud_cover=str(stats.cloud_cover_pct),
        )
        return {
            "status": "skipped",
            "reason": "cloud_cover_too_high",
            "cloud_cover_pct": float(stats.cloud_cover_pct),
        }

    # --- 5. Upload raster to S3 (if raster available) ---
    raster_url = None
    if stats.ndvi_raster:
        storage = get_storage()
        raster_key = storage.ndvi_raster_key(plot_id, band_data.observed_at.strftime("%Y-%m-%d"))
        try:
            # In production, this would be a GeoTIFF. For now, store as JSON
            # (the frontend can render it as a heatmap overlay).
            import json

            raster_json = json.dumps({
                "width": band_data.width,
                "height": band_data.height,
                "ndvi": stats.ndvi_raster,
                "observed_at": band_data.observed_at.isoformat(),
            })
            storage.upload_bytes(
                key=raster_key,
                data=raster_json.encode("utf-8"),
                content_type="application/json",
            )
            raster_url = raster_key
        except Exception as e:
            logger.warning(
                "ndvi.raster_upload_failed",
                plot_id=str(plot_id),
                error=str(e),
            )

    # --- 6. Store observation ---
    source = NDVISource.SYNTHETIC if not sentinel.is_live else NDVISource.SENTINEL2

    observation = await repo.create_observation(
        db,
        plot_id=plot_id,
        observed_at=band_data.observed_at,
        source=source,
        ndvi_mean=stats.ndvi_mean,
        ndvi_min=stats.ndvi_min,
        ndvi_max=stats.ndvi_max,
        ndvi_stddev=stats.ndvi_stddev,
        cloud_cover_pct=stats.cloud_cover_pct,
        valid_pixel_count=stats.valid_pixel_count,
        total_pixel_count=stats.total_pixel_count,
        raster_url=raster_url,
        raw_metadata=band_data.raw_metadata,
    )

    if not observation:
        return {"status": "failed", "reason": "storage_failed"}

    # --- 7. Anomaly detection ---
    anomaly = await _detect_and_create_anomaly(
        db,
        plot_id=plot_id,
        farmer_id=plot.farmer_id,
        current_observation=observation,
    )

    logger.info(
        "ndvi.computed_and_stored",
        plot_id=str(plot_id),
        ndvi_mean=str(stats.ndvi_mean),
        cloud_cover=str(stats.cloud_cover_pct),
        source=source.value,
        anomaly_created=anomaly is not None,
    )

    return {
        "status": "completed",
        "observation_id": str(observation.id),
        "ndvi_mean": stats.ndvi_mean,
        "cloud_cover_pct": stats.cloud_cover_pct,
        "health_category": classify_ndvi_health(float(stats.ndvi_mean)),
        "anomaly_created": anomaly is not None,
        "anomaly_type": anomaly.anomaly_type.value if anomaly else None,
    }


async def _detect_and_create_anomaly(
    db: AsyncSession,
    *,
    plot_id: UUID,
    farmer_id: UUID,
    current_observation: NDVIObservation,
) -> NDVIAnomalyAlert | None:
    """Compare current NDVI to previous and create anomaly alert if needed."""
    previous = await repo.get_previous_observation(
        db, plot_id, current_observation.observed_at
    )
    if not previous:
        return None  # First observation — no comparison

    prev_ndvi = float(previous.ndvi_mean)
    curr_ndvi = float(current_observation.ndvi_mean)

    anomaly_type_str, drop = detect_ndvi_anomaly(prev_ndvi, curr_ndvi)

    if not anomaly_type_str:
        return None

    anomaly_type = NDVIAnomalyType(anomaly_type_str)

    # Check for duplicate (don't spam alerts for the same issue)
    existing = await repo.find_duplicate_anomaly(db, plot_id, anomaly_type)
    if existing:
        return None

    # Create the alert
    alert = await repo.create_anomaly_alert(
        db,
        plot_id=plot_id,
        farmer_id=farmer_id,
        anomaly_type=anomaly_type,
        previous_ndvi=Decimal(str(round(prev_ndvi, 4))),
        current_ndvi=Decimal(str(round(curr_ndvi, 4))),
        drop_magnitude=Decimal(str(round(drop, 4))),
        previous_observation_id=previous.id,
        current_observation_id=current_observation.id,
    )

    logger.info(
        "ndvi.anomaly_created",
        plot_id=str(plot_id),
        anomaly_type=anomaly_type.value,
        previous_ndvi=prev_ndvi,
        current_ndvi=curr_ndvi,
        drop=drop,
    )

    # TODO: Dispatch push notification to farmer (Phase 2)
    # - "NDVI for plot X dropped by 18% in the last week. Tap to view map and inspect."

    return alert


# ---------------------------------------------------------------------------
# Plot NDVI queries
# ---------------------------------------------------------------------------


async def get_plot_ndvi_summary(
    db: AsyncSession,
    plot_id: UUID,
    farmer_id: UUID,
) -> PlotNDVISummaryResponse:
    """Get aggregated NDVI summary for a plot.

    Returns latest observation, previous observation, trend, active anomalies,
    and last 12 observations for the time-series chart.
    """
    plot = await farmer_repo.get_plot_by_id(db, plot_id, include_boundary=False)
    if not plot or plot.farmer_id != farmer_id:
        raise NotFoundError("Plot", str(plot_id))

    # Fetch latest + history + anomalies in parallel
    latest = await repo.get_latest_observation(db, plot_id)
    history = await repo.list_observations_by_plot(db, plot_id, limit=12)
    anomalies = await repo.get_active_anomalies_for_plot(db, plot_id)

    # Determine trend
    trend = "insufficient_data"
    trend_change = None
    previous = None
    if len(history) >= 2:
        latest_ndvi = float(history[0].ndvi_mean)
        prev_ndvi = float(history[1].ndvi_mean)
        previous = history[1]
        trend_change = latest_ndvi - prev_ndvi
        if abs(trend_change) < 0.03:
            trend = "stable"
        elif trend_change > 0:
            trend = "improving"
        else:
            trend = "declining"

    # Build response
    storage = get_storage()
    latest_resp = _to_observation_response(latest, storage) if latest else None
    previous_resp = _to_observation_response(previous, storage) if previous else None
    history_resp = [_to_observation_response(o, storage) for o in history]

    anomaly_resps = [_to_anomaly_response(a) for a in anomalies]

    return PlotNDVISummaryResponse(
        plot_id=plot_id,
        plot_name=plot.nickname or f"Plot {plot.survey_number}",
        latest_observation=latest_resp,
        previous_observation=previous_resp,
        trend=trend,
        trend_change=trend_change,
        active_anomalies=anomaly_resps,
        history=history_resp,
    )


async def get_plot_ndvi_history(
    db: AsyncSession,
    plot_id: UUID,
    farmer_id: UUID,
    *,
    limit: int = 12,
) -> NDVIHistoryResponse:
    """Get NDVI time series for a plot."""
    plot = await farmer_repo.get_plot_by_id(db, plot_id, include_boundary=False)
    if not plot or plot.farmer_id != farmer_id:
        raise NotFoundError("Plot", str(plot_id))

    history = await repo.list_observations_by_plot(db, plot_id, limit=limit)
    storage = get_storage()

    observations = [_to_observation_response(o, storage) for o in history]
    latest_health = observations[0].health_category if observations else None

    # Compute trend
    trend = "insufficient_data"
    if len(observations) >= 2:
        change = float(observations[0].ndvi_mean) - float(observations[1].ndvi_mean)
        if abs(change) < 0.03:
            trend = "stable"
        elif change > 0:
            trend = "improving"
        else:
            trend = "declining"

    return NDVIHistoryResponse(
        plot_id=plot_id,
        observations=observations,
        total=len(observations),
        latest_health=latest_health,
        trend=trend,
    )


async def refresh_plot_ndvi(
    db: AsyncSession,
    plot_id: UUID,
    farmer_id: UUID,
) -> NDVIRefreshResponse:
    """Manually trigger NDVI refresh for a plot.

    The refresh happens synchronously (not via Celery) for immediate feedback.
    Rate-limited to once per day per plot (configurable).
    """
    plot = await farmer_repo.get_plot_by_id(db, plot_id, include_boundary=False)
    if not plot or plot.farmer_id != farmer_id:
        raise NotFoundError("Plot", str(plot_id))

    # Check if a refresh was done today (rate limit)
    latest = await repo.get_latest_observation(db, plot_id)
    if latest:
        age = datetime.now(timezone.utc) - latest.observed_at
        if age < timedelta(hours=12):
            return NDVIRefreshResponse(
                plot_id=plot_id,
                status="skipped",
                observation_id=str(latest.id),
                ndvi_mean=latest.ndvi_mean,
                health_category=classify_ndvi_health(float(latest.ndvi_mean)),
                cloud_cover_pct=latest.cloud_cover_pct,
                message=f"NDVI was refreshed {int(age.total_seconds() / 3600)} hours ago. "
                f"Manual refresh is rate-limited to once per 12 hours.",
            )

    # Compute NDVI
    result = await compute_and_store_ndvi(db, plot_id)

    if result.get("status") == "completed":
        return NDVIRefreshResponse(
            plot_id=plot_id,
            status="completed",
            observation_id=result.get("observation_id"),
            ndvi_mean=result.get("ndvi_mean"),
            health_category=result.get("health_category"),
            cloud_cover_pct=result.get("cloud_cover_pct"),
            message="NDVI refreshed successfully.",
        )
    elif result.get("status") == "skipped":
        return NDVIRefreshResponse(
            plot_id=plot_id,
            status="skipped",
            cloud_cover_pct=Decimal(str(result.get("cloud_cover_pct", 0))),
            message="Cloud cover too high — try again later.",
        )
    else:
        return NDVIRefreshResponse(
            plot_id=plot_id,
            status="failed",
            message=result.get("reason", "Unknown error"),
        )


# ---------------------------------------------------------------------------
# NDVI anomaly queries
# ---------------------------------------------------------------------------


async def get_plot_anomalies(
    db: AsyncSession,
    plot_id: UUID,
    farmer_id: UUID,
) -> NDVIAnomalyListResponse:
    """Get active NDVI anomaly alerts for a plot."""
    plot = await farmer_repo.get_plot_by_id(db, plot_id, include_boundary=False)
    if not plot or plot.farmer_id != farmer_id:
        raise NotFoundError("Plot", str(plot_id))

    anomalies = await repo.get_active_anomalies_for_plot(db, plot_id)
    return NDVIAnomalyListResponse(
        alerts=[_to_anomaly_response(a) for a in anomalies],
        total=len(anomalies),
    )


async def acknowledge_anomaly(
    db: AsyncSession,
    alert_id: UUID,
    farmer_id: UUID,
    payload: NDVIAnomalyAcknowledge,
) -> NDVIAnomalyAlertResponse:
    """Acknowledge or resolve an NDVI anomaly alert."""
    from sqlalchemy import select
    from krishisetu.domains.ndvi.models import NDVIAnomalyAlert

    # Fetch the alert
    result = await db.execute(
        select(NDVIAnomalyAlert).where(NDVIAnomalyAlert.id == alert_id)
    )
    alert = result.scalar_one_or_none()
    if not alert:
        raise NotFoundError("NDVIAnomalyAlert", str(alert_id))

    # Verify ownership
    if alert.farmer_id != farmer_id:
        raise NotFoundError("NDVIAnomalyAlert", str(alert_id))

    updated = await repo.acknowledge_anomaly(
        db, alert_id, resolution_notes=payload.resolution_notes
    )
    if not updated:
        raise NotFoundError("NDVIAnomalyAlert", str(alert_id))

    return _to_anomaly_response(updated)


# ---------------------------------------------------------------------------
# District heatmap (officer view)
# ---------------------------------------------------------------------------


async def get_district_heatmap(
    db: AsyncSession,
    *,
    state: str | None = None,
    days_back: int = 14,
) -> DistrictNDVIHeatmapResponse:
    """Get NDVI heatmap aggregated by district (for officers).

    Returns per-district statistics: avg NDVI, plot count, health distribution,
    active anomaly count.
    """
    stats = await repo.get_district_ndvi_stats(db, state=state, days_back=days_back)

    # Filter by state if provided
    if state:
        stats = [s for s in stats if s["state"] == state]

    # Compute aggregate stats
    total_plots = sum(s["plot_count"] for s in stats)
    avg_ndvi_values = [s["avg_ndvi"] for s in stats if s["avg_ndvi"] is not None]
    overall_avg = (
        sum(avg_ndvi_values) / len(avg_ndvi_values)
        if avg_ndvi_values
        else None
    )

    return DistrictNDVIHeatmapResponse(
        state=state,
        districts=[
            DistrictNDVIStat(**s) for s in stats
        ],
        total_plots=total_plots,
        avg_ndvi=Decimal(str(round(overall_avg, 4))) if overall_avg else None,
        generated_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# Batch refresh (Celery task entry point)
# ---------------------------------------------------------------------------


async def refresh_stale_plots(max_plots: int = MAX_PLOTS_PER_BATCH) -> dict[str, Any]:
    """Refresh NDVI for all plots with stale observations (>7 days old).

    Called by Celery Beat nightly.
    """
    from krishisetu.core.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        plots = await repo.list_plots_needing_refresh(
            db, max_age_days=7, limit=max_plots
        )

    if not plots:
        logger.info("ndvi.no_stale_plots")
        return {"refreshed": 0, "skipped": 0, "failed": 0, "total": 0}

    refreshed = 0
    skipped = 0
    failed = 0

    for plot_info in plots:
        try:
            async with AsyncSessionLocal() as db:
                result = await compute_and_store_ndvi(db, plot_info["plot_id"])
                await db.commit()

            if result.get("status") == "completed":
                refreshed += 1
            elif result.get("status") == "skipped":
                skipped += 1
            else:
                failed += 1
        except Exception as e:
            logger.warning(
                "ndvi.refresh_plot_failed",
                plot_id=str(plot_info["plot_id"]),
                error=str(e),
            )
            failed += 1

    logger.info(
        "ndvi.batch_refresh_completed",
        total=len(plots),
        refreshed=refreshed,
        skipped=skipped,
        failed=failed,
    )

    return {
        "refreshed": refreshed,
        "skipped": skipped,
        "failed": failed,
        "total": len(plots),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compute_bbox_from_plot(plot) -> tuple[float, float, float, float] | None:
    """Compute bounding box (west, south, east, north) from plot boundary.

    Expects plot.boundary to be a GeoJSON Polygon dict (set by repository).
    Returns None if boundary is missing or invalid.
    """
    boundary = getattr(plot, "boundary", None)
    if not boundary:
        # Try centroid
        centroid = getattr(plot, "centroid", None)
        if centroid and isinstance(centroid, dict):
            lon = centroid.get("lon", 0)
            lat = centroid.get("lat", 0)
            # Create a small bbox around centroid (~100m)
            return (lon - 0.001, lat - 0.001, lon + 0.001, lat + 0.001)
        return None

    if isinstance(boundary, str):
        import json
        try:
            boundary = json.loads(boundary)
        except Exception:
            return None

    if not isinstance(boundary, dict) or boundary.get("type") != "Polygon":
        return None

    coords = boundary.get("coordinates", [])
    if not coords or not coords[0]:
        return None

    # Flatten all coordinates
    all_coords = coords[0]  # Exterior ring
    lons = [c[0] for c in all_coords]
    lats = [c[1] for c in all_coords]

    return (min(lons), min(lats), max(lons), max(lats))


def _to_observation_response(
    obs: NDVIObservation, storage
) -> NDVIObservationResponse:
    """Convert NDVIObservation ORM object to response schema."""
    ndvi_mean = float(obs.ndvi_mean)
    health = classify_ndvi_health(ndvi_mean)
    is_cloudy = float(obs.cloud_cover_pct) > 30.0

    # Generate pre-signed URL for raster download
    raster_url = None
    if obs.raster_url:
        try:
            raster_url = storage.generate_download_url(obs.raster_url)
        except Exception:
            pass

    return NDVIObservationResponse(
        id=obs.id,
        plot_id=obs.plot_id,
        observed_at=obs.observed_at,
        source=obs.source,
        ndvi_mean=obs.ndvi_mean,
        ndvi_min=obs.ndvi_min,
        ndvi_max=obs.ndvi_max,
        ndvi_stddev=obs.ndvi_stddev,
        cloud_cover_pct=obs.cloud_cover_pct,
        valid_pixel_count=obs.valid_pixel_count,
        total_pixel_count=obs.total_pixel_count,
        raster_url=obs.raster_url,
        thumbnail_url=obs.thumbnail_url,
        created_at=obs.created_at,
        health_category=health,
        is_cloudy=is_cloudy,
        raster_download_url=raster_url,
    )


def _to_anomaly_response(alert: NDVIAnomalyAlert) -> NDVIAnomalyAlertResponse:
    """Convert NDVIAnomalyAlert ORM object to response schema."""
    prev = float(alert.previous_ndvi)
    drop = float(alert.drop_magnitude)
    drop_pct = (drop / prev) * 100 if prev > 0 else 0.0

    return NDVIAnomalyAlertResponse(
        id=alert.id,
        plot_id=alert.plot_id,
        farmer_id=alert.farmer_id,
        anomaly_type=alert.anomaly_type,
        status=alert.status,
        previous_ndvi=alert.previous_ndvi,
        current_ndvi=alert.current_ndvi,
        drop_magnitude=alert.drop_magnitude,
        drop_percentage=round(abs(drop_pct), 2),
        created_at=alert.created_at,
        acknowledged_at=alert.acknowledged_at,
        resolved_at=alert.resolved_at,
        resolution_notes=alert.resolution_notes,
    )
