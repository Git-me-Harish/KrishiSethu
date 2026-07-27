"""NDVI routes.

Endpoints:
Plot-specific (farmer-facing):
- GET  /plots/{id}/ndvi                — Latest NDVI observation
- GET  /plots/{id}/ndvi/history        — Time series (last 12 observations)
- GET  /plots/{id}/ndvi/summary        — Aggregated summary (latest + trend + alerts + history)
- POST /plots/{id}/ndvi/refresh        — Manually trigger NDVI refresh (rate-limited)
- GET  /plots/{id}/ndvi/anomalies      — Active anomaly alerts for plot
- PATCH /ndvi/anomalies/{id}/ack       — Acknowledge or resolve an anomaly

Officer:
- GET  /officer/ndvi/heatmap           — District NDVI heatmap
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query

from krishisetu.core.dependencies import CurrentUser, DBSession, require_permissions
from krishisetu.core.logging import get_logger
from krishisetu.domains.identity.permissions import (
    PERM_NDVI_READ_DISTRICT,
    PERM_NDVI_READ_OWN,
    PERM_NDVI_REFRESH,
)
from krishisetu.domains.ndvi import services
from krishisetu.domains.ndvi.schemas import (
    DistrictNDVIHeatmapResponse,
    NDVIAnomalyAcknowledge,
    NDVIAnomalyAlertResponse,
    NDVIAnomalyListResponse,
    NDVIHistoryResponse,
    NDVIRefreshResponse,
    PlotNDVISummaryResponse,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Plot NDVI routes
# ---------------------------------------------------------------------------

plot_ndvi_router = APIRouter(
    prefix="/plots/{plot_id}/ndvi",
    tags=["ndvi"],
    dependencies=[Depends(require_permissions(PERM_NDVI_READ_OWN))],
)


@plot_ndvi_router.get("/summary", response_model=PlotNDVISummaryResponse)
async def get_plot_ndvi_summary(
    plot_id: Annotated[UUID, Path()],
    current_user: CurrentUser,
    db: DBSession,
) -> PlotNDVISummaryResponse:
    """Get aggregated NDVI summary for a plot.

    Returns latest observation, trend analysis, active anomalies, and
    last 12 observations for the time-series chart — all in one call.
    """
    return await services.get_plot_ndvi_summary(db, plot_id, current_user.id)


@plot_ndvi_router.get("/history", response_model=NDVIHistoryResponse)
async def get_plot_ndvi_history(
    plot_id: Annotated[UUID, Path()],
    current_user: CurrentUser,
    db: DBSession,
    limit: int = Query(default=12, ge=1, le=52, description="Number of observations (max 1 year)"),
) -> NDVIHistoryResponse:
    """Get NDVI time series for a plot.

    Returns observations in reverse chronological order (most recent first).
    Each observation includes the NDVI statistics and health category.
    """
    return await services.get_plot_ndvi_history(
        db, plot_id, current_user.id, limit=limit
    )


@plot_ndvi_router.post(
    "/refresh",
    response_model=NDVIRefreshResponse,
    dependencies=[Depends(require_permissions(PERM_NDVI_REFRESH))],
)
async def refresh_plot_ndvi(
    plot_id: Annotated[UUID, Path()],
    current_user: CurrentUser,
    db: DBSession,
) -> NDVIRefreshResponse:
    """Manually trigger NDVI refresh for a plot.

    Fetches the latest satellite imagery and recomputes NDVI. Rate-limited
    to once per 12 hours per plot — if the latest observation is newer than
    12 hours, the refresh is skipped and the existing observation is returned.

    In dev mode (no Sentinel Hub credentials), generates synthetic NDVI
    based on plot characteristics and current month.
    """
    return await services.refresh_plot_ndvi(db, plot_id, current_user.id)


@plot_ndvi_router.get("/anomalies", response_model=NDVIAnomalyListResponse)
async def get_plot_anomalies(
    plot_id: Annotated[UUID, Path()],
    current_user: CurrentUser,
    db: DBSession,
) -> NDVIAnomalyListResponse:
    """Get active NDVI anomaly alerts for a plot.

    Anomalies are generated when:
    - NDVI drops by more than 0.15 between consecutive observations
    - NDVI drops by more than 0.30 (severe drop)
    - NDVI falls below 0.2 (bare soil when crop expected)
    """
    return await services.get_plot_anomalies(db, plot_id, current_user.id)


# ---------------------------------------------------------------------------
# Anomaly acknowledgment (separate router — no plot_id in path)
# ---------------------------------------------------------------------------

ndvi_anomaly_router = APIRouter(
    prefix="/ndvi/anomalies",
    tags=["ndvi"],
)


@ndvi_anomaly_router.patch(
    "/{alert_id}/ack",
    response_model=NDVIAnomalyAlertResponse,
    dependencies=[Depends(require_permissions(PERM_NDVI_READ_OWN))],
)
async def acknowledge_anomaly(
    alert_id: Annotated[UUID, Path()],
    payload: NDVIAnomalyAcknowledge,
    current_user: CurrentUser,
    db: DBSession,
) -> NDVIAnomalyAlertResponse:
    """Acknowledge or resolve an NDVI anomaly alert.

    - Without resolution_notes: marks as 'acknowledged' (farmer has seen it)
    - With resolution_notes: marks as 'resolved' (issue addressed)
    """
    return await services.acknowledge_anomaly(
        db, alert_id, current_user.id, payload
    )


# ---------------------------------------------------------------------------
# Officer routes
# ---------------------------------------------------------------------------

officer_ndvi_router = APIRouter(
    prefix="/officer/ndvi",
    tags=["officer"],
    dependencies=[Depends(require_permissions(PERM_NDVI_READ_DISTRICT))],
)


@officer_ndvi_router.get(
    "/heatmap",
    response_model=DistrictNDVIHeatmapResponse,
)
async def get_district_heatmap(
    current_user: CurrentUser,
    db: DBSession,
    state: str | None = Query(
        default=None,
        description="Filter by state. If omitted, returns all states.",
    ),
    days_back: int = Query(
        default=14,
        ge=1,
        le=90,
        description="Only consider observations from the last N days",
    ),
) -> DistrictNDVIHeatmapResponse:
    """Get NDVI heatmap aggregated by district.

    Officer-only endpoint. Returns per-district statistics:
    - Average NDVI across all plots with recent observations
    - Health distribution (healthy / moderate / sparse / bare plots)
    - Active anomaly count

    Used to identify districts under vegetation stress.
    """
    return await services.get_district_heatmap(
        db, state=state, days_back=days_back
    )
