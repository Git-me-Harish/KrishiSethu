"""Plot management routes.

Endpoints:
- GET    /plots                      — List current farmer's plots
- POST   /plots                      — Register a new plot
- GET    /plots/{id}                 — Get plot details (with boundary)
- PATCH  /plots/{id}                 — Update plot (non-boundary fields)
- PUT    /plots/{id}/boundary        — Redraw plot boundary
- DELETE /plots/{id}                 — Delete plot (only if not verified)
- GET    /plots/stats                — Summary statistics for farmer's plots
- GET    /plots/{id}/crops           — List crop cycles on a plot
- POST   /plots/{id}/crops           — Add a crop cycle to a plot
- PATCH  /crop-cycles/{id}           — Update a crop cycle (status, dates)
- GET    /crops                      — List all available crops (master data)
- GET    /officer/plots              — Officer: list plots in district
- PATCH  /officer/plots/{id}/verify  — Officer: verify/reject plot
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, status

from krishisetu.core.dependencies import CurrentUser, DBSession, require_permissions
from krishisetu.core.logging import get_logger
from krishisetu.domains.farmer import services
from krishisetu.domains.farmer.models import PlotVerificationStatus
from krishisetu.domains.farmer.schemas import (
    CropCycleCreate,
    CropCycleResponse,
    CropCycleUpdate,
    CropListResponse,
    OfficerVerifyPlot,
    PlotBoundaryUpdate,
    PlotCreate,
    PlotListResponse,
    PlotResponse,
    PlotStatsResponse,
    PlotUpdate,
)
from krishisetu.domains.identity.permissions import (
    PERM_DISEASE_REPORT_SUBMIT,
    PERM_PLOT_CREATE,
    PERM_PLOT_READ_DISTRICT,
    PERM_PLOT_READ_OWN,
    PERM_PLOT_UPDATE_OWN,
    PERM_PLOT_VERIFY,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Farmer-facing routes
# ---------------------------------------------------------------------------

plots_router = APIRouter(prefix="/plots", tags=["plots"])


@plots_router.get(
    "",
    response_model=PlotListResponse,
    dependencies=[Depends(require_permissions(PERM_PLOT_READ_OWN))],
)
async def list_my_plots(
    current_user: CurrentUser,
    db: DBSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> PlotListResponse:
    """List the current farmer's plots (compact view, no boundary geometry)."""
    return await services.list_my_plots(
        db, current_user.id, page=page, page_size=page_size
    )


@plots_router.post(
    "",
    response_model=PlotResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions(PERM_PLOT_CREATE))],
)
async def create_plot(
    payload: PlotCreate,
    current_user: CurrentUser,
    db: DBSession,
) -> PlotResponse:
    """Register a new plot.

    The plot boundary must be provided as a GeoJSON Polygon in WGS84 (EPSG:4326).
    The area is computed automatically from the boundary.

    Optional fields:
    - irrigation_source: canal, borewell, river, rainfed, drip, sprinkler, tank
    - ownership_type: owned (default), leased, shared
    - nickname: friendly name for easy reference

    For leased plots, lessor_name, lease_start_date, and lease_end_date are required.

    On creation, the platform attempts to auto-populate soil_type and soil_ph
    from ISRIC SoilGrids (best-effort, non-blocking).
    """
    return await services.create_plot(db, current_user.id, payload)


@plots_router.get(
    "/stats",
    response_model=PlotStatsResponse,
    dependencies=[Depends(require_permissions(PERM_PLOT_READ_OWN))],
)
async def get_plot_stats(
    current_user: CurrentUser,
    db: DBSession,
) -> PlotStatsResponse:
    """Get summary statistics for the current farmer's plots."""
    return await services.get_plot_stats(db, current_user.id)


@plots_router.get(
    "/{plot_id}",
    response_model=PlotResponse,
    dependencies=[Depends(require_permissions(PERM_PLOT_READ_OWN))],
)
async def get_plot(
    plot_id: Annotated[UUID, Path()],
    current_user: CurrentUser,
    db: DBSession,
) -> PlotResponse:
    """Get a plot by ID with full boundary geometry (GeoJSON)."""
    return await services.get_plot(db, plot_id, farmer_id=current_user.id)


@plots_router.patch(
    "/{plot_id}",
    response_model=PlotResponse,
    dependencies=[Depends(require_permissions(PERM_PLOT_UPDATE_OWN))],
)
async def update_plot(
    plot_id: Annotated[UUID, Path()],
    payload: PlotUpdate,
    current_user: CurrentUser,
    db: DBSession,
) -> PlotResponse:
    """Update editable fields on a plot (nickname, irrigation_source, pincode).

    Boundary updates use PUT /plots/{id}/boundary (separate endpoint).
    """
    return await services.update_plot(db, plot_id, current_user.id, payload)


@plots_router.put(
    "/{plot_id}/boundary",
    response_model=PlotResponse,
    dependencies=[Depends(require_permissions(PERM_PLOT_UPDATE_OWN))],
)
async def update_plot_boundary(
    plot_id: Annotated[UUID, Path()],
    payload: PlotBoundaryUpdate,
    current_user: CurrentUser,
    db: DBSession,
) -> PlotResponse:
    """Redraw a plot's boundary.

    The old boundary is archived in plot_boundaries for history.
    Area is recomputed from the new boundary.
    """
    return await services.update_plot_boundary(
        db, plot_id, current_user.id, payload
    )


@plots_router.delete(
    "/{plot_id}",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_permissions(PERM_PLOT_UPDATE_OWN))],
)
async def delete_plot(
    plot_id: Annotated[UUID, Path()],
    current_user: CurrentUser,
    db: DBSession,
) -> dict:
    """Delete a plot.

    Only the plot owner can delete. Verified plots cannot be deleted (the
    farmer must contact their agricultural officer to update ownership records).
    Deleting a plot also removes all related crop cycles and boundary history
    (cascade).
    """
    await services.delete_plot(db, plot_id, current_user.id)
    return {"message": "Plot deleted successfully"}


# ---------------------------------------------------------------------------
# Crop cycles on plots
# ---------------------------------------------------------------------------


@plots_router.get(
    "/{plot_id}/crops",
    response_model=list[CropCycleResponse],
    dependencies=[Depends(require_permissions(PERM_PLOT_READ_OWN))],
)
async def list_crop_cycles(
    plot_id: Annotated[UUID, Path()],
    current_user: CurrentUser,
    db: DBSession,
) -> list[CropCycleResponse]:
    """List all crop cycles (rotations) for a plot, most recent first."""
    return await services.list_crop_cycles(db, plot_id, current_user.id)


@plots_router.post(
    "/{plot_id}/crops",
    response_model=CropCycleResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions(PERM_DISEASE_REPORT_SUBMIT))],
)
async def create_crop_cycle(
    plot_id: Annotated[UUID, Path()],
    payload: CropCycleCreate,
    current_user: CurrentUser,
    db: DBSession,
) -> CropCycleResponse:
    """Add a crop cycle (crop + season) to a plot.

    A plot can have only one active (sown or growing) crop cycle at a time.
    The crop area cannot exceed the plot area.
    """
    return await services.create_crop_cycle(db, plot_id, current_user.id, payload)


# ---------------------------------------------------------------------------
# Crop cycle updates (separate router for /crop-cycles/{id})
# ---------------------------------------------------------------------------

crop_cycles_router = APIRouter(prefix="/crop-cycles", tags=["crop-cycles"])


@crop_cycles_router.patch(
    "/{cycle_id}",
    response_model=CropCycleResponse,
    dependencies=[Depends(require_permissions(PERM_PLOT_UPDATE_OWN))],
)
async def update_crop_cycle(
    cycle_id: Annotated[UUID, Path()],
    payload: CropCycleUpdate,
    current_user: CurrentUser,
    db: DBSession,
) -> CropCycleResponse:
    """Update a crop cycle (status, dates, notes).

    Status transitions:
    - planned → sown (when sowing_date is set)
    - sown → growing (crop is established)
    - growing → harvested (when actual_harvest_date is set)
    - growing → failed (crop failure — disease, weather, etc.)
    """
    return await services.update_crop_cycle(db, cycle_id, current_user.id, payload)


# ---------------------------------------------------------------------------
# Crop master data (public)
# ---------------------------------------------------------------------------

crops_router = APIRouter(prefix="/crops", tags=["crops"])


@crops_router.get("", response_model=CropListResponse)
async def list_crops(
    db: DBSession,
    category: str | None = Query(
        default=None,
        description=(
            "Filter by category: cereals, pulses, oilseeds, fibre, sugar, "
            "plantation, horticulture, spices, fodder"
        ),
    ),
    season: str | None = Query(
        default=None, description="Filter by primary season: kharif, rabi, zaid"
    ),
) -> CropListResponse:
    """List all available crops (master data).

    Public endpoint — does not require authentication.
    Used by the plot registration wizard to populate the crop dropdown.
    """
    from krishisetu.domains.farmer.models import CropSeason

    season_enum = CropSeason(season) if season else None
    return await services.list_crops(db, category=category, season=season_enum)


# ---------------------------------------------------------------------------
# Officer routes
# ---------------------------------------------------------------------------

officer_router = APIRouter(
    prefix="/officer/plots",
    tags=["officer"],
    dependencies=[Depends(require_permissions(PERM_PLOT_READ_DISTRICT))],
)


@officer_router.get("", response_model=PlotListResponse)
async def officer_list_plots(
    current_user: CurrentUser,
    db: DBSession,
    verification_status: PlotVerificationStatus | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> PlotListResponse:
    """List plots in the officer's district (for verification worklist).

    The district is resolved from the officer's own assignment — it is never
    taken from the request.

    Officers can filter by verification_status to focus on:
    - pending: New plots awaiting verification
    - resubmission_requested: Farmer was asked to resubmit
    - verified: Already verified (historical)
    - rejected: Rejected plots (audit)
    """
    return await services.officer_list_district_plots(
        db,
        current_user,
        verification_status=verification_status,
        page=page,
        page_size=page_size,
    )


@officer_router.patch(
    "/{plot_id}/verify",
    response_model=PlotResponse,
    dependencies=[Depends(require_permissions(PERM_PLOT_VERIFY))],
)
async def officer_verify_plot(
    plot_id: Annotated[UUID, Path()],
    payload: OfficerVerifyPlot,
    current_user: CurrentUser,
    db: DBSession,
) -> PlotResponse:
    """Verify or reject a plot's ownership claim.

    The officer should cross-reference the survey number with state land
    records (Bhulekh) before verifying. Notes are required when rejecting
    or requesting resubmission.
    """
    from krishisetu.core.exceptions import ValidationError
    from krishisetu.domains.farmer.models import PlotVerificationStatus

    if payload.status in (
        PlotVerificationStatus.REJECTED,
        PlotVerificationStatus.RESUBMISSION_REQUESTED,
    ) and not payload.notes:
        raise ValidationError(
            f"Notes are required when status is {payload.status.value}"
        )

    return await services.officer_verify_plot(
        db,
        plot_id,
        current_user,
        PlotVerificationStatus(payload.status),
        payload.notes,
    )
