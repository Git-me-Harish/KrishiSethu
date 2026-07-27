"""Soil & Weather domain — business logic services.

Orchestrates:
- Soil test management (create manual, import SHC, ISRIC auto-populate)
- Fertilizer recommendation engine (based on soil test + crop type)
- Weather sync (calls IMD/OWM, upserts observations)
- Weather queries (current, forecast, history) with plot-to-district interpolation
- Weather alert generation (checks forecasts against thresholds)
- Weather alert dispatch (notifications to affected farmers)

Key flows:
- Hourly sync: Celery Beat -> sync_district_weather() for each district with plots
- Alert check: Celery Beat -> check_weather_alerts() every 3 hours
- Plot registration: _fetch_soil_from_isric() auto-populates soil data
- Farmer query: get_current_weather(plot_id) -> lookup plot's district -> get latest observation
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from krishisetu.core.exceptions import (
    NotFoundError,
)
from krishisetu.core.logging import get_logger
from krishisetu.domains.farmer import repository as farmer_repo
from krishisetu.domains.soil_weather import repository as repo
from krishisetu.domains.soil_weather.models import (
    SoilTest,
    SoilTestSource,
    WeatherAlert,
    WeatherAlertSeverity,
    WeatherAlertType,
    WeatherDataSource,
    WeatherObservation,
)
from krishisetu.domains.soil_weather.schemas import (
    CurrentWeatherResponse,
    DailyForecastResponse,
    ForecastResponse,
    PlotWeatherSummaryResponse,
    SHCImportRequest,
    SoilTestCreate,
    SoilTestListResponse,
    SoilTestResponse,
    WeatherAlertListResponse,
    WeatherAlertResponse,
    WeatherHistoryResponse,
)
from krishisetu.integrations.imd import (
    get_imd_client,
)
from krishisetu.integrations.isric import get_isric_client
from krishisetu.integrations.openweathermap import get_owm_client

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# District centroid approximation
# ---------------------------------------------------------------------------

# Approximate centroids for major Indian districts (lat, lon)
# Used when we don't have the exact centroid from a plot registration.
# In production, this should be a database table of all ~718 districts.
DISTRICT_CENTROIDS: dict[tuple[str, str], tuple[float, float]] = {
    # Maharashtra
    ("Pune", "Maharashtra"): (18.52, 73.85),
    ("Mumbai", "Maharashtra"): (19.07, 72.87),
    ("Nagpur", "Maharashtra"): (21.15, 79.09),
    ("Nashik", "Maharashtra"): (19.99, 73.78),
    ("Aurangabad", "Maharashtra"): (19.88, 75.34),
    # Karnataka
    ("Bengaluru", "Karnataka"): (12.97, 77.59),
    ("Mysuru", "Karnataka"): (12.30, 76.65),
    ("Belagavi", "Karnataka"): (15.85, 74.51),
    # Tamil Nadu
    ("Chennai", "Tamil Nadu"): (13.08, 80.27),
    ("Coimbatore", "Tamil Nadu"): (11.02, 76.96),
    ("Madurai", "Tamil Nadu"): (9.93, 78.12),
    ("Thanjavur", "Tamil Nadu"): (10.79, 79.13),
    # Uttar Pradesh
    ("Lucknow", "Uttar Pradesh"): (26.85, 80.95),
    ("Kanpur", "Uttar Pradesh"): (26.45, 80.33),
    ("Varanasi", "Uttar Pradesh"): (25.32, 82.97),
    ("Agra", "Uttar Pradesh"): (27.18, 78.01),
    # Punjab
    ("Ludhiana", "Punjab"): (30.90, 75.86),
    ("Amritsar", "Punjab"): (31.63, 74.87),
    ("Jalandhar", "Punjab"): (31.33, 75.58),
    # Haryana
    ("Gurugram", "Haryana"): (28.46, 77.03),
    ("Karnal", "Haryana"): (29.69, 76.99),
    # Telangana
    ("Hyderabad", "Telangana"): (17.39, 78.49),
    # West Bengal
    ("Kolkata", "West Bengal"): (22.57, 88.36),
    # Gujarat
    ("Ahmedabad", "Gujarat"): (23.02, 72.57),
    ("Surat", "Gujarat"): (21.17, 72.83),
    # Madhya Pradesh
    ("Bhopal", "Madhya Pradesh"): (23.26, 77.41),
    ("Indore", "Madhya Pradesh"): (22.72, 75.86),
    # Rajasthan
    ("Jaipur", "Rajasthan"): (26.91, 75.79),
    ("Jodhpur", "Rajasthan"): (26.28, 73.02),
    # Bihar
    ("Patna", "Bihar"): (25.59, 85.14),
    # Odisha
    ("Bhubaneswar", "Odisha"): (20.30, 85.82),
}


def get_district_centroid(district: str, state: str) -> tuple[float, float]:
    """Get approximate (lat, lon) for a district.

    Falls back to state centroid if district not in our lookup table.
    """
    key = (district, state)
    if key in DISTRICT_CENTROIDS:
        return DISTRICT_CENTROIDS[key]

    # State-level fallbacks
    state_centroids = {
        "Maharashtra": (19.0, 76.0),
        "Karnataka": (15.0, 75.0),
        "Tamil Nadu": (11.0, 78.0),
        "Uttar Pradesh": (27.0, 80.0),
        "Punjab": (31.0, 75.0),
        "Haryana": (29.0, 76.0),
        "Telangana": (17.0, 79.0),
        "West Bengal": (23.0, 88.0),
        "Gujarat": (22.0, 72.0),
        "Madhya Pradesh": (23.0, 78.0),
        "Rajasthan": (27.0, 74.0),
        "Bihar": (25.0, 85.0),
        "Odisha": (20.0, 84.0),
    }
    return state_centroids.get(state, (20.59, 78.96))  # Default: center of India


# ---------------------------------------------------------------------------
# Soil test services
# ---------------------------------------------------------------------------


async def create_manual_soil_test(
    db: AsyncSession,
    plot_id: UUID,
    farmer_id: UUID,
    payload: SoilTestCreate,
) -> SoilTestResponse:
    """Create a soil test from manual lab entry.

    Verifies plot ownership, then stores the test with source=lab_manual.
    """
    # Verify plot ownership
    plot = await farmer_repo.get_plot_by_id(db, plot_id, include_boundary=False)
    if not plot or plot.farmer_id != farmer_id:
        raise NotFoundError("Plot", str(plot_id))

    # Generate fertilizer recommendation based on values
    fertilizer_rec = _generate_fertilizer_recommendation(
        nitrogen=payload.nitrogen_n,
        phosphorus=payload.phosphorus_p,
        potassium=payload.potassium_k,
        ph=payload.ph,
        organic_carbon=payload.organic_carbon,
    )
    amendment_rec = _generate_amendment_recommendation(
        ph=payload.ph,
        ec=payload.electrical_conductivity,
        organic_carbon=payload.organic_carbon,
    )

    # Classify soil texture
    soil_texture = None
    if payload.clay_pct and payload.sand_pct and payload.silt_pct:
        soil_texture = _classify_texture(
            float(payload.clay_pct),
            float(payload.sand_pct),
            float(payload.silt_pct),
        )

    test = await repo.create_soil_test(
        db,
        plot_id=plot_id,
        source=SoilTestSource.LAB_MANUAL,
        test_date=payload.test_date,
        lab_name=payload.lab_name,
        nitrogen_n=payload.nitrogen_n,
        phosphorus_p=payload.phosphorus_p,
        potassium_k=payload.potassium_k,
        ph=payload.ph,
        electrical_conductivity=payload.electrical_conductivity,
        organic_carbon=payload.organic_carbon,
        clay_pct=payload.clay_pct,
        sand_pct=payload.sand_pct,
        silt_pct=payload.silt_pct,
        soil_texture=soil_texture,
        micronutrients=payload.micronutrients,
        fertilizer_recommendation=fertilizer_rec,
        amendment_recommendation=amendment_rec,
        notes=payload.notes,
    )

    logger.info(
        "soil_test.created",
        test_id=str(test.id),
        plot_id=str(plot_id),
        source="lab_manual",
    )

    return SoilTestResponse.model_validate(test)


async def import_shc_soil_test(
    db: AsyncSession,
    plot_id: UUID,
    farmer_id: UUID,
    payload: SHCImportRequest,
) -> SoilTestResponse:
    """Import soil test from the Soil Health Card portal.

    Phase 2 enhancement — currently stubbed. In production, this would
    call the SHC portal API with the SHC ID and parse the response.

    For now, raises NotImplementedError to indicate SHC integration
    is not yet wired up.
    """
    # Verify plot ownership
    plot = await farmer_repo.get_plot_by_id(db, plot_id, include_boundary=False)
    if not plot or plot.farmer_id != farmer_id:
        raise NotFoundError("Plot", str(plot_id))

    raise NotImplementedError(
        "Soil Health Card portal integration is not yet available. "
        "Please use manual entry instead."
    )


async def list_soil_tests(
    db: AsyncSession,
    plot_id: UUID,
    farmer_id: UUID,
    *,
    page: int = 1,
    page_size: int = 20,
) -> SoilTestListResponse:
    """List all soil tests for a plot."""
    plot = await farmer_repo.get_plot_by_id(db, plot_id, include_boundary=False)
    if not plot or plot.farmer_id != farmer_id:
        raise NotFoundError("Plot", str(plot_id))

    tests, total = await repo.list_soil_tests_by_plot(
        db, plot_id, page=page, page_size=page_size
    )
    return SoilTestListResponse(
        tests=[SoilTestResponse.model_validate(t) for t in tests],
        total=total,
        page=page,
        page_size=page_size,
        has_more=(page * page_size) < total,
    )


async def get_soil_test(
    db: AsyncSession,
    test_id: UUID,
    farmer_id: UUID,
) -> SoilTestResponse:
    """Get a soil test by ID (verifies plot ownership)."""
    test = await repo.get_soil_test_by_id(db, test_id)
    if not test:
        raise NotFoundError("SoilTest", str(test_id))

    # Verify ownership via plot
    plot = await farmer_repo.get_plot_by_id(db, test.plot_id, include_boundary=False)
    if not plot or plot.farmer_id != farmer_id:
        raise NotFoundError("SoilTest", str(test_id))

    return SoilTestResponse.model_validate(test)


async def auto_populate_isric_soil_data(
    db: AsyncSession,
    plot_id: UUID,
    centroid: dict[str, float] | None,
) -> SoilTest | None:
    """Auto-populate soil data from ISRIC SoilGrids for a plot.

    Called when a plot is registered. Best-effort — failures are logged
    but don't block plot creation.
    """
    if not centroid or "lon" not in centroid or "lat" not in centroid:
        return None

    isric_client = get_isric_client()
    soil_data = await isric_client.get_soil_data(
        lat=centroid["lat"], lon=centroid["lon"]
    )
    if not soil_data:
        return None

    # Don't create a duplicate ISRIC test if one already exists
    existing_tests, _ = await repo.list_soil_tests_by_plot(
        db, plot_id, page=1, page_size=100
    )
    if any(t.source == SoilTestSource.ISRIC_AUTO for t in existing_tests):
        return None  # Already has ISRIC data

    test = await repo.create_soil_test(
        db,
        plot_id=plot_id,
        source=SoilTestSource.ISRIC_AUTO,
        test_date=date.today(),
        ph=soil_data.ph,
        organic_carbon=soil_data.organic_carbon,
        clay_pct=soil_data.clay_pct,
        sand_pct=soil_data.sand_pct,
        silt_pct=soil_data.silt_pct,
        soil_type=soil_data.soil_type,
        soil_texture=soil_data.soil_type,  # ISRIC gives texture class
        notes=(
            f"Auto-populated from ISRIC SoilGrids at coordinates "
            f"({centroid['lat']:.4f}, {centroid['lon']:.4f}). These are model "
            "predictions at 250m resolution, not actual lab tests."
        ),
    )

    logger.info(
        "soil_test.isric_auto_populated",
        plot_id=str(plot_id),
        ph=str(soil_data.ph) if soil_data.ph else "null",
        soil_type=soil_data.soil_type,
    )
    return test


# ---------------------------------------------------------------------------
# Weather services
# ---------------------------------------------------------------------------


async def sync_district_weather(
    db: AsyncSession,
    district: str,
    state: str,
) -> dict[str, Any]:
    """Sync current weather and 7-day forecast for a district.

    Called by Celery Beat every hour for each district with registered plots.

    Flow:
    1. Try IMD (primary)
    2. If IMD fails, try OWM (fallback)
    3. If both fail, log error and return failure
    4. Upsert observation + forecast into database
    """
    lat, lon = get_district_centroid(district, state)
    imd = get_imd_client()

    # --- Fetch current weather ---
    current = await imd.get_current_weather(district, state, lat, lon)
    source = WeatherDataSource.IMD  # synthetic (dev) weather is still IMD-tagged

    # Try OWM as fallback if IMD failed and OWM is available
    if current is None:
        owm = get_owm_client()
        if owm.is_available:
            current = await owm.get_current_weather(lat, lon)
            if current:
                source = WeatherDataSource.OWM

    if current is None:
        logger.error("weather.sync_failed", district=district, state=state)
        return {"status": "failed", "district": district, "state": state}

    # --- Upsert observation ---
    await repo.upsert_weather_observation(
        db,
        district=district,
        state=state,
        observed_at=current.observed_at,
        source=source,
        temperature_c=current.temperature_c,
        feels_like_c=current.feels_like_c,
        temp_min_c=current.temp_min_c,
        temp_max_c=current.temp_max_c,
        precipitation_mm=current.precipitation_mm,
        humidity_pct=current.humidity_pct,
        wind_speed_kmph=current.wind_speed_kmph,
        wind_direction_deg=current.wind_direction_deg,
        pressure_hpa=current.pressure_hpa,
        cloud_cover_pct=current.cloud_cover_pct,
        weather_main=current.weather_main,
        weather_description=current.weather_description,
        weather_icon=current.weather_icon,
        sunrise_at=current.sunrise_at,
        sunset_at=current.sunset_at,
        raw_data=current.raw_data,
    )

    # --- Fetch and upsert forecast ---
    forecasts = await imd.get_forecast(district, state, lat, lon, days=7)
    issued_at = datetime.now(UTC)

    for fc in forecasts:
        await repo.upsert_weather_forecast(
            db,
            district=district,
            state=state,
            forecast_date=fc.forecast_date,
            issued_at=issued_at,
            source=source,
            temp_min_c=fc.temp_min_c,
            temp_max_c=fc.temp_max_c,
            precipitation_mm=fc.precipitation_mm,
            precipitation_probability=fc.precipitation_probability,
            humidity_min_pct=fc.humidity_min_pct,
            humidity_max_pct=fc.humidity_max_pct,
            wind_speed_kmph=fc.wind_speed_kmph,
            wind_direction_deg=fc.wind_direction_deg,
            weather_main=fc.weather_main,
            weather_description=fc.weather_description,
            weather_icon=fc.weather_icon,
            agromet_advisory=fc.agromet_advisory,
            raw_data=fc.raw_data,
        )

    logger.info(
        "weather.synced",
        district=district,
        state=state,
        source=source.value,
        observations=1,
        forecasts=len(forecasts),
    )

    return {
        "status": "success",
        "district": district,
        "state": state,
        "source": source.value,
        "forecasts_stored": len(forecasts),
    }


async def get_current_weather_for_plot(
    db: AsyncSession,
    plot_id: UUID,
    farmer_id: UUID,
) -> CurrentWeatherResponse:
    """Get current weather for a specific plot.

    Looks up the plot's district, fetches the latest observation from DB
    (or syncs if stale).
    """
    plot = await farmer_repo.get_plot_by_id(db, plot_id, include_boundary=False)
    if not plot or plot.farmer_id != farmer_id:
        raise NotFoundError("Plot", str(plot_id))

    return await _get_current_weather_for_district(db, plot.district, plot.state, plot_id=plot_id)


async def get_current_weather_for_district(
    db: AsyncSession,
    district: str,
    state: str,
) -> CurrentWeatherResponse:
    """Get current weather for a district (public endpoint)."""
    return await _get_current_weather_for_district(db, district, state, plot_id=None)


async def _get_current_weather_for_district(
    db: AsyncSession,
    district: str,
    state: str,
    *,
    plot_id: UUID | None = None,
) -> CurrentWeatherResponse:
    """Internal: get current weather for a district.

    If the latest observation is older than 1 hour, trigger a sync first
    (best-effort, non-blocking).
    """
    # Check if we have a recent observation
    latest = await repo.get_latest_weather_observation(db, district, state)

    if latest:
        age = datetime.now(UTC) - latest.observed_at
        if age > timedelta(hours=2):
            # Trigger sync (best-effort)
            try:
                await sync_district_weather(db, district, state)
                latest = await repo.get_latest_weather_observation(db, district, state)
            except Exception as e:
                logger.warning(
                    "weather.sync_on_demand_failed",
                    district=district,
                    error=str(e),
                )
    else:
        # No observation — sync now
        try:
            await sync_district_weather(db, district, state)
            latest = await repo.get_latest_weather_observation(db, district, state)
        except Exception as e:
            logger.warning(
                "weather.initial_sync_failed",
                district=district,
                error=str(e),
            )

    if not latest:
        raise NotFoundError("Weather", f"{district}, {state}")

    # Generate advisory
    advisory = _generate_current_advisory(latest)

    return CurrentWeatherResponse(
        district=district,
        state=state,
        plot_id=plot_id,
        temperature_c=latest.temperature_c or Decimal("0"),
        feels_like_c=latest.feels_like_c or latest.temperature_c or Decimal("0"),
        temp_min_c=latest.temp_min_c or latest.temperature_c or Decimal("0"),
        temp_max_c=latest.temp_max_c or latest.temperature_c or Decimal("0"),
        precipitation_mm=latest.precipitation_mm or Decimal("0"),
        humidity_pct=latest.humidity_pct or Decimal("0"),
        wind_speed_kmph=latest.wind_speed_kmph or Decimal("0"),
        wind_direction_deg=latest.wind_direction_deg or Decimal("0"),
        pressure_hpa=latest.pressure_hpa or Decimal("1013"),
        cloud_cover_pct=latest.cloud_cover_pct or Decimal("0"),
        weather_main=latest.weather_main or "Unknown",
        weather_description=latest.weather_description or "",
        weather_icon=latest.weather_icon or "",
        observed_at=latest.observed_at,
        sunrise_at=latest.sunrise_at,
        sunset_at=latest.sunset_at,
        source=latest.source,
        agromet_advisory=advisory,
    )


async def get_forecast_for_plot(
    db: AsyncSession,
    plot_id: UUID,
    farmer_id: UUID,
) -> ForecastResponse:
    """Get 7-day forecast for a specific plot."""
    plot = await farmer_repo.get_plot_by_id(db, plot_id, include_boundary=False)
    if not plot or plot.farmer_id != farmer_id:
        raise NotFoundError("Plot", str(plot_id))

    return await _get_forecast_for_district(db, plot.district, plot.state, plot_id=plot_id)


async def get_forecast_for_district(
    db: AsyncSession,
    district: str,
    state: str,
) -> ForecastResponse:
    """Get 7-day forecast for a district (public)."""
    return await _get_forecast_for_district(db, district, state, plot_id=None)


async def _get_forecast_for_district(
    db: AsyncSession,
    district: str,
    state: str,
    *,
    plot_id: UUID | None = None,
) -> ForecastResponse:
    forecasts = await repo.get_latest_forecast(db, district, state, days=7)

    if not forecasts:
        # Sync now
        try:
            await sync_district_weather(db, district, state)
            forecasts = await repo.get_latest_forecast(db, district, state, days=7)
        except Exception as e:
            logger.warning("weather.forecast_sync_failed", district=district, error=str(e))

    if not forecasts:
        raise NotFoundError("Forecast", f"{district}, {state}")

    issued_at = max(f.issued_at for f in forecasts)
    return ForecastResponse(
        district=district,
        state=state,
        plot_id=plot_id,
        forecasts=[
            DailyForecastResponse(
                forecast_date=f.forecast_date,
                temp_min_c=f.temp_min_c or Decimal("0"),
                temp_max_c=f.temp_max_c or Decimal("0"),
                precipitation_mm=f.precipitation_mm or Decimal("0"),
                precipitation_probability=f.precipitation_probability or Decimal("0"),
                humidity_min_pct=f.humidity_min_pct or Decimal("0"),
                humidity_max_pct=f.humidity_max_pct or Decimal("0"),
                wind_speed_kmph=f.wind_speed_kmph or Decimal("0"),
                wind_direction_deg=f.wind_direction_deg or Decimal("0"),
                weather_main=f.weather_main or "Unknown",
                weather_description=f.weather_description or "",
                weather_icon=f.weather_icon or "",
                agromet_advisory=f.agromet_advisory,
                source=f.source,
            )
            for f in forecasts
        ],
        issued_at=issued_at,
    )


async def get_weather_history(
    db: AsyncSession,
    plot_id: UUID,
    farmer_id: UUID,
    *,
    hours: int = 24,
    page: int = 1,
    page_size: int = 100,
) -> WeatherHistoryResponse:
    """Get historical weather observations for a plot."""
    plot = await farmer_repo.get_plot_by_id(db, plot_id, include_boundary=False)
    if not plot or plot.farmer_id != farmer_id:
        raise NotFoundError("Plot", str(plot_id))

    observations, total = await repo.list_weather_history(
        db,
        plot.district,
        plot.state,
        hours=hours,
        page=page,
        page_size=page_size,
    )

    return WeatherHistoryResponse(
        district=plot.district,
        state=plot.state,
        plot_id=plot_id,
        observations=[
            CurrentWeatherResponse(
                district=plot.district,
                state=plot.state,
                plot_id=plot_id,
                temperature_c=o.temperature_c or Decimal("0"),
                feels_like_c=o.feels_like_c or o.temperature_c or Decimal("0"),
                temp_min_c=o.temp_min_c or o.temperature_c or Decimal("0"),
                temp_max_c=o.temp_max_c or o.temperature_c or Decimal("0"),
                precipitation_mm=o.precipitation_mm or Decimal("0"),
                humidity_pct=o.humidity_pct or Decimal("0"),
                wind_speed_kmph=o.wind_speed_kmph or Decimal("0"),
                wind_direction_deg=o.wind_direction_deg or Decimal("0"),
                pressure_hpa=o.pressure_hpa or Decimal("1013"),
                cloud_cover_pct=o.cloud_cover_pct or Decimal("0"),
                weather_main=o.weather_main or "Unknown",
                weather_description=o.weather_description or "",
                weather_icon=o.weather_icon or "",
                observed_at=o.observed_at,
                source=o.source,
            )
            for o in observations
        ],
        total=total,
        page=page,
        page_size=page_size,
        has_more=(page * page_size) < total,
    )


# ---------------------------------------------------------------------------
# Weather alert services
# ---------------------------------------------------------------------------

# Alert thresholds
ALERT_THRESHOLDS = {
    WeatherAlertType.HEAT_WAVE: {
        "temp_max_c": Decimal("42"),  # °C
        "severity_by_temp": [
            (Decimal("45"), WeatherAlertSeverity.CRITICAL),
            (Decimal("43"), WeatherAlertSeverity.SEVERE),
            (Decimal("40"), WeatherAlertSeverity.WARNING),
        ],
    },
    WeatherAlertType.HEAVY_RAIN: {
        "precipitation_mm": Decimal("35"),
        "severity_by_mm": [
            (Decimal("115"), WeatherAlertSeverity.CRITICAL),
            (Decimal("65"), WeatherAlertSeverity.SEVERE),
            (Decimal("35"), WeatherAlertSeverity.WARNING),
        ],
    },
    WeatherAlertType.FROST: {
        "temp_min_c": Decimal("4"),  # Below 4°C
        "severity_by_temp": [
            (Decimal("0"), WeatherAlertSeverity.CRITICAL),
            (Decimal("2"), WeatherAlertSeverity.SEVERE),
            (Decimal("4"), WeatherAlertSeverity.WARNING),
        ],
    },
    WeatherAlertType.HIGH_WIND: {
        "wind_speed_kmph": Decimal("40"),
        "severity_by_speed": [
            (Decimal("75"), WeatherAlertSeverity.CRITICAL),
            (Decimal("60"), WeatherAlertSeverity.SEVERE),
            (Decimal("40"), WeatherAlertSeverity.WARNING),
        ],
    },
}


async def check_and_generate_alerts(
    db: AsyncSession,
    districts: list[tuple[str, str]] | None = None,
) -> list[WeatherAlert]:
    """Check forecasts for all districts and generate alerts where thresholds are exceeded.

    Called by Celery Beat every 3 hours.

    Returns the list of newly created alerts.
    """
    if districts is None:
        districts = await repo.list_districts_with_plots(db)

    new_alerts: list[WeatherAlert] = []

    for district, state in districts:
        try:
            alerts = await _check_district_forecast(db, district, state)
            new_alerts.extend(alerts)
        except Exception as e:
            logger.warning(
                "weather.alert_check_failed",
                district=district,
                state=state,
                error=str(e),
            )

    # Expire old alerts
    expired_count = await repo.expire_old_alerts(db)
    if expired_count:
        logger.info("weather.alerts_expired", count=expired_count)

    logger.info(
        "weather.alert_check_completed",
        districts_checked=len(districts),
        new_alerts=len(new_alerts),
    )

    return new_alerts


async def _check_district_forecast(
    db: AsyncSession,
    district: str,
    state: str,
) -> list[WeatherAlert]:
    """Check the latest forecast for a district and generate alerts if needed."""
    forecasts = await repo.get_latest_forecast(db, district, state, days=3)
    if not forecasts:
        return []

    alerts: list[WeatherAlert] = []

    for fc in forecasts:
        # Heat wave check
        heat_wave_threshold = ALERT_THRESHOLDS[WeatherAlertType.HEAT_WAVE]["temp_max_c"]
        if fc.temp_max_c and fc.temp_max_c >= heat_wave_threshold:
            severity = _get_severity_by_threshold(
                fc.temp_max_c,
                ALERT_THRESHOLDS[WeatherAlertType.HEAT_WAVE]["severity_by_temp"],
            )
            alert = await _create_alert_if_new(
                db,
                district=district,
                state=state,
                alert_type=WeatherAlertType.HEAT_WAVE,
                severity=severity,
                effective_at=datetime.combine(fc.forecast_date, datetime.min.time(), tzinfo=UTC),
                expires_at=datetime.combine(
                    fc.forecast_date + timedelta(days=1), datetime.min.time(), tzinfo=UTC
                ),
                title=f"Heat Wave Warning for {district}, {state}",
                description=(
                    f"Maximum temperature expected to reach {fc.temp_max_c}°C "
                    f"on {fc.forecast_date}."
                ),
                recommended_actions=(
                    "Irrigate crops in early morning or evening. "
                    "Provide shade for sensitive crops. "
                    "Avoid pesticide spraying during peak heat hours."
                ),
            )
            if alert:
                alerts.append(alert)

        # Heavy rain check
        heavy_rain_threshold = ALERT_THRESHOLDS[WeatherAlertType.HEAVY_RAIN]["precipitation_mm"]
        if fc.precipitation_mm and fc.precipitation_mm >= heavy_rain_threshold:
            severity = _get_severity_by_threshold(
                fc.precipitation_mm,
                ALERT_THRESHOLDS[WeatherAlertType.HEAVY_RAIN]["severity_by_mm"],
            )
            alert = await _create_alert_if_new(
                db,
                district=district,
                state=state,
                alert_type=WeatherAlertType.HEAVY_RAIN,
                severity=severity,
                effective_at=datetime.combine(fc.forecast_date, datetime.min.time(), tzinfo=UTC),
                expires_at=datetime.combine(
                    fc.forecast_date + timedelta(days=1), datetime.min.time(), tzinfo=UTC
                ),
                title=f"Heavy Rainfall Warning for {district}, {state}",
                description=(
                    f"Heavy rainfall of {fc.precipitation_mm}mm expected "
                    f"on {fc.forecast_date}."
                ),
                recommended_actions=(
                    "Ensure proper drainage in fields. "
                    "Postpone pesticide and fertilizer application. "
                    "Harvest mature crops before the rain. "
                    "Secure stored produce against water damage."
                ),
            )
            if alert:
                alerts.append(alert)

        # Frost check (winter months)
        frost_threshold = ALERT_THRESHOLDS[WeatherAlertType.FROST]["temp_min_c"]
        if fc.temp_min_c and fc.temp_min_c <= frost_threshold:
            severity = _get_severity_by_threshold(
                fc.temp_min_c,
                ALERT_THRESHOLDS[WeatherAlertType.FROST]["severity_by_temp"],
                reverse=True,  # Lower temp = higher severity
            )
            alert = await _create_alert_if_new(
                db,
                district=district,
                state=state,
                alert_type=WeatherAlertType.FROST,
                severity=severity,
                effective_at=datetime.combine(fc.forecast_date, datetime.min.time(), tzinfo=UTC),
                expires_at=datetime.combine(
                    fc.forecast_date + timedelta(days=1), datetime.min.time(), tzinfo=UTC
                ),
                title=f"Frost Warning for {district}, {state}",
                description=(
                    f"Minimum temperature expected to drop to {fc.temp_min_c}°C "
                    f"on {fc.forecast_date}."
                ),
                recommended_actions=(
                    "Cover sensitive crops with plastic or straw. "
                    "Apply light irrigation in the evening to retain soil heat. "
                    "Use smudge pots or wind machines for high-value crops. "
                    "Harvest mature fruits and vegetables before nightfall."
                ),
            )
            if alert:
                alerts.append(alert)

        # High wind check
        high_wind_threshold = ALERT_THRESHOLDS[WeatherAlertType.HIGH_WIND]["wind_speed_kmph"]
        if fc.wind_speed_kmph and fc.wind_speed_kmph >= high_wind_threshold:
            severity = _get_severity_by_threshold(
                fc.wind_speed_kmph,
                ALERT_THRESHOLDS[WeatherAlertType.HIGH_WIND]["severity_by_speed"],
            )
            alert = await _create_alert_if_new(
                db,
                district=district,
                state=state,
                alert_type=WeatherAlertType.HIGH_WIND,
                severity=severity,
                effective_at=datetime.combine(fc.forecast_date, datetime.min.time(), tzinfo=UTC),
                expires_at=datetime.combine(
                    fc.forecast_date + timedelta(days=1), datetime.min.time(), tzinfo=UTC
                ),
                title=f"High Wind Warning for {district}, {state}",
                description=(
                    f"Wind speeds of {fc.wind_speed_kmph} km/h expected "
                    f"on {fc.forecast_date}."
                ),
                recommended_actions=(
                    "Stake tall crops to prevent lodging. "
                    "Secure greenhouses and protective structures. "
                    "Postpone pesticide spraying. "
                    "Harvest mature fruits to prevent wind-fall losses."
                ),
            )
            if alert:
                alerts.append(alert)

    return alerts


async def _create_alert_if_new(
    db: AsyncSession,
    *,
    district: str,
    state: str,
    alert_type: WeatherAlertType,
    severity: WeatherAlertSeverity,
    effective_at: datetime,
    expires_at: datetime,
    title: str,
    description: str,
    recommended_actions: str,
) -> WeatherAlert | None:
    """Create an alert only if an equivalent active alert doesn't already exist."""
    existing = await repo.find_duplicate_alert(db, district, state, alert_type, severity)
    if existing:
        return None  # Already exists

    return await repo.create_weather_alert(
        db,
        district=district,
        state=state,
        alert_type=alert_type,
        severity=severity,
        effective_at=effective_at,
        expires_at=expires_at,
        title=title,
        description=description,
        recommended_actions=recommended_actions,
    )


def _get_severity_by_threshold(
    value: Decimal,
    thresholds: list[tuple[Decimal, WeatherAlertSeverity]],
    *,
    reverse: bool = False,
) -> WeatherAlertSeverity:
    """Get the appropriate severity for a value based on thresholds.

    For normal direction (heat, rain): higher value = higher severity
    For reverse direction (frost): lower value = higher severity
    """
    sorted_thresholds = sorted(thresholds, key=lambda t: t[0], reverse=not reverse)
    for threshold, severity in sorted_thresholds:
        if reverse:
            if value <= threshold:
                return severity
        else:
            if value >= threshold:
                return severity
    return WeatherAlertSeverity.INFO


async def get_active_alerts_for_plot(
    db: AsyncSession,
    plot_id: UUID,
    farmer_id: UUID,
) -> WeatherAlertListResponse:
    """Get active weather alerts for a plot's district."""
    plot = await farmer_repo.get_plot_by_id(db, plot_id, include_boundary=False)
    if not plot or plot.farmer_id != farmer_id:
        raise NotFoundError("Plot", str(plot_id))

    alerts = await repo.get_active_alerts_for_district(db, plot.district, plot.state)
    return WeatherAlertListResponse(
        alerts=[WeatherAlertResponse.model_validate(a) for a in alerts],
        total=len(alerts),
    )


async def get_active_alerts_for_district(
    db: AsyncSession,
    district: str,
    state: str,
) -> WeatherAlertListResponse:
    """Get active alerts for a district (public)."""
    alerts = await repo.get_active_alerts_for_district(db, district, state)
    return WeatherAlertListResponse(
        alerts=[WeatherAlertResponse.model_validate(a) for a in alerts],
        total=len(alerts),
    )


# ---------------------------------------------------------------------------
# Plot weather summary (aggregated)
# ---------------------------------------------------------------------------


async def get_plot_weather_summary(
    db: AsyncSession,
    plot_id: UUID,
    farmer_id: UUID,
) -> PlotWeatherSummaryResponse:
    """Get aggregated weather summary for a plot.

    Combines current conditions, 7-day forecast, and active alerts into
    a single response — used by the dashboard.
    """
    plot = await farmer_repo.get_plot_by_id(db, plot_id, include_boundary=False)
    if not plot or plot.farmer_id != farmer_id:
        raise NotFoundError("Plot", str(plot_id))

    current = await _get_current_weather_for_district(
        db, plot.district, plot.state, plot_id=plot_id
    )
    forecast_resp = await _get_forecast_for_district(db, plot.district, plot.state, plot_id=plot_id)
    alerts = await repo.get_active_alerts_for_district(db, plot.district, plot.state)

    return PlotWeatherSummaryResponse(
        plot_id=plot_id,
        plot_name=plot.nickname or f"Plot {plot.survey_number}",
        district=plot.district,
        state=plot.state,
        current=current,
        forecast=forecast_resp.forecasts,
        active_alerts=[WeatherAlertResponse.model_validate(a) for a in alerts],
    )


# ---------------------------------------------------------------------------
# Helpers (fertilizer recommendations, advisories, soil classification)
# ---------------------------------------------------------------------------


def _generate_fertilizer_recommendation(
    *,
    nitrogen: Decimal | None,
    phosphorus_p: Decimal | None,
    potassium_k: Decimal | None,
    ph: Decimal | None,
    organic_carbon: Decimal | None,
) -> str | None:
    """Generate NPK fertilizer recommendation based on soil test values.

    Based on ICAR generalized recommendations for Indian soils.
    """
    if not any([nitrogen, phosphorus_p, potassium_k]):
        return None

    recommendations = []

    # N recommendation
    if nitrogen is not None:
        if nitrogen < 150:
            recommendations.append("Apply 80-100 kg N/ha (low N status)")
        elif nitrogen < 280:
            recommendations.append("Apply 40-60 kg N/ha (medium N status)")
        else:
            recommendations.append("Apply 20-30 kg N/ha (high N status)")

    # P recommendation (as P2O5)
    if phosphorus_p is not None:
        if phosphorus_p < 12:
            recommendations.append("Apply 60-80 kg P2O5/ha (low P status)")
        elif phosphorus_p < 25:
            recommendations.append("Apply 30-40 kg P2O5/ha (medium P status)")
        else:
            recommendations.append("Apply 20 kg P2O5/ha (high P status)")

    # K recommendation (as K2O)
    if potassium_k is not None:
        if potassium_k < 110:
            recommendations.append("Apply 40-60 kg K2O/ha (low K status)")
        elif potassium_k < 280:
            recommendations.append("Apply 20-30 kg K2O/ha (medium K status)")
        else:
            recommendations.append("No K application needed (high K status)")

    return ". ".join(recommendations) + "." if recommendations else None


def _generate_amendment_recommendation(
    *,
    ph: Decimal | None,
    ec: Decimal | None,
    organic_carbon: Decimal | None,
) -> str | None:
    """Generate soil amendment recommendation (lime, gypsum, organic matter)."""
    recommendations = []

    if ph is not None:
        if ph < 5.5:
            recommendations.append(
                "Soil is acidic. Apply agricultural lime (CaCO3) at 2-4 tonnes/ha "
                "to raise pH to optimal range (6.0-7.0)."
            )
        elif ph > 8.5:
            recommendations.append(
                "Soil is alkaline. Apply gypsum (CaSO4) at 2-5 tonnes/ha "
                "and incorporate organic matter to lower pH."
            )

    if ec is not None and ec > 2:
        recommendations.append(
            "Soil is saline (high EC). Apply gypsum and provide adequate drainage. "
            "Consider salt-tolerant crop varieties."
        )

    if organic_carbon is not None and organic_carbon < 0.5:
        recommendations.append(
            "Soil organic carbon is very low. Apply 10-20 tonnes/ha of "
            "farmyard manure or compost annually."
        )

    return " ".join(recommendations) if recommendations else None


def _classify_texture(clay: float, sand: float, silt: float) -> str:
    """Classify soil texture using USDA triangle (simplified)."""
    if clay >= 40 and sand <= 45:
        return "Clay"
    if clay >= 27 and sand <= 20:
        return "Silty Clay"
    if clay >= 35 and sand >= 45:
        return "Sandy Clay"
    if clay >= 20 and silt < 50:
        return "Clay Loam" if clay >= 27 else "Sandy Clay Loam"
    if silt >= 50 and clay >= 12:
        return "Silty Clay Loam"
    if silt >= 80:
        return "Silt"
    if silt >= 50:
        return "Silt Loam"
    if sand >= 85:
        return "Sand"
    if sand >= 70:
        return "Loamy Sand"
    if sand >= 43 and clay < 20:
        return "Sandy Loam"
    return "Loam"


def _generate_current_advisory(observation: WeatherObservation) -> str:
    """Generate a brief advisory based on current weather conditions."""
    advisories = []

    temp = float(observation.temperature_c) if observation.temperature_c else 25
    humidity = float(observation.humidity_pct) if observation.humidity_pct else 50
    precip = float(observation.precipitation_mm) if observation.precipitation_mm else 0
    wind = float(observation.wind_speed_kmph) if observation.wind_speed_kmph else 10

    if temp > 40:
        advisories.append("Extreme heat. Irrigate crops early morning or late evening.")
    elif temp > 35:
        advisories.append("Hot conditions. Ensure adequate irrigation.")

    if temp < 5:
        advisories.append("Cold conditions. Protect sensitive crops from frost.")

    if precip > 10:
        advisories.append("Active rainfall. Avoid pesticide spraying.")
    elif precip > 0:
        advisories.append("Light rainfall. Good for sowing and transplanting.")

    if humidity > 85:
        advisories.append("High humidity. Monitor for fungal diseases.")

    if wind > 30:
        advisories.append("Strong winds. Secure tall crops and protective structures.")

    if not advisories:
        advisories.append("Weather conditions are favorable for normal farm operations.")

    return " ".join(advisories)
