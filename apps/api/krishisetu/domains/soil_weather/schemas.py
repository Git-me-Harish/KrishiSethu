"""Pydantic schemas for the soil_weather domain.

API contracts for:
- Soil test CRUD (create, list, get, update)
- Soil test manual entry from lab
- SHC (Soil Health Card) import
- Current weather (per-plot, per-district)
- 7-day forecast
- Historical weather (paginated)
- Weather alerts (active, by district)
- Weather alert subscription preferences
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SoilTestSourceEnum(str, Enum):
    SHC_PORTAL = "shc_portal"
    LAB_MANUAL = "lab_manual"
    ISRIC_AUTO = "isric_auto"
    OFFICER_ENTERED = "officer_entered"


class WeatherAlertTypeEnum(str, Enum):
    FROST = "frost"
    HAIL = "hail"
    HEAT_WAVE = "heat_wave"
    HEAVY_RAIN = "heavy_rain"
    CYCLONE = "cyclone"
    DROUGHT = "drought"
    HIGH_WIND = "high_wind"
    FOG = "fog"


class WeatherAlertSeverityEnum(str, Enum):
    INFO = "info"
    WARNING = "warning"
    SEVERE = "severe"
    CRITICAL = "critical"


class WeatherAlertStatusEnum(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# Soil test schemas
# ---------------------------------------------------------------------------


class SoilTestCreate(BaseModel):
    """Request body for POST /plots/{id}/soil-tests (manual entry)."""

    test_date: date = Field(..., description="Date the soil sample was collected")
    lab_name: str | None = Field(
        default=None, max_length=255, description="Lab that performed the test"
    )

    # Nutrients (optional — farmer may not have all values)
    nitrogen_n: Decimal | None = Field(
        default=None, ge=0, le=1000, description="Available N (kg/ha)"
    )
    phosphorus_p: Decimal | None = Field(
        default=None, ge=0, le=1000, description="Available P (kg/ha, as P2O5)"
    )
    potassium_k: Decimal | None = Field(
        default=None, ge=0, le=1000, description="Available K (kg/ha, as K2O)"
    )

    # Chemistry
    ph: Decimal | None = Field(default=None, ge=0, le=14, description="Soil pH (0-14)")
    electrical_conductivity: Decimal | None = Field(
        default=None, ge=0, le=20, description="EC (dS/m)"
    )
    organic_carbon: Decimal | None = Field(
        default=None, ge=0, le=100, description="Organic carbon (%)"
    )

    # Texture (must sum to 100 if provided)
    clay_pct: Decimal | None = Field(default=None, ge=0, le=100)
    sand_pct: Decimal | None = Field(default=None, ge=0, le=100)
    silt_pct: Decimal | None = Field(default=None, ge=0, le=100)

    # Micronutrients
    micronutrients: dict[str, Decimal] | None = Field(
        default=None,
        description='{"iron": 12.5, "zinc": 1.2, "copper": 0.8, "manganese": 5.5, "boron": 0.5}',
    )

    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_texture_sum(self) -> SoilTestCreate:
        """If texture percentages are provided, they must sum to ~100."""
        parts = [self.clay_pct, self.sand_pct, self.silt_pct]
        provided = [p for p in parts if p is not None]
        if len(provided) == 3:
            total = sum(provided)
            if not (95 <= total <= 105):
                raise ValueError(
                    f"Clay + Sand + Silt must sum to ~100, got {total}"
                )
        elif len(provided) > 0 and len(provided) < 3:
            raise ValueError(
                "If any texture percentage is provided, all three "
                "(clay, sand, silt) must be provided"
            )
        return self


class SHCImportRequest(BaseModel):
    """Request body for POST /plots/{id}/soil-tests/import-shc."""

    shc_id: str = Field(..., min_length=5, max_length=50, description="Soil Health Card ID")


class SoilTestResponse(BaseModel):
    """Soil test result with computed fertilizer recommendation."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plot_id: UUID
    source: SoilTestSourceEnum
    shc_id: str | None
    lab_name: str | None
    test_date: date
    nitrogen_n: Decimal | None
    phosphorus_p: Decimal | None
    potassium_k: Decimal | None
    ph: Decimal | None
    electrical_conductivity: Decimal | None
    organic_carbon: Decimal | None
    clay_pct: Decimal | None
    sand_pct: Decimal | None
    silt_pct: Decimal | None
    soil_type: str | None
    soil_texture: str | None
    micronutrients: dict[str, Decimal] | None
    fertilizer_recommendation: str | None
    amendment_recommendation: str | None
    is_verified: bool
    verified_by: UUID | None
    notes: str | None
    created_at: datetime
    updated_at: datetime

    @property
    def is_authoritative(self) -> bool:
        return self.source in (
            SoilTestSourceEnum.SHC_PORTAL,
            SoilTestSourceEnum.OFFICER_ENTERED,
        )


class SoilTestListResponse(BaseModel):
    """Paginated soil test listing."""

    tests: list[SoilTestResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


# ---------------------------------------------------------------------------
# Weather schemas
# ---------------------------------------------------------------------------


class CurrentWeatherResponse(BaseModel):
    """Current weather conditions for a plot or district."""

    # Location
    district: str
    state: str
    plot_id: UUID | None = None  # If requested for a specific plot

    # Conditions
    temperature_c: Decimal
    feels_like_c: Decimal
    temp_min_c: Decimal
    temp_max_c: Decimal
    precipitation_mm: Decimal
    humidity_pct: Decimal
    wind_speed_kmph: Decimal
    wind_direction_deg: Decimal
    pressure_hpa: Decimal
    cloud_cover_pct: Decimal
    weather_main: str
    weather_description: str
    weather_icon: str
    observed_at: datetime
    sunrise_at: datetime | None = None
    sunset_at: datetime | None = None
    source: str  # "imd", "owm", "synthetic"

    # Derived advisory
    agromet_advisory: str | None = None


class DailyForecastResponse(BaseModel):
    """Single day of a 7-day forecast."""

    forecast_date: date
    temp_min_c: Decimal
    temp_max_c: Decimal
    precipitation_mm: Decimal
    precipitation_probability: Decimal
    humidity_min_pct: Decimal
    humidity_max_pct: Decimal
    wind_speed_kmph: Decimal
    wind_direction_deg: Decimal
    weather_main: str
    weather_description: str
    weather_icon: str
    agromet_advisory: str | None = None
    source: str


class ForecastResponse(BaseModel):
    """7-day forecast response."""

    district: str
    state: str
    plot_id: UUID | None = None
    forecasts: list[DailyForecastResponse]
    issued_at: datetime


class WeatherHistoryResponse(BaseModel):
    """Paginated weather history."""

    district: str
    state: str
    plot_id: UUID | None = None
    observations: list[CurrentWeatherResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


class WeatherAlertResponse(BaseModel):
    """Extreme weather alert."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    district: str
    state: str
    alert_type: WeatherAlertTypeEnum
    severity: WeatherAlertSeverityEnum
    status: WeatherAlertStatusEnum
    effective_at: datetime
    expires_at: datetime
    title: str
    description: str
    recommended_actions: str | None
    source: str
    notifications_sent: int
    created_at: datetime


class WeatherAlertListResponse(BaseModel):
    """List of weather alerts."""

    alerts: list[WeatherAlertResponse]
    total: int


class WeatherSyncStatusResponse(BaseModel):
    """Status of the most recent weather sync (for admin/debugging)."""

    last_sync_at: datetime | None
    districts_synced: int
    observations_stored: int
    next_sync_at: datetime | None
    source: str


# ---------------------------------------------------------------------------
# Plot-level weather aggregation
# ---------------------------------------------------------------------------


class PlotWeatherSummaryResponse(BaseModel):
    """Aggregated weather summary for a farmer's plots."""

    plot_id: UUID
    plot_name: str
    district: str
    state: str
    current: CurrentWeatherResponse
    forecast: list[DailyForecastResponse]
    active_alerts: list[WeatherAlertResponse]
