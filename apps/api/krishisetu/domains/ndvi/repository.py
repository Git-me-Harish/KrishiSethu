"""Database access layer for the NDVI domain.

Handles:
- NDVI observation CRUD with partitioned table support
- Time-series queries (latest, history, by date range)
- District-level aggregation for officer heatmap
- NDVI anomaly alert CRUD
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import and_, desc, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from krishisetu.domains.ndvi.models import (
    NDVIAnomalyAlert,
    NDVIAnomalyStatus,
    NDVIAnomalyType,
    NDVIObservation,
    NDVISource,
)

# ---------------------------------------------------------------------------
# NDVI Observation queries
# ---------------------------------------------------------------------------


async def create_observation(
    db: AsyncSession,
    *,
    plot_id: UUID,
    observed_at: datetime,
    source: NDVISource,
    ndvi_mean: Decimal,
    ndvi_min: Decimal,
    ndvi_max: Decimal,
    ndvi_stddev: Decimal,
    cloud_cover_pct: Decimal,
    valid_pixel_count: int,
    total_pixel_count: int,
    raster_url: str | None = None,
    thumbnail_url: str | None = None,
    raw_metadata: dict[str, Any] | None = None,
) -> NDVIObservation | None:
    """Create a new NDVI observation.

    Handles the partitioned table by using raw SQL INSERT with ON CONFLICT.
    """
    from uuid import uuid4

    obs_id = uuid4()

    # Use raw SQL to handle the partitioned table (SQLAlchemy ORM has issues
    # with INSERT into partitioned tables with composite PK)
    query = text("""
        INSERT INTO intelligence.ndvi_observations
            (id, plot_id, observed_at, source,
             ndvi_mean, ndvi_min, ndvi_max, ndvi_stddev,
             cloud_cover_pct, valid_pixel_count, total_pixel_count,
             raster_url, thumbnail_url, raw_metadata)
        VALUES
            (:id, :plot_id, :observed_at, :source,
             :ndvi_mean, :ndvi_min, :ndvi_max, :ndvi_stddev,
             :cloud_cover_pct, :valid_pixel_count, :total_pixel_count,
             :raster_url, :thumbnail_url, CAST(:raw_metadata AS jsonb))
        ON CONFLICT (plot_id, observed_at, source) DO UPDATE SET
            ndvi_mean = EXCLUDED.ndvi_mean,
            ndvi_min = EXCLUDED.ndvi_min,
            ndvi_max = EXCLUDED.ndvi_max,
            ndvi_stddev = EXCLUDED.ndvi_stddev,
            cloud_cover_pct = EXCLUDED.cloud_cover_pct,
            valid_pixel_count = EXCLUDED.valid_pixel_count,
            total_pixel_count = EXCLUDED.total_pixel_count,
            raster_url = EXCLUDED.raster_url,
            thumbnail_url = EXCLUDED.thumbnail_url,
            raw_metadata = EXCLUDED.raw_metadata
        RETURNING id
    """)

    import json

    try:
        result = await db.execute(
            query,
            {
                "id": obs_id,
                "plot_id": plot_id,
                "observed_at": observed_at,
                "source": source.value,
                "ndvi_mean": float(ndvi_mean),
                "ndvi_min": float(ndvi_min),
                "ndvi_max": float(ndvi_max),
                "ndvi_stddev": float(ndvi_stddev),
                "cloud_cover_pct": float(cloud_cover_pct),
                "valid_pixel_count": valid_pixel_count,
                "total_pixel_count": total_pixel_count,
                "raster_url": raster_url,
                "thumbnail_url": thumbnail_url,
                "raw_metadata": json.dumps(raw_metadata) if raw_metadata else None,
            },
        )
        row = result.fetchone()
        await db.flush()

        if row:
            return await get_observation_by_id(db, row[0], observed_at)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            "ndvi.observation_create_failed",
            plot_id=str(plot_id),
            error=str(e),
        )
    return None


async def get_observation_by_id(
    db: AsyncSession, obs_id: UUID, observed_at: datetime
) -> NDVIObservation | None:
    """Get an observation by ID (requires observed_at for partition pruning)."""
    result = await db.execute(
        select(NDVIObservation).where(
            and_(
                NDVIObservation.id == obs_id,
                NDVIObservation.observed_at == observed_at,
            )
        )
    )
    return result.scalar_one_or_none()


async def get_latest_observation(
    db: AsyncSession, plot_id: UUID
) -> NDVIObservation | None:
    """Get the most recent NDVI observation for a plot."""
    result = await db.execute(
        select(NDVIObservation)
        .where(NDVIObservation.plot_id == plot_id)
        .order_by(desc(NDVIObservation.observed_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_previous_observation(
    db: AsyncSession, plot_id: UUID, before: datetime
) -> NDVIObservation | None:
    """Get the observation before a given time (for anomaly detection)."""
    result = await db.execute(
        select(NDVIObservation)
        .where(
            and_(
                NDVIObservation.plot_id == plot_id,
                NDVIObservation.observed_at < before,
            )
        )
        .order_by(desc(NDVIObservation.observed_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def list_observations_by_plot(
    db: AsyncSession,
    plot_id: UUID,
    *,
    limit: int = 12,
) -> list[NDVIObservation]:
    """List NDVI observations for a plot, most recent first."""
    result = await db.execute(
        select(NDVIObservation)
        .where(NDVIObservation.plot_id == plot_id)
        .order_by(desc(NDVIObservation.observed_at))
        .limit(limit)
    )
    return list(result.scalars().all())


async def list_plots_needing_refresh(
    db: AsyncSession,
    *,
    max_age_days: int = 7,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """List plots whose NDVI is older than max_age_days.

    Returns a list of dicts with plot_id, farmer_id, district, state, last_observed_at.
    """
    cutoff = datetime.now(UTC) - timedelta(days=max_age_days)

    query = text("""
        SELECT p.id as plot_id, p.farmer_id, p.district, p.state,
               p.village, p.nickname,
               latest.observed_at as last_observed_at
        FROM farmer.plots p
        LEFT JOIN LATERAL (
            SELECT observed_at
            FROM intelligence.ndvi_observations
            WHERE plot_id = p.id
            ORDER BY observed_at DESC
            LIMIT 1
        ) latest ON true
        WHERE latest.observed_at IS NULL OR latest.observed_at < :cutoff
        ORDER BY COALESCE(latest.observed_at, '1970-01-01'::timestamptz) ASC
        LIMIT :limit
    """)

    result = await db.execute(query, {"cutoff": cutoff, "limit": limit})
    return [
        {
            "plot_id": row.plot_id,
            "farmer_id": row.farmer_id,
            "district": row.district,
            "state": row.state,
            "village": row.village,
            "nickname": row.nickname,
            "last_observed_at": row.last_observed_at,
        }
        for row in result.fetchall()
    ]


# ---------------------------------------------------------------------------
# NDVI Anomaly Alert queries
# ---------------------------------------------------------------------------


async def create_anomaly_alert(
    db: AsyncSession,
    *,
    plot_id: UUID,
    farmer_id: UUID,
    anomaly_type: NDVIAnomalyType,
    previous_ndvi: Decimal,
    current_ndvi: Decimal,
    drop_magnitude: Decimal,
    previous_observation_id: UUID | None = None,
    current_observation_id: UUID,
) -> NDVIAnomalyAlert:
    """Create a new NDVI anomaly alert."""
    alert = NDVIAnomalyAlert(
        plot_id=plot_id,
        farmer_id=farmer_id,
        anomaly_type=anomaly_type,
        previous_ndvi=previous_ndvi,
        current_ndvi=current_ndvi,
        drop_magnitude=drop_magnitude,
        previous_observation_id=previous_observation_id,
        current_observation_id=current_observation_id,
    )
    db.add(alert)
    await db.flush()
    await db.refresh(alert)
    return alert


async def get_active_anomalies_for_plot(
    db: AsyncSession, plot_id: UUID
) -> list[NDVIAnomalyAlert]:
    """Get all active/acknowledged/investigating anomalies for a plot."""
    result = await db.execute(
        select(NDVIAnomalyAlert)
        .where(
            and_(
                NDVIAnomalyAlert.plot_id == plot_id,
                NDVIAnomalyAlert.status.in_([
                    NDVIAnomalyStatus.ACTIVE.value,
                    NDVIAnomalyStatus.ACKNOWLEDGED.value,
                    NDVIAnomalyStatus.INVESTIGATING.value,
                ]),
            )
        )
        .order_by(desc(NDVIAnomalyAlert.created_at))
    )
    return list(result.scalars().all())


async def get_active_anomalies_for_farmer(
    db: AsyncSession, farmer_id: UUID
) -> list[NDVIAnomalyAlert]:
    """Get all active anomalies for a farmer (across all plots)."""
    result = await db.execute(
        select(NDVIAnomalyAlert)
        .where(
            and_(
                NDVIAnomalyAlert.farmer_id == farmer_id,
                NDVIAnomalyAlert.status.in_([
                    NDVIAnomalyStatus.ACTIVE.value,
                    NDVIAnomalyStatus.ACKNOWLEDGED.value,
                    NDVIAnomalyStatus.INVESTIGATING.value,
                ]),
            )
        )
        .order_by(desc(NDVIAnomalyAlert.created_at))
    )
    return list(result.scalars().all())


async def find_duplicate_anomaly(
    db: AsyncSession,
    plot_id: UUID,
    anomaly_type: NDVIAnomalyType,
) -> NDVIAnomalyAlert | None:
    """Check if an equivalent active anomaly already exists."""
    result = await db.execute(
        select(NDVIAnomalyAlert)
        .where(
            and_(
                NDVIAnomalyAlert.plot_id == plot_id,
                NDVIAnomalyAlert.anomaly_type == anomaly_type.value,
                NDVIAnomalyAlert.status.in_([
                    NDVIAnomalyStatus.ACTIVE.value,
                    NDVIAnomalyStatus.ACKNOWLEDGED.value,
                    NDVIAnomalyStatus.INVESTIGATING.value,
                ]),
            )
        )
        .order_by(desc(NDVIAnomalyAlert.created_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def acknowledge_anomaly(
    db: AsyncSession,
    alert_id: UUID,
    resolution_notes: str | None = None,
) -> NDVIAnomalyAlert | None:
    """Acknowledge or resolve an anomaly alert."""
    # If resolution notes are provided, mark as resolved; else just acknowledge
    new_status = NDVIAnomalyStatus.RESOLVED if resolution_notes else NDVIAnomalyStatus.ACKNOWLEDGED
    now = datetime.now(UTC)

    update_values: dict[str, Any] = {
        "status": new_status.value,
        "acknowledged_at": now,
    }
    if resolution_notes:
        update_values["resolved_at"] = now
        update_values["resolution_notes"] = resolution_notes

    await db.execute(
        update(NDVIAnomalyAlert)
        .where(NDVIAnomalyAlert.id == alert_id)
        .values(**update_values)
    )
    await db.flush()

    result = await db.execute(
        select(NDVIAnomalyAlert).where(NDVIAnomalyAlert.id == alert_id)
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# District aggregation (for officer heatmap)
# ---------------------------------------------------------------------------


async def get_district_ndvi_stats(
    db: AsyncSession,
    *,
    state: str | None = None,
    days_back: int = 14,
) -> list[dict[str, Any]]:
    """Get NDVI statistics aggregated by district.

    For each district, computes:
    - Average NDVI (across all plots with recent observations)
    - Min/Max NDVI
    - Plot count
    - Health distribution (healthy/moderate/sparse/bare)
    - Active anomaly count
    """
    cutoff = datetime.now(UTC) - timedelta(days=days_back)

    query = text("""
        SELECT
            p.district,
            p.state,
            AVG(latest.ndvi_mean) as avg_ndvi,
            MIN(latest.ndvi_min) as min_ndvi,
            MAX(latest.ndvi_max) as max_ndvi,
            COUNT(DISTINCT p.id) as plot_count,
            COUNT(DISTINCT CASE WHEN latest.ndvi_mean >= 0.6 THEN p.id END) as healthy_plots,
            COUNT(DISTINCT CASE WHEN latest.ndvi_mean >= 0.3 AND latest.ndvi_mean < 0.6
                  THEN p.id END) as moderate_plots,
            COUNT(DISTINCT CASE WHEN latest.ndvi_mean >= 0.1 AND latest.ndvi_mean < 0.3
                  THEN p.id END) as sparse_plots,
            COUNT(DISTINCT CASE WHEN latest.ndvi_mean < 0.1 THEN p.id END) as bare_plots,
            COUNT(DISTINCT na.id) as active_anomalies
        FROM farmer.plots p
        LEFT JOIN LATERAL (
            SELECT ndvi_mean, ndvi_min, ndvi_max
            FROM intelligence.ndvi_observations
            WHERE plot_id = p.id AND observed_at >= :cutoff
            ORDER BY observed_at DESC
            LIMIT 1
        ) latest ON true
        LEFT JOIN intelligence.ndvi_anomaly_alerts na ON na.plot_id = p.id
            AND na.status IN ('active', 'acknowledged', 'investigating')
        WHERE p.district IS NOT NULL
        GROUP BY p.district, p.state
        ORDER BY p.state, p.district
    """)

    params: dict[str, Any] = {"cutoff": cutoff}
    result = await db.execute(query, params)

    stats = []
    for row in result.fetchall():
        stats.append({
            "district": row.district,
            "state": row.state,
            "avg_ndvi": Decimal(str(round(row.avg_ndvi, 4))) if row.avg_ndvi else None,
            "min_ndvi": Decimal(str(round(row.min_ndvi, 4))) if row.min_ndvi else None,
            "max_ndvi": Decimal(str(round(row.max_ndvi, 4))) if row.max_ndvi else None,
            "plot_count": row.plot_count,
            "healthy_plots": row.healthy_plots or 0,
            "moderate_plots": row.moderate_plots or 0,
            "sparse_plots": row.sparse_plots or 0,
            "bare_plots": row.bare_plots or 0,
            "active_anomalies": row.active_anomalies or 0,
        })

    return stats


async def get_plot_count_by_state(db: AsyncSession) -> dict[str, int]:
    """Get plot count by state (for filtering)."""
    from krishisetu.domains.farmer.models import Plot

    query = (
        select(Plot.state, func.count(Plot.id))
        .group_by(Plot.state)
        .order_by(desc(func.count(Plot.id)))
    )
    result = await db.execute(query)
    return {row[0]: row[1] for row in result.fetchall()}
