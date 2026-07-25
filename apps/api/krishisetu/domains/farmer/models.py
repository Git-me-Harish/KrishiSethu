"""SQLAlchemy ORM models for the farmer domain.

This module defines:
- Crop (master data: rice, wheat, cotton, etc. with growing seasons)
- PlotCategory (master data: agricultural, horticultural, plantations)
- Plot (farmer's registered plot with PostGIS boundary)
- PlotBoundary (historical boundary snapshots)
- CropCycle (crop grown on a plot during a season)

The Plot model uses PostGIS GEOGRAPHY type for boundary storage, enabling
spatial queries (find plots in district, compute area, check overlap).

All farmer-owned data has Row-Level Security (RLS) policies enforcing:
- Farmers can only access their own plots
- Agri officers can access plots in their assigned district
- Insurers can access plots with active insurance policies
- Admins have full access
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from geoalchemy2 import Geography
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
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from krishisetu.core.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class IrrigationSource(str, Enum):
    """Source of irrigation for a plot."""

    CANAL = "canal"
    BOREWELL = "borewell"
    RIVER = "river"
    RAINFED = "rainfed"
    DRIP = "drip"
    SPRINKLER = "sprinkler"
    TANK = "tank"
    OTHER = "other"


class PlotOwnershipType(str, Enum):
    """Ownership type for a plot."""

    OWNED = "owned"
    LEASED = "leased"
    SHARED = "shared"  # Joint ownership


class PlotVerificationStatus(str, Enum):
    """Verification status of a plot's ownership claim."""

    PENDING = "pending"
    VERIFIED = "verified"
    REJECTED = "rejected"
    RESUBMISSION_REQUESTED = "resubmission_requested"


class CropSeason(str, Enum):
    """Indian cropping seasons."""

    KHARIF = "kharif"  # June - October (monsoon)
    RABI = "rabi"  # November - March (winter)
    ZAID = "zaid" # April - June (summer)


class CropCycleStatus(str, Enum):
    """Status of a crop cycle."""

    PLANNED = "planned"
    SOWN = "sown"
    GROWING = "growing"
    HARVESTED = "harvested"
    FAILED = "failed"  # Crop failure (disease, weather, etc.)


# ---------------------------------------------------------------------------
# Master data: Crop
# ---------------------------------------------------------------------------


class Crop(Base):
    """Master data: crops grown in India.

    Includes both food crops (rice, wheat) and cash crops (cotton, sugarcane).
    Used for crop cycle registration and scheme eligibility.
    """

    __tablename__ = "crops"
    __table_args__ = {"schema": "farmer"}

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        server_default=func.gen_random_uuid(),
        primary_key=True,
        nullable=False,
    )
    slug: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        comment="URL-friendly identifier, e.g., 'rice', 'wheat', 'cotton'",
    )
    name_en: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="English name",
    )
    name_hi: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Hindi name (Devanagari)",
    )
    scientific_name: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="Botanical name, e.g., 'Oryza sativa'",
    )
    crop_category: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="cereals, pulses, oilseeds, fibre, sugar, plantation, horticulture, spices",
    )
    primary_season: Mapped[CropSeason] = mapped_column(
        String(20),
        nullable=False,
        comment="Primary growing season",
    )
    duration_days_min: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Minimum crop duration in days",
    )
    duration_days_max: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Maximum crop duration in days",
    )
    water_requirement_mm: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Total water requirement per season in mm",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        server_default=func.text("true"),
        nullable=False,
        default=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.NOW(),
        nullable=False,
    )

    # Relationship: crop cycles growing this crop
    crop_cycles: Mapped[list[CropCycle]] = relationship(
        "CropCycle", back_populates="crop"
    )

    def __repr__(self) -> str:
        return f"<Crop slug={self.slug} name={self.name_en}>"


# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------


class Plot(Base):
    """A farmer's registered plot with PostGIS boundary.

    The boundary is stored as GEOGRAPHY(POLYGON, 4326) — geographic coordinates
    in WGS84 (lat/lon). PostGIS provides:
    - ST_Area(): compute area in square meters
    - ST_Contains(): point-in-polygon queries
    - ST_Intersects(): overlap detection (prevent duplicate registration)
    - ST_Distance(): proximity queries (find nearby suppliers)

    A plot can have:
    - Multiple crop cycles over time (rotations across seasons)
    - One active crop cycle at a time (current growing season)
    - Multiple soil tests (history)
    - Multiple NDVI observations (time series)

    Ownership verification is performed by an agricultural officer who
    cross-references the survey number with state land records.
    """

    __tablename__ = "plots"
    __table_args__ = (
        UniqueConstraint(
            "farmer_id",
            "survey_number",
            "village",
            "district",
            "state",
            name="plots_farmer_survey_unique",
        ),
        {"schema": "farmer"},
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        server_default=func.gen_random_uuid(),
        primary_key=True,
        nullable=False,
    )
    farmer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("identity.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Owner of the plot (FK to identity.users)",
    )

    # --- Land record identifiers ---
    survey_number: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="State land record identifier (e.g., Survey No. 142/3)",
    )
    village: Mapped[str] = mapped_column(String(255), nullable=False)
    district: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="District name (used for officer assignment)",
    )
    state: Mapped[str] = mapped_column(String(100), nullable=False)
    pincode: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
        comment="6-digit Indian pincode",
    )

    # --- Geographic data ---
    area_ha: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        nullable=False,
        comment="Plot area in hectares (auto-computed from boundary on save)",
    )
    boundary: Mapped[object] = mapped_column(
        Geography(geometry_type="POLYGON", srid=4326),
        nullable=False,
        comment="Plot boundary as WGS84 polygon (lat/lon)",
    )
    centroid: Mapped[object] = mapped_column(
        Geography(geometry_type="POINT", srid=4326),
        nullable=True,
        comment="Auto-computed centroid for proximity queries",
    )

    # --- Soil & irrigation ---
    soil_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Auto-populated from ISRIC SoilGrids on registration",
    )
    soil_ph: Mapped[Decimal | None] = mapped_column(
        Numeric(4, 2),
        nullable=True,
        comment="Soil pH (auto from ISRIC or manual entry)",
    )
    irrigation_source: Mapped[IrrigationSource | None] = mapped_column(
        String(20),
        nullable=True,
        comment="Primary irrigation source",
    )

    # --- Ownership ---
    ownership_type: Mapped[PlotOwnershipType] = mapped_column(
        String(20),
        server_default=func.text("'owned'"),
        nullable=False,
        default=PlotOwnershipType.OWNED,
    )
    lessor_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Name of landowner (if leased)",
    )
    lease_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    lease_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # --- Verification ---
    verification_status: Mapped[PlotVerificationStatus] = mapped_column(
        String(30),
        server_default=func.text("'pending'"),
        nullable=False,
        default=PlotVerificationStatus.PENDING,
        index=True,
    )
    verified_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("identity.users.id", ondelete="SET NULL"),
        nullable=True,
    )
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    verification_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Officer notes during verification (rejection reasons, etc.)",
    )

    # --- Display name (farmer-assigned) ---
    nickname: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Farmer-friendly name, e.g., 'Back field near well'",
    )

    # --- Timestamps ---
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.NOW(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.NOW(),
        nullable=False,
    )

    # --- Relationships ---
    crop_cycles: Mapped[list[CropCycle]] = relationship(
        "CropCycle",
        back_populates="plot",
        cascade="all, delete-orphan",
    )
    boundary_history: Mapped[list[PlotBoundary]] = relationship(
        "PlotBoundary",
        back_populates="plot",
        cascade="all, delete-orphan",
        order_by="PlotBoundary.created_at.desc()",
    )

    @property
    def display_name(self) -> str:
        """Human-readable name for UI."""
        if self.nickname:
            return self.nickname
        return f"Plot {self.survey_number} — {self.village}"

    @property
    def is_verified(self) -> bool:
        return self.verification_status == PlotVerificationStatus.VERIFIED

    @property
    def is_leased(self) -> bool:
        return self.ownership_type == PlotOwnershipType.LEASED

    def __repr__(self) -> str:
        return (
            f"<Plot id={self.id} farmer={self.farmer_id} "
            f"survey={self.survey_number} village={self.village} "
            f"area={self.area_ha}ha verified={self.verification_status}>"
        )


# ---------------------------------------------------------------------------
# PlotBoundary (historical)
# ---------------------------------------------------------------------------


class PlotBoundary(Base):
    """Historical plot boundary snapshots.

    When a farmer redraws the plot boundary, the old boundary is archived
    here. This preserves history for NDVI recomputation and dispute resolution.
    """

    __tablename__ = "plot_boundaries"
    __table_args__ = {"schema": "farmer"}

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
    boundary: Mapped[object] = mapped_column(
        Geography(geometry_type="POLYGON", srid=4326),
        nullable=False,
    )
    area_ha: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    source: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="user_drawn",
        comment="user_drawn, satellite_detected, officer_corrected, imported",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.NOW(),
        nullable=False,
    )
    created_by: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("identity.users.id"),
        nullable=False,
    )

    plot: Mapped[Plot] = relationship("Plot", back_populates="boundary_history")

    def __repr__(self) -> str:
        return f"<PlotBoundary plot={self.plot_id} area={self.area_ha}ha source={self.source}>"


# ---------------------------------------------------------------------------
# CropCycle
# ---------------------------------------------------------------------------


class CropCycle(Base):
    """A crop grown on a plot during a specific season.

    A plot can have multiple crop cycles over time (rotations):
    - Kharif 2026: Rice
    - Rabi 2026-27: Wheat
    - Zaid 2027: Watermelon

    Only one crop cycle can be 'growing' at a time per plot.
    """

    __tablename__ = "crop_cycles"
    __table_args__ = {"schema": "farmer"}

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
    crop_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("farmer.crops.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # --- Season ---
    season: Mapped[CropSeason] = mapped_column(
        String(20),
        nullable=False,
        comment="Kharif, Rabi, or Zaid",
    )
    season_year: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Year of sowing (e.g., 2026)",
    )

    # --- Dates ---
    sowing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    expected_harvest_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_harvest_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # --- Area under this crop (may be less than plot area for intercropping) ---
    area_ha: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        nullable=False,
        comment="Area under this crop (≤ plot area)",
    )

    # --- Status ---
    status: Mapped[CropCycleStatus] = mapped_column(
        String(20),
        server_default=func.text("'planned'"),
        nullable=False,
        default=CropCycleStatus.PLANNED,
        index=True,
    )

    # --- Notes ---
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Timestamps ---
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.NOW(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.NOW(),
        nullable=False,
    )

    # --- Relationships ---
    plot: Mapped[Plot] = relationship("Plot", back_populates="crop_cycles")
    crop: Mapped[Crop] = relationship("Crop", back_populates="crop_cycles")

    @property
    def season_label(self) -> str:
        """Human-readable season label, e.g., 'Kharif 2026'."""
        return f"{self.season.value.title()} {self.season_year}"

    @property
    def is_active(self) -> bool:
        """Whether this crop cycle is currently growing."""
        return self.status in (
            CropCycleStatus.SOWN,
            CropCycleStatus.GROWING,
        )

    def __repr__(self) -> str:
        return (
            f"<CropCycle plot={self.plot_id} crop={self.crop_id} "
            f"season={self.season_label} status={self.status}>"
        )
