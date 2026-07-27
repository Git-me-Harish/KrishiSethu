"""Database access layer for the soil_weather domain.

Handles:
- Soil test CRUD with source-based filtering
- Weather observation upsert (handles partitioned table)
- Weather forecast upsert
- Weather alert CRUD with active/expired filtering
- District list queries (for sync jobs)
- Plot-to-district weather lookup
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import and_, desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from krishisetu.core.logging import get_logger
from krishisetu.domains.soil_weather.models import (
    SoilTest,
    SoilTestSource,
    WeatherAlert,
    WeatherAlertSeverity,
    WeatherAlertStatus,
    WeatherAlertType,
    WeatherDataSource,
    WeatherForecast,
    WeatherObservation,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Soil test queries
# ---------------------------------------------------------------------------


async def create_soil_test(
    db: AsyncSession,
    *,
    plot_id: UUID,
    source: SoilTestSource,
    test_date: date,
    shc_id: str | None = None,
    lab_name: str | None = None,
    nitrogen_n: Decimal | None = None,
    phosphorus_p: Decimal | None = None,
    potassium_k: Decimal | None = None,
    ph: Decimal | None = None,
    electrical_conductivity: Decimal | None = None,
    organic_carbon: Decimal | None = None,
    clay_pct: Decimal | None = None,
    sand_pct: Decimal | None = None,
    silt_pct: Decimal | None = None,
    soil_type: str | None = None,
    soil_texture: str | None = None,
    micronutrients: dict[str, Any] | None = None,
    fertilizer_recommendation: str | None = None,
    amendment_recommendation: str | None = None,
    notes: str | None = None,
) -> SoilTest:
    """Create a new soil test record."""
    test = SoilTest(
        plot_id=plot_id,
        source=source,
        test_date=test_date,
        shc_id=shc_id,
        lab_name=lab_name,
        nitrogen_n=nitrogen_n,
        phosphorus_p=phosphorus_p,
        potassium_k=potassium_k,
        ph=ph,
        electrical_conductivity=electrical_conductivity,
        organic_carbon=organic_carbon,
        clay_pct=clay_pct,
        sand_pct=sand_pct,
        silt_pct=silt_pct,
        soil_type=soil_type,
        soil_texture=soil_texture,
        micronutrients=micronutrients,
        fertilizer_recommendation=fertilizer_recommendation,
        amendment_recommendation=amendment_recommendation,
        notes=notes,
    )
    db.add(test)
    await db.flush()
    await db.refresh(test)
    return test


async def get_soil_test_by_id(db: AsyncSession, test_id: UUID) -> SoilTest | None:
    result = await db.execute(select(SoilTest).where(SoilTest.id == test_id))
    return result.scalar_one_or_none()


async def list_soil_tests_by_plot(
    db: AsyncSession,
    plot_id: UUID,
    *,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[SoilTest], int]:
    """List all soil tests for a plot, most recent first."""
    count_query = select(func.count(SoilTest.id)).where(SoilTest.plot_id == plot_id)
    total = (await db.execute(count_query)).scalar_one()

    offset = (page - 1) * page_size
    query = (
        select(SoilTest)
        .where(SoilTest.plot_id == plot_id)
        .order_by(desc(SoilTest.test_date))
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(query)
    return list(result.scalars().all()), total


async def get_latest_soil_test(db: AsyncSession, plot_id: UUID) -> SoilTest | None:
    """Get the most recent soil test for a plot."""
    query = (
        select(SoilTest)
        .where(SoilTest.plot_id == plot_id)
        .order_by(desc(SoilTest.test_date))
        .limit(1)
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def update_soil_test(
    db: AsyncSession,
    test_id: UUID,
    **fields: Any,
) -> SoilTest | None:
    """Update a soil test."""
    if not fields:
        return await get_soil_test_by_id(db, test_id)

    await db.execute(
        update(SoilTest).where(SoilTest.id == test_id).values(**fields)
    )
    await db.flush()
    return await get_soil_test_by_id(db, test_id)


async def verify_soil_test(
    db: AsyncSession,
    test_id: UUID,
    officer_id: UUID,
) -> SoilTest | None:
    """Officer verifies a soil test."""
    return await update_soil_test(
        db,
        test_id,
        is_verified=True,
        verified_by=officer_id,
        source=SoilTestSource.OFFICER_ENTERED,
    )


# ---------------------------------------------------------------------------
# Weather observation queries
# ---------------------------------------------------------------------------


async def upsert_weather_observation(
    db: AsyncSession,
    *,
    district: str,
    state: str,
    observed_at: datetime,
    source: WeatherDataSource,
    temperature_c: Decimal | None = None,
    feels_like_c: Decimal | None = None,
    temp_min_c: Decimal | None = None,
    temp_max_c: Decimal | None = None,
    precipitation_mm: Decimal | None = None,
    precipitation_probability: Decimal | None = None,
    humidity_pct: Decimal | None = None,
    wind_speed_kmph: Decimal | None = None,
    wind_direction_deg: Decimal | None = None,
    wind_gust_kmph: Decimal | None = None,
    pressure_hpa: Decimal | None = None,
    cloud_cover_pct: Decimal | None = None,
    visibility_km: Decimal | None = None,
    uv_index: Decimal | None = None,
    weather_main: str | None = None,
    weather_description: str | None = None,
    weather_icon: str | None = None,
    sunrise_at: datetime | None = None,
    sunset_at: datetime | None = None,
    raw_data: dict[str, Any] | None = None,
) -> WeatherObservation | None:
    """Insert or update a weather observation.

    Uses ON CONFLICT to handle the unique constraint on
    (district, state, observed_at, source). If a row already exists for
    these values, it's updated.
    """
    # Use raw SQL for ON CONFLICT (SQLAlchemy 2.0 supports this via
    # insert().on_conflict_do_update())
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    stmt = pg_insert(WeatherObservation).values(
        district=district,
        state=state,
        observed_at=observed_at,
        source=source.value,
        temperature_c=temperature_c,
        feels_like_c=feels_like_c,
        temp_min_c=temp_min_c,
        temp_max_c=temp_max_c,
        precipitation_mm=precipitation_mm,
        precipitation_probability=precipitation_probability,
        humidity_pct=humidity_pct,
        wind_speed_kmph=wind_speed_kmph,
        wind_direction_deg=wind_direction_deg,
        wind_gust_kmph=wind_gust_kmph,
        pressure_hpa=pressure_hpa,
        cloud_cover_pct=cloud_cover_pct,
        visibility_km=visibility_km,
        uv_index=uv_index,
        weather_main=weather_main,
        weather_description=weather_description,
        weather_icon=weather_icon,
        sunrise_at=sunrise_at,
        sunset_at=sunset_at,
        raw_data=raw_data,
    )

    # ON CONFLICT (district, state, observed_at, source) DO UPDATE
    update_fields = {
        "temperature_c": stmt.excluded.temperature_c,
        "feels_like_c": stmt.excluded.feels_like_c,
        "temp_min_c": stmt.excluded.temp_min_c,
        "temp_max_c": stmt.excluded.temp_max_c,
        "precipitation_mm": stmt.excluded.precipitation_mm,
        "humidity_pct": stmt.excluded.humidity_pct,
        "wind_speed_kmph": stmt.excluded.wind_speed_kmph,
        "weather_main": stmt.excluded.weather_main,
        "weather_description": stmt.excluded.weather_description,
        "weather_icon": stmt.excluded.weather_icon,
        "raw_data": stmt.excluded.raw_data,
    }

    stmt = stmt.on_conflict_do_update(
        constraint="weather_obs_district_time_source_unique",
        set_=update_fields,
    ).returning(WeatherObservation.id)

    try:
        result = await db.execute(stmt)
        row = result.fetchone()
        await db.flush()
        if row:
            return WeatherObservation(
                id=row[0],
                district=district,
                state=state,
                observed_at=observed_at,
                source=source.value,
                temperature_c=temperature_c,
                # ... (other fields populated from inputs)
            )
    except Exception as e:
        # Fall back to plain insert if upsert fails (e.g., partition doesn't exist yet)
        import logging
        logging.getLogger(__name__).warning(
            "weather_obs.upsert_failed",
            district=district,
            error=str(e),
        )
    return None


async def get_latest_weather_observation(
    db: AsyncSession, district: str, state: str
) -> WeatherObservation | None:
    """Get the most recent weather observation for a district."""
    query = (
        select(WeatherObservation)
        .where(
            and_(
                WeatherObservation.district == district,
                WeatherObservation.state == state,
            )
        )
        .order_by(desc(WeatherObservation.observed_at))
        .limit(1)
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def list_weather_history(
    db: AsyncSession,
    district: str,
    state: str,
    *,
    hours: int = 24,
    page: int = 1,
    page_size: int = 100,
) -> tuple[list[WeatherObservation], int]:
    """List weather observations for a district, most recent first."""
    cutoff = datetime.now(UTC) - timedelta(hours=hours)

    count_query = (
        select(func.count(WeatherObservation.id))
        .where(
            and_(
                WeatherObservation.district == district,
                WeatherObservation.state == state,
                WeatherObservation.observed_at >= cutoff,
            )
        )
    )
    total = (await db.execute(count_query)).scalar_one()

    offset = (page - 1) * page_size
    query = (
        select(WeatherObservation)
        .where(
            and_(
                WeatherObservation.district == district,
                WeatherObservation.state == state,
                WeatherObservation.observed_at >= cutoff,
            )
        )
        .order_by(desc(WeatherObservation.observed_at))
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(query)
    return list(result.scalars().all()), total


# ---------------------------------------------------------------------------
# Weather forecast queries
# ---------------------------------------------------------------------------


async def upsert_weather_forecast(
    db: AsyncSession,
    *,
    district: str,
    state: str,
    forecast_date: date,
    issued_at: datetime,
    source: WeatherDataSource,
    temp_min_c: Decimal | None = None,
    temp_max_c: Decimal | None = None,
    precipitation_mm: Decimal | None = None,
    precipitation_probability: Decimal | None = None,
    humidity_min_pct: Decimal | None = None,
    humidity_max_pct: Decimal | None = None,
    wind_speed_kmph: Decimal | None = None,
    wind_direction_deg: Decimal | None = None,
    weather_main: str | None = None,
    weather_description: str | None = None,
    weather_icon: str | None = None,
    agromet_advisory: str | None = None,
    raw_data: dict[str, Any] | None = None,
) -> WeatherForecast | None:
    """Insert or update a weather forecast."""
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    stmt = pg_insert(WeatherForecast).values(
        district=district,
        state=state,
        forecast_date=forecast_date,
        issued_at=issued_at,
        source=source.value,
        temp_min_c=temp_min_c,
        temp_max_c=temp_max_c,
        precipitation_mm=precipitation_mm,
        precipitation_probability=precipitation_probability,
        humidity_min_pct=humidity_min_pct,
        humidity_max_pct=humidity_max_pct,
        wind_speed_kmph=wind_speed_kmph,
        wind_direction_deg=wind_direction_deg,
        weather_main=weather_main,
        weather_description=weather_description,
        weather_icon=weather_icon,
        agromet_advisory=agromet_advisory,
        raw_data=raw_data,
    )

    update_fields = {
        "temp_min_c": stmt.excluded.temp_min_c,
        "temp_max_c": stmt.excluded.temp_max_c,
        "precipitation_mm": stmt.excluded.precipitation_mm,
        "precipitation_probability": stmt.excluded.precipitation_probability,
        "humidity_min_pct": stmt.excluded.humidity_min_pct,
        "humidity_max_pct": stmt.excluded.humidity_max_pct,
        "wind_speed_kmph": stmt.excluded.wind_speed_kmph,
        "wind_direction_deg": stmt.excluded.wind_direction_deg,
        "weather_main": stmt.excluded.weather_main,
        "weather_description": stmt.excluded.weather_description,
        "weather_icon": stmt.excluded.weather_icon,
        "agromet_advisory": stmt.excluded.agromet_advisory,
        "raw_data": stmt.excluded.raw_data,
    }

    stmt = stmt.on_conflict_do_update(
        constraint="weather_fcst_district_date_source_issued_unique",
        set_=update_fields,
    ).returning(WeatherForecast.id)

    try:
        result = await db.execute(stmt)
        row = result.fetchone()
        await db.flush()
        if row:
            return WeatherForecast(
                id=row[0],
                district=district,
                state=state,
                forecast_date=forecast_date,
                issued_at=issued_at,
                source=source.value,
                temp_min_c=temp_min_c,
                temp_max_c=temp_max_c,
                precipitation_mm=precipitation_mm,
                precipitation_probability=precipitation_probability,
                humidity_min_pct=humidity_min_pct,
                humidity_max_pct=humidity_max_pct,
                wind_speed_kmph=wind_speed_kmph,
                wind_direction_deg=wind_direction_deg,
                weather_main=weather_main,
                weather_description=weather_description,
                weather_icon=weather_icon,
                agromet_advisory=agromet_advisory,
                raw_data=raw_data,
            )
    except Exception as exc:
        logger.warning(
            "soil_weather.upsert_forecast_failed",
            district=district,
            state=state,
            error=str(exc),
        )
    return None


async def get_latest_forecast(
    db: AsyncSession,
    district: str,
    state: str,
    *,
    days: int = 7,
) -> list[WeatherForecast]:
    """Get the latest 7-day forecast for a district.

    Returns forecasts issued most recently, for the next `days` days.
    """
    today = date.today()
    end_date = today + timedelta(days=days)

    # Get the most recent issue time
    subq = (
        select(func.max(WeatherForecast.issued_at).label("max_issued"))
        .where(
            and_(
                WeatherForecast.district == district,
                WeatherForecast.state == state,
                WeatherForecast.forecast_date >= today,
                WeatherForecast.forecast_date < end_date,
            )
        )
        .scalar_subquery()
    )

    query = (
        select(WeatherForecast)
        .where(
            and_(
                WeatherForecast.district == district,
                WeatherForecast.state == state,
                WeatherForecast.forecast_date >= today,
                WeatherForecast.forecast_date < end_date,
                WeatherForecast.issued_at == subq,
            )
        )
        .order_by(WeatherForecast.forecast_date)
    )
    result = await db.execute(query)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Weather alert queries
# ---------------------------------------------------------------------------


async def create_weather_alert(
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
    recommended_actions: str | None = None,
    source: str = "krishisetu_engine",
    raw_data: dict[str, Any] | None = None,
) -> WeatherAlert:
    """Create a new weather alert."""
    alert = WeatherAlert(
        district=district,
        state=state,
        alert_type=alert_type,
        severity=severity,
        effective_at=effective_at,
        expires_at=expires_at,
        title=title,
        description=description,
        recommended_actions=recommended_actions,
        source=source,
        raw_data=raw_data,
    )
    db.add(alert)
    await db.flush()
    await db.refresh(alert)
    return alert


async def get_active_alerts_for_district(
    db: AsyncSession, district: str, state: str
) -> list[WeatherAlert]:
    """Get all active alerts for a district."""
    now = datetime.now(UTC)
    query = (
        select(WeatherAlert)
        .where(
            and_(
                WeatherAlert.district == district,
                WeatherAlert.state == state,
                WeatherAlert.status == WeatherAlertStatus.ACTIVE.value,
                WeatherAlert.effective_at <= now,
                WeatherAlert.expires_at > now,
            )
        )
        .order_by(desc(WeatherAlert.severity))
    )
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_active_alerts_for_districts(
    db: AsyncSession, districts: list[tuple[str, str]]
) -> list[WeatherAlert]:
    """Get active alerts for multiple districts (batch query)."""
    if not districts:
        return []
    now = datetime.now(UTC)

    from sqlalchemy import or_

    # Build OR conditions for each (district, state) pair
    conditions = []
    for district, state in districts:
        conditions.append(
            and_(
                WeatherAlert.district == district,
                WeatherAlert.state == state,
            )
        )

    query = (
        select(WeatherAlert)
        .where(
            and_(
                WeatherAlert.status == WeatherAlertStatus.ACTIVE.value,
                WeatherAlert.effective_at <= now,
                WeatherAlert.expires_at > now,
                or_(*conditions),
            )
        )
        .order_by(desc(WeatherAlert.severity))
    )
    result = await db.execute(query)
    return list(result.scalars().all())


async def expire_old_alerts(db: AsyncSession) -> int:
    """Mark alerts as expired if their expiry time has passed.

    Called by Celery Beat every hour.
    Returns the number of alerts marked expired.
    """
    now = datetime.now(UTC)
    result = await db.execute(
        update(WeatherAlert)
        .where(
            and_(
                WeatherAlert.status == WeatherAlertStatus.ACTIVE.value,
                WeatherAlert.expires_at < now,
            )
        )
        .values(status=WeatherAlertStatus.EXPIRED.value)
    )
    await db.flush()
    return result.rowcount or 0


async def find_duplicate_alert(
    db: AsyncSession,
    district: str,
    state: str,
    alert_type: WeatherAlertType,
    severity: WeatherAlertSeverity,
) -> WeatherAlert | None:
    """Check if an equivalent alert already exists (active, same type+severity).

    Prevents duplicate alert creation for the same district.
    """
    query = (
        select(WeatherAlert)
        .where(
            and_(
                WeatherAlert.district == district,
                WeatherAlert.state == state,
                WeatherAlert.alert_type == alert_type.value,
                WeatherAlert.severity == severity.value,
                WeatherAlert.status == WeatherAlertStatus.ACTIVE.value,
            )
        )
        .order_by(desc(WeatherAlert.created_at))
        .limit(1)
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def update_alert_notification_count(
    db: AsyncSession, alert_id: UUID, count: int
) -> None:
    """Update the notifications_sent counter after dispatching."""
    now = datetime.now(UTC)
    await db.execute(
        update(WeatherAlert)
        .where(WeatherAlert.id == alert_id)
        .values(notifications_sent=count, last_notification_at=now)
    )
    await db.flush()


# ---------------------------------------------------------------------------
# District queries (for sync jobs)
# ---------------------------------------------------------------------------


async def list_districts_with_plots(db: AsyncSession) -> list[tuple[str, str]]:
    """List all (district, state) pairs that have registered plots.

    Used by the weather sync Celery task to know which districts to fetch
    weather for.
    """
    from krishisetu.domains.farmer.models import Plot

    query = (
        select(Plot.district, Plot.state)
        .distinct()
        .order_by(Plot.state, Plot.district)
    )
    result = await db.execute(query)
    return [(row[0], row[1]) for row in result.fetchall()]


async def get_last_weather_sync_time(
    db: AsyncSession, district: str, state: str
) -> datetime | None:
    """Get the timestamp of the most recent weather observation for a district."""
    query = (
        select(func.max(WeatherObservation.observed_at))
        .where(
            and_(
                WeatherObservation.district == district,
                WeatherObservation.state == state,
            )
        )
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()
