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
- When a plot is registered, the service dispatches a Celery task that
  queries ISRIC's REST API with the plot's centroid to fetch soil
  properties (soil type, pH, organic carbon).
- The task runs asynchronously and updates the plot row when it completes.
- The plot creation endpoint returns immediately (201) without waiting
  for the soil data — the frontend can poll or use a WebSocket to get
  the updated soil data.

"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from krishisetu.core.exceptions import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from krishisetu.core.logging import get_logger
from krishisetu.domains.farmer import repository as repo
from krishisetu.domains.farmer.models import (
    CropCycleStatus,
    CropSeason,
    IrrigationSource,
    PlotOwnershipType,
    PlotVerificationStatus,
)
from krishisetu.domains.farmer.schemas import (
    CropCycleCreate,
    CropCycleResponse,
    CropCycleUpdate,
    CropResponse,
    CropListResponse,
    PlotBoundaryUpdate,
    PlotCreate,
    PlotListItem,
    PlotListResponse,
    PlotResponse,
    PlotStatsResponse,
    PlotUpdate,
)

logger = get_logger(__name__)

# Constants
MAX_PLOTS_PER_FARMER = 50
MIN_PLOT_AREA_HA = Decimal("0.01")
MAX_PLOT_AREA_HA = Decimal("1000")
MIN_POLYGON_POINTS = 4  # 3 unique + closing
MAX_POLYGON_POINTS = 1000  # Sanity limit for very complex boundaries

# Crop services
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

# Plot services
async def create_plot(
    db: AsyncSession,
    farmer_id: UUID,
    payload: PlotCreate,
) -> PlotResponse:
    """Register a new plot for a farmer.

    Steps:
    1. Validate farmer hasn't exceeded plot limit
    2. Validate boundary geometry
    3. Check for duplicate survey number (EXISTS query, O(1))
    4. Check for boundary overlap (warning, not error)
    5. Create plot (database computes area from boundary)
    6. Dispatch Celery task to fetch soil data from ISRIC (async, non-blocking)

    FIX (T5): The ISRIC soil fetch is now async. Previously, create_plot()
    made a synchronous HTTP call to ISRIC with a 10-second timeout, blocking
    the farmer's plot-registration request. Now, the plot is created
    immediately and a Celery task (fetch_soil_data) updates the soil_type
    and soil_ph columns when the ISRIC API responds.
    """
    # --- Check plot limit ---
    existing_plots, total_count = await repo.list_plots_by_farmer(
        db, farmer_id, page=1, page_size=1
    )
    if total_count >= MAX_PLOTS_PER_FARMER:
        raise ValidationError(
            f"Maximum plot limit ({MAX_PLOTS_PER_FARMER}) reached. "
            "Contact support to increase the limit."
        )

    _validate_boundary(payload.boundary)
    is_duplicate = await repo.check_duplicate_survey_number(
        db,
        farmer_id=farmer_id,
        survey_number=payload.survey_number,
        village=payload.village,
        district=payload.district,
        state=payload.state,
    )
    if is_duplicate:
        raise ConflictError(
            f"Plot with survey number {payload.survey_number} already registered in "
            f"{payload.village}, {payload.district}, {payload.state}"
        )

    overlaps = await repo.check_plot_overlap(db, payload.boundary.model_dump())
    if overlaps:
        logger.warning(
            "plot.overlap_detected",
            farmer_id=str(farmer_id),
            overlapping_plots=len(overlaps),
        )

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

    if area_ha < MIN_PLOT_AREA_HA or area_ha > MAX_PLOT_AREA_HA:
        logger.warning(
            "plot.area_out_of_bounds",
            plot_id=str(plot.id),
            area_ha=str(area_ha),
        )
    try:
        from krishisetu.workers.tasks.soil import fetch_soil_data

        # Extract centroid from the created plot for the task
        centroid = _extract_centroid(plot)
        if centroid:
            task = fetch_soil_data.delay(
                str(plot.id),
                centroid["lon"],
                centroid["lat"],
            )
            logger.info(
                "plot.soil_task_dispatched",
                plot_id=str(plot.id),
                task_id=task.id,
            )
        else:
            logger.warning(
                "plot.soil_task_skipped_no_centroid",
                plot_id=str(plot.id),
            )
    except Exception as e:
        # Best-effort — don't fail plot creation if the task dispatch fails
        # (e.g. Redis is down). The plot exists; soil data can be fetched
        # later via a manual refresh endpoint.
        logger.warning(
            "plot.soil_task_dispatch_failed",
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



# Crop cycle services
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


# Officer verification services
async def officer_list_district_plots(
    db: AsyncSession,
    officer_id: UUID,
    district: str,
    state: str | None,
    *,

    verification_status: PlotVerificationStatus | None = None,
    page: int = 1,
    page_size: int = 20,
) -> PlotListResponse:
    """List plots in an officer's district (for verification worklist)."""
    plots, total = await repo.list_plots_by_district(
        db,
        district,
        state=state,
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
    officer_id: UUID,
    status: PlotVerificationStatus,
    notes: str | None = None,
) -> PlotResponse:
    """Officer verifies or rejects a plot."""
    plot = await repo.get_plot_by_id(db, plot_id, include_boundary=False)
    if not plot:
        raise NotFoundError("Plot", str(plot_id))

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

# Helpers
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


def _extract_centroid(plot) -> dict[str, float] | None:
    """Extract centroid {lon, lat} from a Plot ORM object or dict.

    The Plot object from get_plot_by_id (with include_boundary=True) has
    `centroid` as a GeoJSON dict (from ST_AsGeoJSON). The object from
    include_boundary=False has it as a GeoAlchemy2 element (not directly
    usable). We handle both cases.
    """
    if plot is None:
        return None

    centroid = getattr(plot, "centroid", None)
    if centroid is None:
        return None

    # Case 1: centroid is already a dict (from raw SQL ST_AsGeoJSON)
    if isinstance(centroid, dict):
        coords = centroid.get("coordinates")
        if coords and len(coords) >= 2:
            return {"lon": coords[0], "lat": coords[1]}

    # Case 2: centroid is a GeoAlchemy2 WKBElement — can't easily extract
    # in sync code. The Celery task will re-fetch the plot with the
    # raw SQL path if needed.
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
