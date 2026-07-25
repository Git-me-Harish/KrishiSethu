"""Pydantic schemas for the NDVI domain."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NDVISourceEnum(str, Enum):
    SENTINEL2 = "sentinel2"
    LANDSAT8 = "landsat8"
    SYNTHETIC = "synthetic"


class NDVIHealthEnum(str, Enum):
    HEALTHY = "healthy"
    MODERATE = "moderate"
    SPARSE = "sparse"
    BARE = "bare"


class NDVIAnomalyTypeEnum(str, Enum):
    SIGNIFICANT_DROP = "significant_drop"
    SEVERE_DROP = "severe_drop"
    LOW_VEGETATION = "low_vegetation"
    PROLONGED_DECLINE = "prolonged_decline"


class NDVIAnomalyStatusEnum(str, Enum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"


# ---------------------------------------------------------------------------
# NDVI Observation schemas
# ---------------------------------------------------------------------------


class NDVIObservationResponse(BaseModel):
    """NDVI observation with computed health category."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plot_id: UUID
    observed_at: datetime
    source: NDVISourceEnum
    ndvi_mean: Decimal
    ndvi_min: Decimal
    ndvi_max: Decimal
    ndvi_stddev: Decimal
    cloud_cover_pct: Decimal
    valid_pixel_count: int
    total_pixel_count: int
    raster_url: str | None
    thumbnail_url: str | None
    created_at: datetime
    health_category: str = Field(..., description="healthy, moderate, sparse, bare")
    is_cloudy: bool = Field(..., description="True if cloud cover > 30%")
    raster_download_url: str | None = Field(
        default=None,
        description="Pre-signed S3 URL for raster download (15-min validity)",
    )


class NDVIHistoryResponse(BaseModel):
    """Time series of NDVI observations for a plot."""

    plot_id: UUID
    observations: list[NDVIObservationResponse]
    total: int
    latest_health: str | None = None
    trend: str | None = Field(
        default=None,
        description="improving, declining, stable, insufficient_data",
    )


class NDVIRefreshResponse(BaseModel):
    """Response from a manual NDVI refresh request."""

    plot_id: UUID
    status: str  # "queued", "completed", "failed"
    observation_id: UUID | None = None
    ndvi_mean: Decimal | None = None
    health_category: str | None = None
    cloud_cover_pct: Decimal | None = None
    message: str | None = None


# ---------------------------------------------------------------------------
# NDVI Anomaly Alert schemas
# ---------------------------------------------------------------------------


class NDVIAnomalyAlertResponse(BaseModel):
    """NDVI anomaly alert for a plot."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plot_id: UUID
    farmer_id: UUID
    anomaly_type: NDVIAnomalyTypeEnum
    status: NDVIAnomalyStatusEnum
    previous_ndvi: Decimal
    current_ndvi: Decimal
    drop_magnitude: Decimal
    drop_percentage: float
    created_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None
    resolution_notes: str | None


class NDVIAnomalyListResponse(BaseModel):
    """List of NDVI anomaly alerts."""

    alerts: list[NDVIAnomalyAlertResponse]
    total: int


class NDVIAnomalyAcknowledge(BaseModel):
    """Request body for acknowledging an NDVI anomaly alert."""

    resolution_notes: str | None = Field(default=None, max_length=2000)


# ---------------------------------------------------------------------------
# District heatmap (officer view)
# ---------------------------------------------------------------------------


class DistrictNDVIStat(BaseModel):
    """NDVI statistics for a single district (heatmap entry)."""

    district: str
    state: str
    avg_ndvi: Decimal | None
    min_ndvi: Decimal | None
    max_ndvi: Decimal | None
    plot_count: int
    healthy_plots: int
    moderate_plots: int
    sparse_plots: int
    bare_plots: int
    active_anomalies: int


class DistrictNDVIHeatmapResponse(BaseModel):
    """District-level NDVI heatmap for officers."""

    state: str | None = None
    districts: list[DistrictNDVIStat]
    total_plots: int
    avg_ndvi: Decimal | None
    generated_at: datetime


# ---------------------------------------------------------------------------
# Plot NDVI summary
# ---------------------------------------------------------------------------


class PlotNDVISummaryResponse(BaseModel):
    """Aggregated NDVI summary for a plot (latest + trend + alerts)."""

    plot_id: UUID
    plot_name: str
    latest_observation: NDVIObservationResponse | None
    previous_observation: NDVIObservationResponse | None
    trend: str  # improving, declining, stable, insufficient_data
    trend_change: float | None = Field(
        default=None,
        description="NDVI change from previous observation (positive = improving)",
    )
    active_anomalies: list[NDVIAnomalyAlertResponse] = Field(default_factory=list)
    history: list[NDVIObservationResponse] = Field(
        default_factory=list,
        description="Last 12 observations for time-series chart",
    )
