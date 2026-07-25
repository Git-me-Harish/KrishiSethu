"""Soil & Weather routes.

Endpoints:
Plot-specific (farmer-facing, require auth + plot ownership):
- GET  /plots/{id}/weather/current    — Current weather at plot
- GET  /plots/{id}/weather/forecast   — 7-day forecast at plot
- GET  /plots/{id}/weather/history    — Historical observations
- GET  /plots/{id}/weather/alerts     — Active alerts for plot's district
- GET  /plots/{id}/weather/summary    — Aggregated summary (current + forecast + alerts)
- GET  /plots/{id}/soil-tests         — List soil tests
- POST /plots/{id}/soil-tests         — Manual soil test entry
- POST /plots/{id}/soil-tests/import-shc — Import from Soil Health Card (Phase 2)
- GET  /plots/{id}/soil-tests/{test_id} — Get specific soil test

District-level (public, no auth):
- GET  /weather/district/{district}   — Current weather for district
- GET  /weather/district/{district}/forecast — 7-day forecast
- GET  /weather/district/{district}/alerts   — Active alerts

Admin/debug:
- POST /admin/weather/sync            — Force weather sync for a district
- POST /admin/weather/check-alerts    — Force alert check
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, status

from krishisetu.core.dependencies import CurrentUser, DBSession, require_permissions
from krishisetu.core.exceptions import ValidationError
from krishisetu.core.logging import get_logger
from krishisetu.domains.identity.models import UserRole
from krishisetu.domains.identity.permissions import (
    PERM_SOIL_TEST_ADD,
    PERM_SOIL_TEST_READ_OWN,
    PERM_WEATHER_READ,
)
from krishisetu.domains.soil_weather import services
from krishisetu.domains.soil_weather.schemas import (
    CurrentWeatherResponse,
    ForecastResponse,
    PlotWeatherSummaryResponse,
    SHCImportRequest,
    SoilTestCreate,
    SoilTestListResponse,
    SoilTestResponse,
    WeatherAlertListResponse,
    WeatherHistoryResponse,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Plot-specific weather routes
# ---------------------------------------------------------------------------

plot_weather_router = APIRouter(
    prefix="/plots/{plot_id}/weather",
    tags=["weather"],
    dependencies=[Depends(require_permissions(PERM_WEATHER_READ))],
)


@plot_weather_router.get("/current", response_model=CurrentWeatherResponse)
async def get_plot_current_weather(
    plot_id: Annotated[UUID, Path()],
    current_user: CurrentUser,
    db: DBSession,
) -> CurrentWeatherResponse:
    """Get current weather conditions for a specific plot.

    Looks up the plot's district and returns the latest weather observation.
    If the observation is older than 2 hours, triggers a sync first.
    """
    return await services.get_current_weather_for_plot(db, plot_id, current_user.id)


@plot_weather_router.get("/forecast", response_model=ForecastResponse)
async def get_plot_forecast(
    plot_id: Annotated[UUID, Path()],
    current_user: CurrentUser,
    db: DBSession,
) -> ForecastResponse:
    """Get 7-day weather forecast for a specific plot."""
    return await services.get_forecast_for_plot(db, plot_id, current_user.id)


@plot_weather_router.get("/history", response_model=WeatherHistoryResponse)
async def get_plot_weather_history(
    plot_id: Annotated[UUID, Path()],
    current_user: CurrentUser,
    db: DBSession,
    hours: int = Query(default=24, ge=1, le=720, description="Hours of history (max 30 days)"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=500),
) -> WeatherHistoryResponse:
    """Get historical weather observations for a plot's district."""
    return await services.get_weather_history(
        db, plot_id, current_user.id, hours=hours, page=page, page_size=page_size
    )


@plot_weather_router.get("/alerts", response_model=WeatherAlertListResponse)
async def get_plot_weather_alerts(
    plot_id: Annotated[UUID, Path()],
    current_user: CurrentUser,
    db: DBSession,
) -> WeatherAlertListResponse:
    """Get active weather alerts for a plot's district."""
    return await services.get_active_alerts_for_plot(db, plot_id, current_user.id)


@plot_weather_router.get("/summary", response_model=PlotWeatherSummaryResponse)
async def get_plot_weather_summary(
    plot_id: Annotated[UUID, Path()],
    current_user: CurrentUser,
    db: DBSession,
) -> PlotWeatherSummaryResponse:
    """Get aggregated weather summary for a plot (current + forecast + alerts).

    Convenience endpoint for the dashboard — combines three queries into one.
    """
    return await services.get_plot_weather_summary(db, plot_id, current_user.id)


# ---------------------------------------------------------------------------
# Plot-specific soil test routes
# ---------------------------------------------------------------------------

plot_soil_router = APIRouter(
    prefix="/plots/{plot_id}/soil-tests",
    tags=["soil"],
)


@plot_soil_router.get(
    "",
    response_model=SoilTestListResponse,
    dependencies=[Depends(require_permissions(PERM_SOIL_TEST_READ_OWN))],
)
@plot_soil_router.get(
    "/",
    response_model=SoilTestListResponse,
    include_in_schema=False,
    dependencies=[Depends(require_permissions(PERM_SOIL_TEST_READ_OWN))],
)
async def list_plot_soil_tests(
    plot_id: Annotated[UUID, Path()],
    current_user: CurrentUser,
    db: DBSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> SoilTestListResponse:
    """List all soil tests for a plot, most recent first."""
    return await services.list_soil_tests(
        db, plot_id, current_user.id, page=page, page_size=page_size
    )


@plot_soil_router.post(
    "",
    response_model=SoilTestResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions(PERM_SOIL_TEST_ADD))],
)
async def create_plot_soil_test(
    plot_id: Annotated[UUID, Path()],
    payload: SoilTestCreate,
    current_user: CurrentUser,
    db: DBSession,
) -> SoilTestResponse:
    """Add a manual soil test result for a plot.

    Enter the values from your soil testing lab report. The platform will
    automatically generate fertilizer and amendment recommendations based
    on the test results.
    """
    return await services.create_manual_soil_test(
        db, plot_id, current_user.id, payload
    )


@plot_soil_router.post(
    "/import-shc",
    response_model=SoilTestResponse,
    dependencies=[Depends(require_permissions(PERM_SOIL_TEST_ADD))],
)
async def import_shc(
    plot_id: Annotated[UUID, Path()],
    payload: SHCImportRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> SoilTestResponse:
    """Import soil test from the Soil Health Card portal.

    Enter your SHC ID and the platform will fetch the official test results
    from the government portal.

    Note: This integration is currently in development.
    """
    return await services.import_shc_soil_test(
        db, plot_id, current_user.id, payload
    )


# ---------------------------------------------------------------------------
# District-level weather routes (public)
# ---------------------------------------------------------------------------

district_weather_router = APIRouter(
    prefix="/weather/district",
    tags=["weather"],
)


@district_weather_router.get("/{district}", response_model=CurrentWeatherResponse)
async def get_district_current_weather(
    district: Annotated[str, Path()],
    state: str = Query(..., description="State name (required for disambiguation)"),
    db: DBSession = None,
) -> CurrentWeatherResponse:
    """Get current weather for a district.

    Public endpoint — no authentication required.
    Used by the public scheme catalog and landing page.
    """
    return await services.get_current_weather_for_district(db, district, state)


@district_weather_router.get(
    "/{district}/forecast", response_model=ForecastResponse
)
async def get_district_forecast(
    district: Annotated[str, Path()],
    state: str = Query(..., description="State name"),
    db: DBSession = None,
) -> ForecastResponse:
    """Get 7-day forecast for a district (public)."""
    return await services.get_forecast_for_district(db, district, state)


@district_weather_router.get(
    "/{district}/alerts", response_model=WeatherAlertListResponse
)
async def get_district_alerts(
    district: Annotated[str, Path()],
    state: str = Query(..., description="State name"),
    db: DBSession = None,
) -> WeatherAlertListResponse:
    """Get active weather alerts for a district (public)."""
    return await services.get_active_alerts_for_district(db, district, state)


# ---------------------------------------------------------------------------
# Admin routes
# ---------------------------------------------------------------------------

admin_weather_router = APIRouter(
    prefix="/admin/weather",
    tags=["admin"],
    dependencies=[Depends(require_permissions(PERM_WEATHER_READ))],
)


@admin_weather_router.post("/sync")
async def force_weather_sync(
    current_user: CurrentUser,
    db: DBSession,
    district: str = Query(..., description="District to sync"),
    state: str = Query(..., description="State"),
) -> dict:
    """Force a weather sync for a specific district (admin/debug).

    Useful for testing or for refreshing data outside the hourly schedule.
    """
    if current_user.role != UserRole.ADMIN:
        from krishisetu.core.exceptions import AuthorizationError

        raise AuthorizationError("Admin access required")

    result = await services.sync_district_weather(db, district, state)
    return result


@admin_weather_router.post("/check-alerts")
async def force_alert_check(
    current_user: CurrentUser,
    db: DBSession,
) -> dict:
    """Force a weather alert check across all districts (admin/debug)."""
    if current_user.role != UserRole.ADMIN:
        from krishisetu.core.exceptions import AuthorizationError

        raise AuthorizationError("Admin access required")

    alerts = await services.check_and_generate_alerts(db)
    return {
        "alerts_generated": len(alerts),
        "alert_types": [a.alert_type.value for a in alerts],
    }
