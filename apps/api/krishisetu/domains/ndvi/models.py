"""SQLAlchemy ORM models for the NDVI domain.

Tables:
- intelligence.ndvi_observations    (per-plot NDVI stats, partitioned monthly)
- intelligence.ndvi_rasters         (S3-hosted GeoTIFF references)
- intelligence.ndvi_anomaly_alerts  (NDVI drop alerts for farmers)

Design notes:
- ndvi_observations is RANGE-partitioned by observed_at (monthly) for
  time-series query performance at scale
- Each observation stores summary stats (mean, min, max, stddev) plus a
  reference to the full raster stored in S3
- Anomaly alerts are generated when NDVI drops by more than 0.15 between
  consecutive observations
- The raster_url stores an S3 object key; pre-signed URLs are generated
  on demand for client access
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import ClassVar
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from krishisetu.core.database import Base

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class NDVISource(str, Enum):
    """Source of NDVI imagery."""

    SENTINEL2 = "sentinel2"   # Sentinel-2 L2A (primary, 10m, 5-day revisit)
    LANDSAT8 = "landsat8"     # Landsat 8/9 (backup, 30m, 16-day revisit)
    SYNTHETIC = "synthetic"   # Dev mode synthetic data


class NDVIAnomalyType(str, Enum):
    """Type of NDVI anomaly."""

    SIGNIFICANT_DROP = "significant_drop"      # > 0.15 drop
    SEVERE_DROP = "severe_drop"                # > 0.30 drop
    LOW_VEGETATION = "low_vegetation"          # NDVI < 0.2 (bare soil)
    PROLONGED_DECLINE = "prolonged_decline"    # 3+ consecutive drops


class NDVIAnomalyStatus(str, Enum):
    """Status of an NDVI anomaly alert."""

    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"  # Farmer has seen the alert
    INVESTIGATING = "investigating"  # Farmer submitted a disease report
    RESOLVED = "resolved"            # Issue resolved (harvest, treatment, etc.)


# ---------------------------------------------------------------------------
# NDVIObservation
# ---------------------------------------------------------------------------


class NDVIObservation(Base):
    """NDVI observation for a plot at a specific time.

    Stores summary statistics computed from the full NDVI raster. The raster
    itself is stored in S3 (raster_url) and served via pre-signed URLs.

    Partitioned by month (RANGE on observed_at) for efficient time-series
    queries. With 1M plots x weekly observations x 2 years = ~100M rows,
    partitioning is essential.
    """

    __tablename__ = "ndvi_observations"
    __table_args__ = (
        UniqueConstraint(
            "plot_id", "observed_at", "source",
            name="ndvi_obs_plot_time_source_unique"
        ),
        {"schema": "intelligence"},
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, primary_key=True
    )
    plot_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("farmer.plots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Time of observation (satellite pass time)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    # Source
    source: Mapped[NDVISource] = mapped_column(
        String(20), nullable=False, default=NDVISource.SENTINEL2
    )

    # NDVI statistics (computed from raster)
    ndvi_mean: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        comment="Mean NDVI across the plot (-1 to 1)",
    )
    ndvi_min: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), nullable=False, comment="Minimum NDVI (worst pixel)"
    )
    ndvi_max: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), nullable=False, comment="Maximum NDVI (best pixel)"
    )
    ndvi_stddev: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        comment="Standard deviation (uniformity indicator)",
    )

    # Cloud cover
    cloud_cover_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        comment="Percentage of plot area obscured by clouds",
    )

    # Pixel statistics
    valid_pixel_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Number of valid (non-cloud) pixels in the plot",
    )
    total_pixel_count: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Total pixels in the plot"
    )

    # Raster storage
    raster_url: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        comment="S3 object key for the NDVI raster GeoTIFF",
    )
    thumbnail_url: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        comment="S3 key for PNG thumbnail (for quick preview)",
    )

    # Raw data
    raw_metadata: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Original satellite metadata (tile ID, processing baseline, etc.)",
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.NOW(), nullable=False
    )

    # Relationship
    plot = relationship("Plot", backref="ndvi_observations", lazy="selectin")

    @property
    def health_category(self) -> str:
        """Categorize NDVI mean into a health label.

        - healthy: NDVI >= 0.6
        - moderate: 0.3 <= NDVI < 0.6
        - sparse: 0.1 <= NDVI < 0.3
        - bare: NDVI < 0.1
        """
        ndvi = float(self.ndvi_mean)
        if ndvi >= 0.6:
            return "healthy"
        if ndvi >= 0.3:
            return "moderate"
        if ndvi >= 0.1:
            return "sparse"
        return "bare"

    @property
    def is_cloudy(self) -> bool:
        """Whether cloud cover exceeds usable threshold (>30%)."""
        return float(self.cloud_cover_pct) > 30.0

    def __repr__(self) -> str:
        return (
            f"<NDVIObservation plot={self.plot_id} "
            f"time={self.observed_at} mean={self.ndvi_mean}>"
        )


# ---------------------------------------------------------------------------
# NDVIAnomalyAlert
# ---------------------------------------------------------------------------


class NDVIAnomalyAlert(Base):
    """Alert for NDVI anomaly (significant drop, low vegetation, etc.).

    Generated by the NDVI computation pipeline when:
    - NDVI drops by more than 0.15 between consecutive observations
    - NDVI falls below 0.2 (bare soil when crop is expected)
    - 3+ consecutive observations show declining NDVI

    Lifecycle:
    - ACTIVE: Alert created, farmer notified
    - ACKNOWLEDGED: Farmer has seen the alert
    - INVESTIGATING: Farmer submitted a disease report for the plot
    - RESOLVED: Issue resolved (harvest, treatment, etc.)
    """

    __tablename__ = "ndvi_anomaly_alerts"
    __table_args__: ClassVar[dict[str, str]] = {"schema": "intelligence"}

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        server_default=func.gen_random_uuid(),
        primary_key=True,
        nullable=False,
    )
    plot_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("farmer.plots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    farmer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("identity.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Anomaly details
    anomaly_type: Mapped[NDVIAnomalyType] = mapped_column(
        String(30), nullable=False, index=True
    )
    status: Mapped[NDVIAnomalyStatus] = mapped_column(
        String(20),
        server_default=func.text("'active'"),
        nullable=False,
        default=NDVIAnomalyStatus.ACTIVE,
        index=True,
    )

    # NDVI values that triggered the alert
    previous_ndvi: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), nullable=False, comment="Previous observation NDVI mean"
    )
    current_ndvi: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), nullable=False, comment="Current observation NDVI mean"
    )
    drop_magnitude: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        comment="Absolute NDVI drop (previous - current)",
    )

    # Observation references
    previous_observation_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    current_observation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False
    )

    # Notification
    notification_sent: Mapped[bool] = mapped_column(
        String(10),  # Storing as string for partitioned table compatibility
        server_default=func.text("'false'"),
        nullable=False,
        default=False,
    )
    notification_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Acknowledgment
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolution_notes: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Farmer's notes on resolution"
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.NOW(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.NOW(), nullable=False
    )

    @property
    def drop_percentage(self) -> float:
        """NDVI drop as a percentage of previous value."""
        prev = float(self.previous_ndvi)
        if prev <= 0:
            return 0.0
        return abs(float(self.drop_magnitude) / prev) * 100

    def __repr__(self) -> str:
        return (
            f"<NDVIAnomalyAlert plot={self.plot_id} "
            f"type={self.anomaly_type} drop={self.drop_magnitude}>"
        )
