"""Farmer domain — business logic services.

The service layer:
- Validates business rules (plot ownership, area limits, lease dates)
- Orchestrates multiple repository calls
- Integrates with external services (ISRIC SoilGrids)
- Enforces permission checks at the service boundary

Key business rules:
- A farmer can have a maximum of 50 plots (configurable)
- Plot area must be between 0.01 ha and 1000 ha (sanity bounds)
- A plot can have only one active crop cycle at a time
- Boundary must have at least 3 unique points (4 with closing)
- Leased plots require lessor name and lease dates

ISRIC SoilGrids integration:
- When a plot is registered, the service queries ISRIC's REST API with the
  plot's centroid to fetch soil properties (soil type, pH, organic carbon)
- These are stored on the plot for future reference
- The integration is currently a stub that returns None — Phase 2 will wire
  it to the real API
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from krishisetu.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from krishisetu.core.logging import get_logger
from krishisetu.domains.farmer import repository as repo
from krishisetu.domains.farmer.models import (
    CropSeason,
    IrrigationSource,
    PlotOwnershipType,
    PlotVerificationStatus,
)
from krishisetu.domains.farmer.officer_scope import (
    require_within_jurisdiction,
    resolve_officer_jurisdiction,
)
from krishisetu.domains.farmer.schemas import (
    CropCycleCreate,
    CropCycleResponse,
    CropCycleUpdate,
    CropListResponse,
    CropResponse,
    PlotBoundaryUpdate,
    PlotCreate,
    PlotListItem,
    PlotListResponse,
    PlotResponse,
    PlotStatsResponse,
    PlotUpdate,
)
from krishisetu.domains.identity.models import User

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_PLOTS_PER_FARMER = 50
MIN_PLOT_AREA_HA = Decimal("0.01")
MAX_PLOT_AREA_HA = Decimal("1000")
MIN_POLYGON_POINTS = 4  # 3 unique + closing
MAX_POLYGON_POINTS = 1000  # Sanity limit for very complex boundaries
ISRIC_API_URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"


# ---------------------------------------------------------------------------
# Crop services
# ---------------------------------------------------------------------------


async def list_crops(
    db: AsyncSession,
    *,
    category: str | None = None,
    season: CropSeason | None = None,
) -> CropListResponse:
    """List all available crops, optionally filtered."""
    crops = await repo.list_crops(db, category=category, season=season)
    return CropListResponse(
        crops=[CropResponse.model_validate(c) for c in crops],
        total=len(crops),
    )


# ---------------------------------------------------------------------------
# Plot services
# ---------------------------------------------------------------------------


async def create_plot(
    db: AsyncSession,
    farmer_id: UUID,
    payload: PlotCreate,
) -> PlotResponse:
    """Register a new plot for a farmer.

    Steps:
    1. Validate farmer hasn't exceeded plot limit
    2. Validate boundary geometry
    3. Check for overlap with existing plots (warning, not error)
    4. Create plot (database computes area from boundary)
    5. Auto-populate soil data from ISRIC (best-effort, async)
    """
    # --- Check plot limit ---
    _existing_plots, total_count = await repo.list_plots_by_farmer(
        db, farmer_id, page=1, page_size=1
    )
    if total_count >= MAX_PLOTS_PER_FARMER:
        raise ValidationError(
            f"Maximum plot limit ({MAX_PLOTS_PER_FARMER}) reached. "
            "Contact support to increase the limit."
        )

    # --- Validate boundary ---
    _validate_boundary(payload.boundary)

    # --- Check for duplicate survey number for this farmer ---
    # (handled by DB unique constraint, but we check early for better error message)
    plots, _ = await repo.list_plots_by_farmer(db, farmer_id, page=1, page_size=100)
    for p in plots:
        if (
            p["survey_number"] == payload.survey_number
            and p["village"] == payload.village
            and p["district"] == payload.district
            and p["state"] == payload.state
        ):
            raise ConflictError(
                f"Plot with survey number {payload.survey_number} already registered in "
                f"{payload.village}, {payload.district}, {payload.state}"
            )

    # --- Check for boundary overlap (warning only) ---
    overlaps = await repo.check_plot_overlap(db, payload.boundary.model_dump())
    if overlaps:
        logger.warning(
            "plot.overlap_detected",
            farmer_id=str(farmer_id),
            overlapping_plots=len(overlaps),
        )
        # Don't raise — just log. The farmer might be re-registering or
        # the overlap is partial and acceptable.

    # --- Create plot ---
    plot, area_ha = await repo.create_plot(
        db,
        farmer_id=farmer_id,
        survey_number=payload.survey_number,
        village=payload.village,
        district=payload.district,
        state=payload.state,
        boundary_geojson=payload.boundary.model_dump(),
        pincode=payload.pincode,
        irrigation_source=IrrigationSource(payload.irrigation_source)
        if payload.irrigation_source
        else None,
        ownership_type=PlotOwnershipType(payload.ownership_type),
        lessor_name=payload.lessor_name,
        lease_start_date=payload.lease_start_date,
        lease_end_date=payload.lease_end_date,
        nickname=payload.nickname,
    )

    # --- Sanity-check computed area ---
    if area_ha < MIN_PLOT_AREA_HA or area_ha > MAX_PLOT_AREA_HA:
        logger.warning(
            "plot.area_out_of_bounds",
            plot_id=str(plot.id),
            area_ha=str(area_ha),
        )
        # Don't raise — just log. The boundary might be intentionally small
        # (e.g., kitchen garden) or large (e.g., plantation).

    # --- Auto-populate soil data from ISRIC (best-effort, non-blocking) ---
    try:
        soil_data = await _fetch_soil_from_isric(plot.centroid)
        if soil_data:
            await repo.update_plot(
                db,
                plot.id,
                soil_type=soil_data.get("soil_type"),
                soil_ph=soil_data.get("ph"),
            )
            # Re-fetch to include soil data
            plot = await repo.get_plot_by_id(db, plot.id)
    except Exception as e:
        # Soil fetch is best-effort — don't fail plot creation
        logger.warning(
            "plot.soil_fetch_failed",
            plot_id=str(plot.id),
            error=str(e),
        )

    logger.info(
        "plot.created",
        plot_id=str(plot.id),
        farmer_id=str(farmer_id),
        area_ha=str(area_ha),
        village=payload.village,
        district=payload.district,
    )

    return _to_plot_response(plot)


async def get_plot(
    db: AsyncSession,
    plot_id: UUID,
    *,
    farmer_id: UUID | None = None,
) -> PlotResponse:
    """Get a plot by ID. If farmer_id is provided, verifies ownership."""
    plot = await repo.get_plot_by_id(db, plot_id)
    if not plot:
        raise NotFoundError("Plot", str(plot_id))

    if farmer_id and plot.farmer_id != farmer_id:
        raise NotFoundError("Plot", str(plot_id))  # Don't leak existence

    return _to_plot_response(plot)


async def list_my_plots(
    db: AsyncSession,
    farmer_id: UUID,
    *,
    page: int = 1,
    page_size: int = 20,
) -> PlotListResponse:
    """List the current farmer's plots (compact view, no boundary)."""
    plots, total = await repo.list_plots_by_farmer(
        db, farmer_id, page=page, page_size=page_size
    )
    return PlotListResponse(
        plots=[PlotListItem(**p) for p in plots],
        total=total,
        page=page,
        page_size=page_size,
        has_more=(page * page_size) < total,
    )


async def update_plot(
    db: AsyncSession,
    plot_id: UUID,
    farmer_id: UUID,
    payload: PlotUpdate,
) -> PlotResponse:
    """Update editable fields on a plot."""
    plot = await repo.get_plot_by_id(db, plot_id, include_boundary=False)
    if not plot or plot.farmer_id != farmer_id:
        raise NotFoundError("Plot", str(plot_id))

    updated = await repo.update_plot(
        db,
        plot_id,
        nickname=payload.nickname,
        irrigation_source=IrrigationSource(payload.irrigation_source)
        if payload.irrigation_source
        else None,
        pincode=payload.pincode,
    )

    return _to_plot_response(updated or plot)


async def update_plot_boundary(
    db: AsyncSession,
    plot_id: UUID,
    farmer_id: UUID,
    payload: PlotBoundaryUpdate,
) -> PlotResponse:
    """Redraw a plot's boundary.

    The old boundary is archived in plot_boundaries for history.
    Area is recomputed from the new boundary.
    """
    plot = await repo.get_plot_by_id(db, plot_id, include_boundary=False)
    if not plot or plot.farmer_id != farmer_id:
        raise NotFoundError("Plot", str(plot_id))

    _validate_boundary(payload.boundary)

    result = await repo.update_plot_boundary(
        db,
        plot_id,
        payload.boundary.model_dump(),
        source=payload.source,
        updated_by=farmer_id,
    )
    if not result:
        raise NotFoundError("Plot", str(plot_id))

    updated_plot, area_ha = result
    logger.info(
        "plot.boundary_updated",
        plot_id=str(plot_id),
        new_area_ha=str(area_ha),
    )

    return _to_plot_response(updated_plot)


async def delete_plot(
    db: AsyncSession, plot_id: UUID, farmer_id: UUID
) -> None:
    """Delete a plot. Only the owner can delete; verified plots cannot be deleted."""
    plot = await repo.get_plot_by_id(db, plot_id, include_boundary=False)
    if not plot or plot.farmer_id != farmer_id:
        raise NotFoundError("Plot", str(plot_id))

    if plot.verification_status == PlotVerificationStatus.VERIFIED:
        raise ValidationError(
            "Cannot delete a verified plot. Contact your agricultural officer "
            "to update ownership records instead."
        )

    await repo.delete_plot(db, plot_id)
    logger.info("plot.deleted", plot_id=str(plot_id), farmer_id=str(farmer_id))


async def get_plot_stats(db: AsyncSession, farmer_id: UUID) -> PlotStatsResponse:
    """Get summary statistics for the farmer's plots."""
    stats = await repo.get_plot_stats(db, farmer_id)
    return PlotStatsResponse(**stats)


# ---------------------------------------------------------------------------
# Crop cycle services
# ---------------------------------------------------------------------------


async def create_crop_cycle(
    db: AsyncSession,
    plot_id: UUID,
    farmer_id: UUID,
    payload: CropCycleCreate,
) -> CropCycleResponse:
    """Add a crop cycle to a plot."""
    # Verify plot ownership
    plot = await repo.get_plot_by_id(db, plot_id, include_boundary=False)
    if not plot or plot.farmer_id != farmer_id:
        raise NotFoundError("Plot", str(plot_id))

    # Validate area doesn't exceed plot area
    if payload.area_ha > plot.area_ha:
        raise ValidationError(
            f"Crop area ({payload.area_ha} ha) cannot exceed plot area ({plot.area_ha} ha)"
        )

    # Check for active crop cycle (only one allowed)
    if await repo.check_active_crop_cycle(db, plot_id):
        raise ConflictError(
            "Plot already has an active crop cycle. Mark the existing one as "
            "harvested or failed before adding a new one."
        )

    # Validate crop exists
    from krishisetu.domains.farmer.repository import get_crop_by_id

    crop = await get_crop_by_id(db, payload.crop_id)
    if not crop:
        raise NotFoundError("Crop", str(payload.crop_id))

    cycle = await repo.create_crop_cycle(
        db,
        plot_id=plot_id,
        crop_id=payload.crop_id,
        season=payload.season,
        season_year=payload.season_year,
        area_ha=payload.area_ha,
        sowing_date=payload.sowing_date,
        expected_harvest_date=payload.expected_harvest_date,
        notes=payload.notes,
    )

    cycle_dict = await repo.get_crop_cycle_by_id(db, cycle.id)
    logger.info(
        "crop_cycle.created",
        cycle_id=str(cycle.id),
        plot_id=str(plot_id),
        crop=crop.name_en,
        season=payload.season.value,
    )

    return CropCycleResponse(**cycle_dict)


async def list_crop_cycles(
    db: AsyncSession, plot_id: UUID, farmer_id: UUID
) -> list[CropCycleResponse]:
    """List all crop cycles for a plot."""
    plot = await repo.get_plot_by_id(db, plot_id, include_boundary=False)
    if not plot or plot.farmer_id != farmer_id:
        raise NotFoundError("Plot", str(plot_id))

    cycles = await repo.list_crop_cycles_by_plot(db, plot_id)
    return [CropCycleResponse(**c) for c in cycles]


async def update_crop_cycle(
    db: AsyncSession,
    cycle_id: UUID,
    farmer_id: UUID,
    payload: CropCycleUpdate,
) -> CropCycleResponse:
    """Update a crop cycle (status, dates, notes)."""
    cycle = await repo.get_crop_cycle_by_id(db, cycle_id)
    if not cycle:
        raise NotFoundError("CropCycle", str(cycle_id))

    # Verify ownership via plot
    plot = await repo.get_plot_by_id(db, cycle["plot_id"], include_boundary=False)
    if not plot or plot.farmer_id != farmer_id:
        raise NotFoundError("CropCycle", str(cycle_id))

    updates: dict[str, Any] = {}
    if payload.sowing_date is not None:
        updates["sowing_date"] = payload.sowing_date
    if payload.expected_harvest_date is not None:
        updates["expected_harvest_date"] = payload.expected_harvest_date
    if payload.actual_harvest_date is not None:
        updates["actual_harvest_date"] = payload.actual_harvest_date
    if payload.status is not None:
        updates["status"] = payload.status
    if payload.notes is not None:
        updates["notes"] = payload.notes

    updated = await repo.update_crop_cycle(db, cycle_id, **updates)
    return CropCycleResponse(**updated)


# ---------------------------------------------------------------------------
# Officer verification services
# ---------------------------------------------------------------------------


async def officer_list_district_plots(
    db: AsyncSession,
    officer: User,
    *,
    verification_status: PlotVerificationStatus | None = None,
    page: int = 1,
    page_size: int = 20,
) -> PlotListResponse:
    """List plots in an officer's district (for verification worklist).

    The district/state come from the officer's own assignment, never from the
    request.
    """
    jurisdiction = resolve_officer_jurisdiction(officer)

    plots, total = await repo.list_plots_by_district(
        db,
        jurisdiction.district if jurisdiction else None,
        state=jurisdiction.state if jurisdiction else None,
        verification_status=verification_status,
        page=page,
        page_size=page_size,
    )
    return PlotListResponse(
        plots=[PlotListItem(**p) for p in plots],
        total=total,
        page=page,
        page_size=page_size,
        has_more=(page * page_size) < total,
    )


async def officer_verify_plot(
    db: AsyncSession,
    plot_id: UUID,
    officer: User,
    status: PlotVerificationStatus,
    notes: str | None = None,
) -> PlotResponse:
    """Officer verifies or rejects a plot in their own district."""
    officer_id = officer.id
    plot = await repo.get_plot_by_id(db, plot_id, include_boundary=False)
    if not plot:
        raise NotFoundError("Plot", str(plot_id))

    jurisdiction = resolve_officer_jurisdiction(officer)
    require_within_jurisdiction(
        jurisdiction, state=plot.state, district=plot.district
    )

    if status not in (
        PlotVerificationStatus.VERIFIED,
        PlotVerificationStatus.REJECTED,
        PlotVerificationStatus.RESUBMISSION_REQUESTED,
    ):
        raise ValidationError(
            "Status must be one of: verified, rejected, resubmission_requested"
        )

    updated = await repo.verify_plot(db, plot_id, officer_id, status, notes)
    logger.info(
        "plot.verified",
        plot_id=str(plot_id),
        officer_id=str(officer_id),
        status=status.value,
    )

    return _to_plot_response(updated or plot)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _validate_boundary(boundary) -> None:
    """Validate a GeoJSON polygon boundary."""
    coords = boundary.coordinates
    if not coords:
        raise ValidationError("Boundary must have at least one ring")

    exterior = coords[0]
    if len(exterior) < MIN_POLYGON_POINTS:
        raise ValidationError(
            f"Boundary must have at least {MIN_POLYGON_POINTS} points "
            f"(3 unique + closing point). Got {len(exterior)}."
        )

    if len(exterior) > MAX_POLYGON_POINTS:
        raise ValidationError(
            f"Boundary has too many points ({len(exterior)}). Maximum is "
            f"{MAX_POLYGON_POINTS}. Simplify the boundary."
        )

    # Check ring is closed
    if exterior[0] != exterior[-1]:
        raise ValidationError("Boundary ring must be closed (first and last point identical)")


async def _fetch_soil_from_isric(centroid: dict[str, float] | None) -> dict[str, Any] | None:
    """Fetch soil data from ISRIC SoilGrids API for the given centroid.

    ISRIC SoilGrids is a free global soil property prediction system at 250m
    resolution. API: https://rest.isric.org/soilgrids/v2.0/properties/query

    Returns a dict with:
    - soil_type: WRB soil type (e.g., 'Acrisols', 'Luvisols')
    - ph: soil pH (mean of top 30cm)

    Returns None on any error (best-effort).
    """
    if not centroid or "lon" not in centroid or "lat" not in centroid:
        return None

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                ISRIC_API_URL,
                params={
                    "lon": centroid["lon"],
                    "lat": centroid["lat"],
                    "property": ["phh2o", "soc"],  # pH and soil organic carbon
                    "depth": "5-15cm",  # Top layer
                    "value": "mean",
                },
            )
        if response.status_code != 200:
            logger.warning(
                "isric.api_error",
                status=response.status_code,
                body=response.text[:200],
            )
            return None

        data = response.json()
        # Parse the response — actual structure TBD when integrated for real
        # For now, return a placeholder structure
        properties = data.get("properties", {})
        layers = properties.get("layers", [])

        ph = None
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
    except Exception as e:
        logger.warning("isric.fetch_failed", error=str(e))
        return None


def _to_plot_response(plot) -> PlotResponse:
    """Convert a Plot ORM object (with parsed boundary dict) to PlotResponse."""
    if plot is None:
        raise NotFoundError("Plot", "unknown")

    # Handle both ORM objects and dicts
    if hasattr(plot, "__dict__"):
        data = {
            "id": plot.id,
            "farmer_id": plot.farmer_id,
            "survey_number": plot.survey_number,
            "village": plot.village,
            "district": plot.district,
            "state": plot.state,
            "pincode": plot.pincode,
            "area_ha": plot.area_ha,
            "boundary": plot.boundary,
            "centroid": plot.centroid if isinstance(plot.centroid, dict) else None,
            "soil_type": plot.soil_type,
            "soil_ph": plot.soil_ph,
            "irrigation_source": plot.irrigation_source,
            "ownership_type": plot.ownership_type,
            "lessor_name": getattr(plot, "lessor_name", None),
            "lease_start_date": getattr(plot, "lease_start_date", None),
            "lease_end_date": getattr(plot, "lease_end_date", None),
            "verification_status": plot.verification_status,
            "verified_by": getattr(plot, "verified_by", None),
            "verified_at": getattr(plot, "verified_at", None),
            "verification_notes": getattr(plot, "verification_notes", None),
            "nickname": getattr(plot, "nickname", None),
            "created_at": plot.created_at,
            "updated_at": plot.updated_at,
        }
    else:
        data = plot

    # Handle string enum values from raw SQL queries
    if isinstance(data.get("irrigation_source"), str):
        try:
            data["irrigation_source"] = IrrigationSource(data["irrigation_source"])
        except ValueError:
            data["irrigation_source"] = None

    if isinstance(data.get("ownership_type"), str):
        try:
            data["ownership_type"] = PlotOwnershipType(data["ownership_type"])
        except ValueError:
            data["ownership_type"] = PlotOwnershipType.OWNED

    if isinstance(data.get("verification_status"), str):
        try:
            data["verification_status"] = PlotVerificationStatus(
                data["verification_status"]
            )
        except ValueError:
            data["verification_status"] = PlotVerificationStatus.PENDING

    return PlotResponse(**data)
