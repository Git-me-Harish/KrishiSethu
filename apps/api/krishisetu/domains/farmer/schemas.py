"""Pydantic schemas for the farmer domain.

These schemas define the API contract for plot management. The key challenge
is handling GeoJSON for plot boundaries — the API accepts GeoJSON
Polygon from the frontend, converts to PostGIS GEOGRAPHY for storage,
and returns GeoJSON on read.

GeoJSON Polygon format:
    {
        "type": "Polygon",
        "coordinates": [
            [[lon, lat], [lon, lat], ..., [lon, lat]]  // First ring (exterior)
            // Optional: additional rings (holes)
        ]
    }

The first and last coordinate of each ring MUST be identical (closed ring).
Coordinates are [longitude, latitude] in WGS84 (EPSG:4326).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# GeoJSON types
# ---------------------------------------------------------------------------


class GeoJSONPosition(BaseModel):
    """A GeoJSON position [longitude, latitude] or [lon, lat, altitude]."""

    type: Literal["Position"] = "Position"


class GeoJSONPolygon(BaseModel):
    """A GeoJSON Polygon geometry.

    Coordinates is an array of linear ring coordinate arrays. The first ring
    is the exterior ring (boundary), subsequent rings are holes.

    Each ring must be closed (first and last coordinate identical) and have
    at least 4 positions (3 unique points + closing point).
    """

    type: Literal["Polygon"] = "Polygon"
    coordinates: list[list[list[float]]] = Field(
        ...,
        description="Array of linear rings. Each ring is an array of [lon, lat] positions.",
        min_length=1,
    )

    @field_validator("coordinates")
    @classmethod
    def validate_polygon(cls, v: list[list[list[float]]]) -> list[list[list[float]]]:
        if not v:
            raise ValueError("Polygon must have at least one ring")

        for ring_idx, ring in enumerate(v):
            ring_type = "exterior ring" if ring_idx == 0 else f"hole {ring_idx}"
            if len(ring) < 4:
                raise ValueError(
                    f"Polygon {ring_type} must have at least 4 positions (3 unique + closing), got {len(ring)}"
                )

            # Check ring is closed
            if ring[0] != ring[-1]:
                raise ValueError(f"Polygon {ring_type} must be closed (first and last position identical)")

            # Validate each position has 2 or 3 coordinates
            for pos_idx, pos in enumerate(ring):
                if len(pos) < 2 or len(pos) > 3:
                    raise ValueError(
                        f"Position {pos_idx} in {ring_type} must have 2 or 3 coordinates, got {len(pos)}"
                    )
                lon, lat = pos[0], pos[1]
                if not -180 <= lon <= 180:
                    raise ValueError(f"Longitude must be in [-180, 180], got {lon}")
                if not -90 <= lat <= 90:
                    raise ValueError(f"Latitude must be in [-90, 90], got {lat}")

        return v


class GeoJSONFeature(BaseModel):
    """A GeoJSON Feature with Polygon geometry (used for plot responses)."""

    type: Literal["Feature"] = "Feature"
    geometry: GeoJSONPolygon
    properties: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Enums (mirror of model enums, exposed for OpenAPI)
# ---------------------------------------------------------------------------


class IrrigationSourceEnum(str, Enum):
    CANAL = "canal"
    BOREWELL = "borewell"
    RIVER = "river"
    RAINFED = "rainfed"
    DRIP = "drip"
    SPRINKLER = "sprinkler"
    TANK = "tank"
    OTHER = "other"


class OwnershipTypeEnum(str, Enum):
    OWNED = "owned"
    LEASED = "leased"
    SHARED = "shared"


class VerificationStatusEnum(str, Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"
    RESUBMISSION_REQUESTED = "resubmission_requested"


class CropSeasonEnum(str, Enum):
    KHARIF = "kharif"
    RABI = "rabi"
    ZAID = "zaid"


class CropCycleStatusEnum(str, Enum):
    PLANNED = "planned"
    SOWN = "sown"
    GROWING = "growing"
    HARVESTED = "harvested"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Plot schemas
# ---------------------------------------------------------------------------


class PlotCreate(BaseModel):
    """Request body for POST /plots."""

    survey_number: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="State land record identifier (e.g., 'Survey No. 142/3')",
    )
    village: str = Field(..., min_length=1, max_length=255)
    district: str = Field(..., min_length=1, max_length=100)
    state: str = Field(..., min_length=1, max_length=100)
    pincode: str | None = Field(
        default=None,
        pattern=r"^[1-9][0-9]{5}$",
        description="6-digit Indian pincode",
    )
    boundary: GeoJSONPolygon = Field(
        ...,
        description="Plot boundary as GeoJSON Polygon in WGS84 (EPSG:4326)",
    )
    irrigation_source: IrrigationSourceEnum | None = None
    ownership_type: OwnershipTypeEnum = Field(default=OwnershipTypeEnum.OWNED)
    lessor_name: str | None = Field(default=None, max_length=255)
    lease_start_date: date | None = None
    lease_end_date: date | None = None
    nickname: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def validate_lease_fields(self) -> PlotCreate:
        """If ownership_type is leased, lessor_name and lease dates are required."""
        if self.ownership_type == OwnershipTypeEnum.LEASED:
            if not self.lessor_name:
                raise ValueError("lessor_name is required for leased plots")
            if not self.lease_start_date or not self.lease_end_date:
                raise ValueError("lease_start_date and lease_end_date are required for leased plots")
            if self.lease_end_date <= self.lease_start_date:
                raise ValueError("lease_end_date must be after lease_start_date")
        return self


class PlotUpdate(BaseModel):
    """Request body for PATCH /plots/{id} (partial update)."""

    nickname: str | None = Field(default=None, max_length=100)
    irrigation_source: IrrigationSourceEnum | None = None
    pincode: str | None = Field(default=None, pattern=r"^[1-9][0-9]{5}$")


class PlotBoundaryUpdate(BaseModel):
    """Request body for PUT /plots/{id}/boundary (redraw boundary)."""

    boundary: GeoJSONPolygon
    source: Literal["user_drawn", "officer_corrected"] = "user_drawn"


class PlotResponse(BaseModel):
    """Plot representation with GeoJSON boundary."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    farmer_id: UUID
    survey_number: str
    village: str
    district: str
    state: str
    pincode: str | None
    area_ha: Decimal
    boundary: GeoJSONPolygon
    centroid: dict[str, float] | None = Field(
        default=None,
        description="Centroid as {lon, lat} for proximity queries",
    )
    soil_type: str | None
    soil_ph: Decimal | None
    irrigation_source: IrrigationSourceEnum | None
    ownership_type: OwnershipTypeEnum
    lessor_name: str | None
    lease_start_date: date | None
    lease_end_date: date | None
    verification_status: VerificationStatusEnum
    verified_by: UUID | None
    verified_at: datetime | None
    verification_notes: str | None
    nickname: str | None
    created_at: datetime
    updated_at: datetime

    @property
    def display_name(self) -> str:
        if self.nickname:
            return self.nickname
        return f"Plot {self.survey_number} — {self.village}"


class PlotListItem(BaseModel):
    """Compact plot representation for list views (no boundary geometry)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    survey_number: str
    village: str
    district: str
    state: str
    area_ha: Decimal
    verification_status: VerificationStatusEnum
    nickname: str | None
    centroid: dict[str, float] | None = None
    current_crop: str | None = Field(default=None, description="Currently growing crop name")
    current_crop_cycle_id: UUID | None = None
    created_at: datetime


class PlotListResponse(BaseModel):
    """Paginated response for plot listing."""

    plots: list[PlotListItem]
    total: int
    page: int
    page_size: int
    has_more: bool


# ---------------------------------------------------------------------------
# Crop schemas
# ---------------------------------------------------------------------------


class CropResponse(BaseModel):
    """Crop master data."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name_en: str
    name_hi: str | None
    scientific_name: str | None
    crop_category: str
    primary_season: CropSeasonEnum
    duration_days_min: int
    duration_days_max: int
    water_requirement_mm: int | None


class CropListResponse(BaseModel):
    """Paginated response for crop listing."""

    crops: list[CropResponse]
    total: int


# ---------------------------------------------------------------------------
# Crop cycle schemas
# ---------------------------------------------------------------------------


class CropCycleCreate(BaseModel):
    """Request body for POST /plots/{id}/crops."""

    crop_id: UUID
    season: CropSeasonEnum
    season_year: int = Field(..., ge=2000, le=2100)
    sowing_date: date | None = None
    expected_harvest_date: date | None = None
    area_ha: Decimal = Field(..., gt=0, description="Area under this crop (≤ plot area)")
    notes: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_dates(self) -> CropCycleCreate:
        if (
            self.sowing_date
            and self.expected_harvest_date
            and self.expected_harvest_date <= self.sowing_date
        ):
            raise ValueError("expected_harvest_date must be after sowing_date")
        return self


class CropCycleUpdate(BaseModel):
    """Request body for PATCH /crop-cycles/{id}."""

    sowing_date: date | None = None
    expected_harvest_date: date | None = None
    actual_harvest_date: date | None = None
    status: CropCycleStatusEnum | None = None
    notes: str | None = Field(default=None, max_length=2000)


class CropCycleResponse(BaseModel):
    """Crop cycle representation."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    plot_id: UUID
    crop_id: UUID
    crop_name: str | None = None  # Joined from crops table
    season: CropSeasonEnum
    season_year: int
    sowing_date: date | None
    expected_harvest_date: date | None
    actual_harvest_date: date | None
    area_ha: Decimal
    status: CropCycleStatusEnum
    notes: str | None
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Officer verification schemas
# ---------------------------------------------------------------------------


class OfficerVerifyPlot(BaseModel):
    """Request body for PATCH /officer/plots/{id}/verify."""

    status: Literal[VerificationStatusEnum.VERIFIED, VerificationStatusEnum.REJECTED, VerificationStatusEnum.RESUBMISSION_REQUESTED]
    notes: str | None = Field(default=None, max_length=2000)


class OfficerPlotListResponse(BaseModel):
    """Plots pending verification in officer's district."""

    plots: list[PlotListItem]
    total: int
    page: int
    page_size: int
    has_more: bool


class PlotStatsResponse(BaseModel):
    """Summary statistics for the current user's plots."""

    total_plots: int
    total_area_ha: Decimal
    verified_plots: int
    pending_verification: int
    rejected_plots: int
    leased_plots: int
    by_district: dict[str, int]
    current_season_crops: list[str]
