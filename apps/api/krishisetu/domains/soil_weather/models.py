"""SQLAlchemy ORM models for the soil_weather domain.

Tables:
- intelligence.soil_tests            (per-plot soil test results)
- intelligence.weather_observations  (time-series weather data per district)
- intelligence.weather_forecasts     (7-day forecasts per district)
- intelligence.weather_alerts        (extreme weather alerts for plots/districts)

Design notes:
- weather_observations and weather_forecasts are partitioned by month
  (RANGE on observed_at) for query performance at scale
- District is the spatial key (not plot) for weather — interpolation to
  plot level happens at query time using plot centroid
- Soil tests can come from three sources: SHC portal, manual entry, ISRIC
  auto-populate. Each has different validation and trust level.
- Weather alerts support multiple severities (info, warning, severe, critical)
  and types (frost, hail, heat_wave, heavy_rain, cyclone, drought)
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from krishisetu.core.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SoilTestSource(str, Enum):
    """Source of soil test data."""

    SHC_PORTAL = "shc_portal"        # Official Soil Health Card
    LAB_MANUAL = "lab_manual"        # Manual entry from any lab
    ISRIC_AUTO = "isric_auto"        # Auto-populated from ISRIC SoilGrids
    OFFICER_ENTERED = "officer_entered"


class WeatherDataSource(str, Enum):
    """Source of weather data."""

    IMD = "imd"               # India Meteorological Department (primary)
    OWM = "owm"               # OpenWeatherMap (fallback)
    SENTINEL = "sentinel"     # Sentinel Hub (satellite-derived)


class WeatherAlertType(str, Enum):
    """Type of extreme weather alert."""

    FROST = "frost"
    HAIL = "hail"
    HEAT_WAVE = "heat_wave"
    HEAVY_RAIN = "heavy_rain"
    CYCLONE = "cyclone"
    DROUGHT = "drought"
    HIGH_WIND = "high_wind"
    FOG = "fog"


class WeatherAlertSeverity(str, Enum):
    """Severity of a weather alert."""

    INFO = "info"          # Awareness, no action needed
    WARNING = "warning"    # Prepare for action
    SEVERE = "severe"      # Take action now
    CRITICAL = "critical"  # Life-threatening, immediate action


class WeatherAlertStatus(str, Enum):
    """Status of a weather alert (lifecycle)."""

    ACTIVE = "active"      # Alert is in effect
    EXPIRED = "expired"    # Alert period has passed
    CANCELLED = "cancelled"  # Alert withdrawn by source


# ---------------------------------------------------------------------------
# SoilTest
# ---------------------------------------------------------------------------


class SoilTest(Base):
    """Soil test results for a plot.

    A plot can have multiple soil tests over time (history). The most recent
    test is considered authoritative.

    Sources:
    - SHC_PORTAL: Fetched from the official Soil Health Card portal by SHC ID.
      Most authoritative — official government lab results.
    - LAB_MANUAL: Farmer enters results from any soil testing lab. Moderate trust.
    - ISRIC_AUTO: Auto-populated from ISRIC SoilGrids at plot registration.
      Lowest trust — global 250m resolution predictions, not actual lab tests.
    - OFFICER_ENTERED: Agricultural officer enters results after field visit.

    Nutrient values use standard units:
    - N, P, K: kg/ha (kilograms per hectare)
    - pH: 0-14 scale
    - EC (electrical conductivity): dS/m (decisiemens per meter)
    - OC (organic carbon): %
    - Micronutrients (Fe, Zn, Cu, Mn, B): ppm (parts per million)
    """

    __tablename__ = "soil_tests"
    __table_args__ = (
        UniqueConstraint(
            "plot_id", "test_date", "source", name="soil_tests_plot_date_source_unique"
        ),
        {"schema": "intelligence"},
    )

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

    # Source
    source: Mapped[SoilTestSource] = mapped_column(
        String(30),
        nullable=False,
        index=True,
        comment="shc_portal, lab_manual, isric_auto, officer_entered",
    )
    shc_id: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Soil Health Card ID (if source=shc_portal)",
    )
    lab_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Lab name (if source=lab_manual)",
    )

    # Test date
    test_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
        index=True,
        comment="Date the sample was collected (not the date entered)",
    )

    # Primary nutrients (kg/ha)
    nitrogen_n: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 2), nullable=True, comment="Available nitrogen (kg/ha)"
    )
    phosphorus_p: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 2), nullable=True, comment="Available phosphorus (kg/ha, as P2O5)"
    )
    potassium_k: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 2), nullable=True, comment="Available potassium (kg/ha, as K2O)"
    )

    # Soil chemistry
    ph: Mapped[Decimal | None] = mapped_column(
        Numeric(4, 2), nullable=True, comment="Soil pH (0-14 scale)"
    )
    electrical_conductivity: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 3), nullable=True, comment="EC in dS/m (decisiemens per meter)"
    )
    organic_carbon: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True, comment="Organic carbon percentage (%)"
    )

    # Physical properties (ISRIC provides these)
    clay_pct: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True, comment="Clay percentage (0-100)"
    )
    sand_pct: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True, comment="Sand percentage (0-100)"
    )
    silt_pct: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True, comment="Silt percentage (0-100)"
    )

    # Soil type classification
    soil_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Soil type classification (e.g., 'Acrisols', 'Vertisols')",
    )
    soil_texture: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        comment="Texture class: sandy, loamy, clayey, silty, etc.",
    )

    # Micronutrients (ppm)
    micronutrients: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment='{"iron": 12.5, "zinc": 1.2, "copper": 0.8, "manganese": 5.5, "boron": 0.5}',
    )

    # Recommendations
    fertilizer_recommendation: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="NPK dosage recommendation based on test results",
    )
    amendment_recommendation: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Soil amendment recommendation (lime for acidic, gypsum for alkaline, etc.)",
    )

    # Trust/metadata
    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        server_default=func.text("false"),
        nullable=False,
        default=False,
        comment="Officer-verified test results",
    )
    verified_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("identity.users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Notes
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.NOW(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.NOW(), nullable=False
    )

    # Relationship
    plot = relationship("Plot", backref="soil_tests", lazy="selectin")

    @property
    def is_authoritative(self) -> bool:
        """Whether this test is from an authoritative source."""
        return self.source in (SoilTestSource.SHC_PORTAL, SoilTestSource.OFFICER_ENTERED)

    def __repr__(self) -> str:
        return f"<SoilTest plot={self.plot_id} date={self.test_date} source={self.source}>"


# ---------------------------------------------------------------------------
# WeatherObservation (current/historical conditions)
# ---------------------------------------------------------------------------


class WeatherObservation(Base):
    """Weather observation for a district at a specific time.

    Stored at district level (not plot) for efficiency — India has ~718
    districts, each gets ~24 observations per day (hourly). With 7 years
    of history, that's ~4.4M rows — partitioning is essential.

    Plot-level weather is computed at query time by interpolating from
    the nearest district observations using plot centroid.

    Source priority: IMD > OWM > Sentinel. If multiple sources report
    for the same (district, observed_at), the higher-priority source wins.
    """

    __tablename__ = "weather_observations"
    __table_args__ = (
        UniqueConstraint(
            "district", "state", "observed_at", "source",
            name="weather_obs_district_time_source_unique"
        ),
        {"schema": "intelligence"},
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        server_default=func.gen_random_uuid(),
        primary_key=True,
        nullable=False,
    )

    # Location (district-level)
    district: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # Centroid of the district for proximity queries
    district_centroid_lon: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 6), nullable=True
    )
    district_centroid_lat: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 6), nullable=True
    )

    # Time
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    # Source
    source: Mapped[WeatherDataSource] = mapped_column(
        String(20), nullable=False, default=WeatherDataSource.IMD
    )

    # Temperature (°C)
    temperature_c: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    feels_like_c: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    temp_min_c: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    temp_max_c: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)

    # Precipitation (mm)
    precipitation_mm: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 2), nullable=True, comment="Precipitation in mm for the observation period"
    )
    precipitation_probability: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True, comment="Probability of precipitation (0-100)"
    )

    # Humidity (%)
    humidity_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)

    # Wind
    wind_speed_kmph: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 2), nullable=True, comment="Wind speed in km/h"
    )
    wind_direction_deg: Mapped[Decimal | None] = mapped_column(
        Numeric(6, 2), nullable=True, comment="Wind direction in degrees (0-360)"
    )
    wind_gust_kmph: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)

    # Atmospheric
    pressure_hpa: Mapped[Decimal | None] = mapped_column(
        Numeric(7, 1), nullable=True, comment="Atmospheric pressure in hPa"
    )
    cloud_cover_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    visibility_km: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    uv_index: Mapped[Decimal | None] = mapped_column(Numeric(4, 1), nullable=True)

    # Conditions (text + code)
    weather_main: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="Rain, Clear, Clouds, Thunderstorm, etc."
    )
    weather_description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    weather_icon: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Sunrise/sunset (only on the first observation of the day)
    sunrise_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sunset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Raw data (for debugging and re-processing)
    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.NOW(), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<WeatherObservation district={self.district} "
            f"time={self.observed_at} source={self.source}>"
        )


# ---------------------------------------------------------------------------
# WeatherForecast (7-day)
# ---------------------------------------------------------------------------


class WeatherForecast(Base):
    """Daily weather forecast for a district.

    IMD provides 7-day forecasts. We store each day as a separate row for
    efficient querying by date range.

    Forecasts are updated every 6 hours (4 times per day). Old forecasts
    are retained for verification (compare forecast vs actual).
    """

    __tablename__ = "weather_forecasts"
    __table_args__ = (
        UniqueConstraint(
            "district", "state", "forecast_date", "source", "issued_at",
            name="weather_fcst_district_date_source_issued_unique"
        ),
        {"schema": "intelligence"},
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        server_default=func.gen_random_uuid(),
        primary_key=True,
        nullable=False,
    )

    # Location
    district: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Forecast target date (the day this forecast is FOR)
    forecast_date: Mapped[date] = mapped_column(
        Date, nullable=False, index=True
    )

    # When this forecast was issued (by the source)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    # Source
    source: Mapped[WeatherDataSource] = mapped_column(
        String(20), nullable=False, default=WeatherDataSource.IMD
    )

    # Temperature (°C)
    temp_min_c: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    temp_max_c: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)

    # Precipitation
    precipitation_mm: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    precipitation_probability: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)

    # Humidity
    humidity_min_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    humidity_max_pct: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)

    # Wind
    wind_speed_kmph: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    wind_direction_deg: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)

    # Conditions
    weather_main: Mapped[str | None] = mapped_column(String(50), nullable=True)
    weather_description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    weather_icon: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Advisory
    agromet_advisory: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="IMD agromet advisory text for farmers",
    )

    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.NOW(), nullable=False
    )

    @property
    def is_today(self) -> bool:
        from datetime import date as date_cls

        return self.forecast_date == date_cls.today()

    def __repr__(self) -> str:
        return f"<WeatherForecast district={self.district} date={self.forecast_date}>"


# ---------------------------------------------------------------------------
# WeatherAlert (extreme weather)
# ---------------------------------------------------------------------------


class WeatherAlert(Base):
    """Extreme weather alert for a district or plot.

    Generated by Celery Beat job (every 3 hours) that checks forecasts
    against thresholds. When an alert is generated:
    1. Stored in this table
    2. Push notification dispatched to all farmers with plots in the affected district
    3. SMS dispatched for severe/critical alerts
    4. Voice advisory dispatched for critical alerts (in farmer's preferred language)

    Lifecycle:
    - ACTIVE: Alert is in effect (within forecast period)
    - EXPIRED: Alert period has passed (auto-updated by Celery Beat)
    - CANCELLED: Source withdrew the alert (rare)
    """

    __tablename__ = "weather_alerts"
    __table_args__ = {"schema": "intelligence"}

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        server_default=func.gen_random_uuid(),
        primary_key=True,
        nullable=False,
    )

    # Location
    district: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Alert details
    alert_type: Mapped[WeatherAlertType] = mapped_column(
        String(30), nullable=False, index=True
    )
    severity: Mapped[WeatherAlertSeverity] = mapped_column(
        String(20), nullable=False, index=True
    )
    status: Mapped[WeatherAlertStatus] = mapped_column(
        String(20),
        server_default=func.text("'active'"),
        nullable=False,
        default=WeatherAlertStatus.ACTIVE,
        index=True,
    )

    # Timing
    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="When the alert takes effect"
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, comment="When the alert expires"
    )

    # Content
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_actions: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Specific actions farmers should take (harvest now, cover crops, etc.)",
    )

    # Source
    source: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="krishisetu_engine",
        comment="krishisetu_engine, imd, owm",
    )
    raw_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Notification dispatch tracking
    notifications_sent: Mapped[int] = mapped_column(
        Integer, server_default=func.text("0"), nullable=False, default=0
    )
    last_notification_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.NOW(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.NOW(), nullable=False
    )

    @property
    def is_active(self) -> bool:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        return self.status == WeatherAlertStatus.ACTIVE and self.effective_at <= now < self.expires_at

    def __repr__(self) -> str:
        return (
            f"<WeatherAlert district={self.district} type={self.alert_type} "
            f"severity={self.severity} status={self.status}>"
        )
