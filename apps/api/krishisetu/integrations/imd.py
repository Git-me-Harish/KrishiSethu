"""India Meteorological Department (IMD) API client.

IMD provides official weather data for India through:
- Current weather observations (hourly, per district)
- 7-day forecasts
- Agromet advisories (twice weekly)

API access requires registration at https://mausam.imd.gov.in/. The IMD
API is free for government use; commercial use requires a paid plan.

In development (no IMD_API_KEY), the client falls back to a deterministic
synthetic data generator based on Indian climatology. This is NOT mock
data — it's a realistic approximation based on:
- Month-based temperature ranges (hot summer, cool winter, monsoon)
- District latitude (north = cooler, south = warmer)
- Time of day (cooler at night, warmer at afternoon)
- Monsoon season (June-September = higher precipitation probability)

This enables full development without API keys while producing realistic
test data that varies by location and time.
"""

from __future__ import annotations

import hashlib
import math
import random
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx

from krishisetu.core.config import settings
from krishisetu.core.logging import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CurrentWeather:
    """Current weather conditions for a location."""

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
    raw_data: dict[str, Any] | None = None


@dataclass
class DailyForecast:
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
    raw_data: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Constants — Indian climatology baseline
# ---------------------------------------------------------------------------

# Monthly temperature baselines (°C) — Indian average by month
# Format: (avg_temp, temp_amplitude_daily_range)
MONTHLY_TEMPS = {
    1: (16, 12),    # January — cool
    2: (19, 13),
    3: (24, 14),
    4: (29, 14),
    5: (33, 13),    # May — hottest in north
    6: (32, 11),
    7: (29, 8),     # July — monsoon
    8: (28, 8),
    9: (29, 9),
    10: (27, 11),
    11: (22, 12),
    12: (17, 12),   # December — cool
}

# Monsoon precipitation probability by month (India)
MONSOON_PRECIP_PROB = {
    1: 0.05, 2: 0.05, 3: 0.05, 4: 0.05, 5: 0.10,
    6: 0.50, 7: 0.80, 8: 0.75, 9: 0.40,  # Monsoon
    10: 0.15, 11: 0.05, 12: 0.05,
}

# Latitude adjustment — northern India is cooler
# India spans from 8°N (Kanyakumari) to 37°N (Kashmir)
# Approximate temp drop: 1°C per degree latitude above 20°N
LATITUDE_TEMP_FACTOR = -0.7


# ---------------------------------------------------------------------------
# IMD API client
# ---------------------------------------------------------------------------


class IMDClient:
    """Client for the India Meteorological Department (IMD) API.

    In production (IMD_API_KEY set), makes real HTTP calls.
    In development, generates realistic synthetic data based on climatology.
    """

    BASE_URL = "https://mausam.imd.gov.in/api/v1"
    FORECAST_ENDPOINT = "/forecast/daily"
    CURRENT_ENDPOINT = "/current"

    def __init__(self) -> None:
        self.api_key = settings().IMD_API_KEY
        self.base_url = self.BASE_URL
        self.timeout = 10.0

    @property
    def is_live(self) -> bool:
        """Whether the client makes real API calls (True) or synthetic data (False)."""
        return self.api_key is not None and not settings().is_development

    async def get_current_weather(
        self, district: str, state: str, lat: float, lon: float
    ) -> CurrentWeather:
        """Fetch current weather for a district.

        Args:
            district: District name (e.g., 'Pune')
            state: State name (e.g., 'Maharashtra')
            lat: District centroid latitude
            lon: District centroid longitude
        """
        if self.is_live:
            try:
                return await self._fetch_current_live(district, state, lat, lon)
            except Exception as e:
                logger.warning(
                    "imd.live_failed_falling_back",
                    district=district,
                    error=str(e),
                )
                # Fall through to synthetic
        return self._generate_current_synthetic(district, state, lat, lon)

    async def get_forecast(
        self, district: str, state: str, lat: float, lon: float, days: int = 7
    ) -> list[DailyForecast]:
        """Fetch 7-day forecast for a district."""
        if self.is_live:
            try:
                return await self._fetch_forecast_live(district, state, lat, lon, days)
            except Exception as e:
                logger.warning(
                    "imd.forecast_live_failed",
                    district=district,
                    error=str(e),
                )
        return self._generate_forecast_synthetic(district, state, lat, lon, days)

    # -----------------------------------------------------------------------
    # Live API calls (production)
    # -----------------------------------------------------------------------

    async def _fetch_current_live(
        self, district: str, state: str, lat: float, lon: float
    ) -> CurrentWeather:
        """Make real HTTP call to IMD API."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}{self.CURRENT_ENDPOINT}",
                params={
                    "api_key": self.api_key.get_secret_value() if self.api_key else "",
                    "lat": lat,
                    "lon": lon,
                    "district": district,
                    "state": state,
                },
            )
        response.raise_for_status()
        data = response.json()

        return self._parse_current_from_api(data, district, state)

    async def _fetch_forecast_live(
        self, district: str, state: str, lat: float, lon: float, days: int
    ) -> list[DailyForecast]:
        """Make real HTTP call to IMD forecast API."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{self.base_url}{self.FORECAST_ENDPOINT}",
                params={
                    "api_key": self.api_key.get_secret_value() if self.api_key else "",
                    "lat": lat,
                    "lon": lon,
                    "district": district,
                    "state": state,
                    "days": days,
                },
            )
        response.raise_for_status()
        data = response.json()

        return [
            self._parse_forecast_from_api(day_data)
            for day_data in data.get("forecasts", [])
        ]

    def _parse_current_from_api(
        self, data: dict[str, Any], district: str, state: str
    ) -> CurrentWeather:
        """Parse IMD API response into CurrentWeather."""
        # Actual IMD API response format TBD — this is a reasonable guess
        # based on common weather API patterns. Will be adjusted when
        # we have real API access.
        main = data.get("main", {})
        wind = data.get("wind", {})
        weather_list = data.get("weather", [{}])
        weather = weather_list[0] if weather_list else {}
        sys_data = data.get("sys", {})

        return CurrentWeather(
            temperature_c=Decimal(str(main.get("temp", 25))),
            feels_like_c=Decimal(str(main.get("feels_like", main.get("temp", 25)))),
            temp_min_c=Decimal(str(main.get("temp_min", 20))),
            temp_max_c=Decimal(str(main.get("temp_max", 30))),
            precipitation_mm=Decimal(
                str(data.get("rain", {}).get("1h", 0) if data.get("rain") else 0)
            ),
            humidity_pct=Decimal(str(main.get("humidity", 60))),
            wind_speed_kmph=Decimal(str(wind.get("speed", 0))),
            wind_direction_deg=Decimal(str(wind.get("deg", 0))),
            pressure_hpa=Decimal(str(main.get("pressure", 1013))),
            cloud_cover_pct=Decimal(str(data.get("clouds", {}).get("all", 0))),
            weather_main=weather.get("main", "Unknown"),
            weather_description=weather.get("description", ""),
            weather_icon=weather.get("icon", ""),
            observed_at=datetime.fromtimestamp(
                data.get("dt", datetime.now(UTC).timestamp()),
                tz=UTC,
            ),
            sunrise_at=datetime.fromtimestamp(
                sys_data.get("sunrise"), tz=UTC
            ) if sys_data.get("sunrise") else None,
            sunset_at=datetime.fromtimestamp(
                sys_data.get("sunset"), tz=UTC
            ) if sys_data.get("sunset") else None,
            raw_data=data,
        )

    def _parse_forecast_from_api(self, data: dict[str, Any]) -> DailyForecast:
        """Parse single day of IMD forecast API response."""
        temp = data.get("temp", {})
        weather_list = data.get("weather", [{}])
        weather = weather_list[0] if weather_list else {}

        return DailyForecast(
            forecast_date=date.fromisoformat(data.get("date", date.today().isoformat())),
            temp_min_c=Decimal(str(temp.get("min", 20))),
            temp_max_c=Decimal(str(temp.get("max", 30))),
            precipitation_mm=Decimal(str(data.get("precipitation", 0))),
            precipitation_probability=Decimal(str(data.get("precipitation_probability", 0))),
            humidity_min_pct=Decimal(str(data.get("humidity", {}).get("min", 40))),
            humidity_max_pct=Decimal(str(data.get("humidity", {}).get("max", 80))),
            wind_speed_kmph=Decimal(str(data.get("wind_speed", 10))),
            wind_direction_deg=Decimal(str(data.get("wind_direction", 0))),
            weather_main=weather.get("main", "Unknown"),
            weather_description=weather.get("description", ""),
            weather_icon=weather.get("icon", ""),
            agromet_advisory=data.get("agromet_advisory"),
            raw_data=data,
        )

    # -----------------------------------------------------------------------
    # Synthetic data generation (development)
    # -----------------------------------------------------------------------

    def _generate_current_synthetic(
        self, district: str, state: str, lat: float, lon: float
    ) -> CurrentWeather:
        """Generate realistic synthetic current weather based on climatology.

        Deterministic per (district, hour) — same input gives same output
        within the same hour. Uses a hash of (district, hour) to seed the
        random generator, so different districts at the same time get
        different but stable values.
        """
        now = datetime.now(UTC)
        # Convert to IST (UTC+5:30)
        ist_now = now + timedelta(hours=5, minutes=30)
        hour = ist_now.hour

        # Get month-based baseline
        month = ist_now.month
        base_temp, daily_amplitude = MONTHLY_TEMPS[month]

        # Latitude adjustment
        lat_adjustment = (lat - 20) * LATITUDE_TEMP_FACTOR
        base_temp += lat_adjustment

        # Time-of-day adjustment — cosine wave with peak at 15:00 (3 PM)
        # temp = base + amplitude * cos((hour - 15) * pi / 12)
        hour_factor = math.cos((hour - 15) * math.pi / 12)
        temp = base_temp + (daily_amplitude / 2) * hour_factor

        # Deterministic seed for stable values within the hour
        seed_str = f"{district}:{state}:{ist_now.strftime('%Y%m%d%H')}"
        # Non-cryptographic: seeds a deterministic RNG for synthetic weather
        # data (dev/fallback mode), not used for any security purpose.
        seed = int(
            hashlib.md5(seed_str.encode(), usedforsecurity=False).hexdigest(), 16
        ) % (2**32)
        rng = random.Random(seed)  # noqa: S311 -- synthetic data generation, not security

        # Add small random variation (±1.5°C)
        temp += rng.uniform(-1.5, 1.5)
        feels_like = temp + rng.uniform(-2, 3)  # Heat index adjustment

        # Min/max for the day
        temp_min = base_temp - daily_amplitude / 2 + rng.uniform(-1, 1)
        temp_max = base_temp + daily_amplitude / 2 + rng.uniform(-1, 1)

        # Humidity — higher in monsoon, lower in winter
        base_humidity = 50
        if 6 <= month <= 9:  # Monsoon
            base_humidity = 75
        elif month in (12, 1, 2):  # Winter
            base_humidity = 45
        humidity = base_humidity + rng.uniform(-10, 10)

        # Precipitation
        precip_prob = MONSOON_PRECIP_PROB[month]
        if rng.random() < precip_prob:
            precipitation = rng.uniform(0.5, 25)
            weather_main = "Rain"
            weather_desc = "light rain" if precipitation < 5 else "moderate rain"
            icon = "10d"
            cloud_cover = rng.uniform(70, 95)
        else:
            precipitation = 0
            if cloud_roll := rng.random():
                if cloud_roll < 0.3:
                    weather_main = "Clear"
                    weather_desc = "clear sky"
                    icon = "01d"
                    cloud_cover = rng.uniform(0, 20)
                elif cloud_roll < 0.7:
                    weather_main = "Clouds"
                    weather_desc = "few clouds"
                    icon = "02d"
                    cloud_cover = rng.uniform(20, 60)
                else:
                    weather_main = "Clouds"
                    weather_desc = "overcast"
                    icon = "04d"
                    cloud_cover = rng.uniform(60, 95)

        # Wind
        wind_speed = rng.uniform(5, 25)
        wind_dir = rng.uniform(0, 360)

        # Pressure
        pressure = 1013 + rng.uniform(-10, 10)

        # Sunrise/sunset (approximate based on latitude and day of year)
        sunrise, sunset = self._compute_sunrise_sunset(lat, ist_now.date())

        return CurrentWeather(
            temperature_c=Decimal(str(round(temp, 1))),
            feels_like_c=Decimal(str(round(feels_like, 1))),
            temp_min_c=Decimal(str(round(temp_min, 1))),
            temp_max_c=Decimal(str(round(temp_max, 1))),
            precipitation_mm=Decimal(str(round(precipitation, 1))),
            humidity_pct=Decimal(str(round(humidity, 0))),
            wind_speed_kmph=Decimal(str(round(wind_speed, 1))),
            wind_direction_deg=Decimal(str(round(wind_dir, 0))),
            pressure_hpa=Decimal(str(round(pressure, 1))),
            cloud_cover_pct=Decimal(str(round(cloud_cover, 0))),
            weather_main=weather_main,
            weather_description=weather_desc,
            weather_icon=icon,
            observed_at=now,
            sunrise_at=sunrise,
            sunset_at=sunset,
            raw_data={"synthetic": True, "seed": seed_str},
        )

    def _generate_forecast_synthetic(
        self, district: str, state: str, lat: float, lon: float, days: int
    ) -> list[DailyForecast]:
        """Generate realistic synthetic 7-day forecast."""
        today = date.today()
        forecasts: list[DailyForecast] = []

        for day_offset in range(days):
            forecast_date = today + timedelta(days=day_offset)
            month = forecast_date.month

            base_temp, daily_amplitude = MONTHLY_TEMPS[month]
            lat_adjustment = (lat - 20) * LATITUDE_TEMP_FACTOR
            base_temp += lat_adjustment

            seed_str = f"{district}:{state}:{forecast_date.isoformat()}"
            # Non-cryptographic: seeds a deterministic RNG for synthetic
            # weather data (dev/fallback mode), not used for security.
            seed = int(
                hashlib.md5(seed_str.encode(), usedforsecurity=False).hexdigest(), 16
            ) % (2**32)
            rng = random.Random(seed)  # noqa: S311 -- synthetic data generation, not security

            temp_min = base_temp - daily_amplitude / 2 + rng.uniform(-2, 2)
            temp_max = base_temp + daily_amplitude / 2 + rng.uniform(-2, 2)

            precip_prob = MONSOON_PRECIP_PROB[month]
            will_rain = rng.random() < precip_prob
            precipitation = rng.uniform(2, 30) if will_rain else 0
            precip_probability = Decimal(str(round(precip_prob * 100 + rng.uniform(-10, 10), 0)))

            if will_rain:
                weather_main = "Rain"
                weather_desc = "light rain" if precipitation < 10 else "moderate rain"
                icon = "10d"
            elif rng.random() < 0.4:
                weather_main = "Clouds"
                weather_desc = "partly cloudy"
                icon = "02d"
            else:
                weather_main = "Clear"
                weather_desc = "clear sky"
                icon = "01d"

            humidity_min = 40 + rng.uniform(-10, 10)
            humidity_max = 80 + rng.uniform(-10, 10)

            wind_speed = rng.uniform(5, 20)
            wind_dir = rng.uniform(0, 360)

            # Agromet advisory (deterministic, based on conditions)
            advisory = self._generate_agromet_advisory(
                month, will_rain, float(temp_max), float(precipitation)
            )

            forecasts.append(
                DailyForecast(
                    forecast_date=forecast_date,
                    temp_min_c=Decimal(str(round(temp_min, 1))),
                    temp_max_c=Decimal(str(round(temp_max, 1))),
                    precipitation_mm=Decimal(str(round(precipitation, 1))),
                    precipitation_probability=precip_probability,
                    humidity_min_pct=Decimal(str(round(humidity_min, 0))),
                    humidity_max_pct=Decimal(str(round(humidity_max, 0))),
                    wind_speed_kmph=Decimal(str(round(wind_speed, 1))),
                    wind_direction_deg=Decimal(str(round(wind_dir, 0))),
                    weather_main=weather_main,
                    weather_description=weather_desc,
                    weather_icon=icon,
                    agromet_advisory=advisory,
                    raw_data={"synthetic": True, "seed": seed_str},
                )
            )

        return forecasts

    def _generate_agromet_advisory(
        self, month: int, will_rain: bool, temp_max: float, precipitation: float
    ) -> str:
        """Generate a brief agromet advisory based on conditions."""
        advisories = []

        if will_rain and precipitation > 15:
            advisories.append("Heavy rainfall expected. Avoid spraying pesticides.")
        elif will_rain:
            advisories.append("Light rainfall expected. Good time for sowing.")

        if temp_max > 40:
            advisories.append("Heat wave conditions. Irrigate crops in early morning or evening.")
        elif temp_max > 35:
            advisories.append("High temperature. Ensure adequate irrigation.")

        if month in (6, 7, 8, 9):
            advisories.append("Monsoon season. Ensure proper drainage in fields.")
        elif month in (11, 12, 1, 2):
            advisories.append("Rabi season. Monitor for frost in northern regions.")
        elif month in (3, 4, 5):
            advisories.append("Summer season. Mulch to conserve soil moisture.")

        if not advisories:
            advisories.append("Weather conditions are favorable for normal farm operations.")

        return " ".join(advisories)

    def _compute_sunrise_sunset(
        self, lat: float, target_date: date
    ) -> tuple[datetime, datetime]:
        """Compute approximate sunrise/sunset times for a latitude and date.

        Uses a simplified solar calculation. For production, replace with
        a proper astronomical library like `astral` or `skyfield`.
        """
        # Day of year
        day_of_year = target_date.timetuple().tm_yday

        # Solar declination (approximate)
        declination = 23.45 * math.sin(math.radians((360 / 365) * (day_of_year - 81)))

        # Hour angle at sunrise/sunset
        lat_rad = math.radians(lat)
        decl_rad = math.radians(declination)
        cos_hour_angle = math.tan(lat_rad) * math.tan(decl_rad)

        # Clamp to handle polar regions (not relevant for India, but safe)
        cos_hour_angle = max(-1, min(1, cos_hour_angle))
        hour_angle = math.degrees(math.acos(cos_hour_angle))

        # Sunrise/sunset in UTC hours (approximate — ignores equation of time)
        sunrise_hour_utc = 12 - hour_angle / 15
        sunset_hour_utc = 12 + hour_angle / 15

        # Convert to datetime in IST (UTC+5:30)
        sunrise_ist = sunrise_hour_utc + 5.5
        sunset_ist = sunset_hour_utc + 5.5

        sunrise = datetime.combine(
            target_date, datetime.min.time(), tzinfo=UTC
        ) + timedelta(hours=sunrise_ist)
        sunset = datetime.combine(
            target_date, datetime.min.time(), tzinfo=UTC
        ) + timedelta(hours=sunset_ist)

        return sunrise, sunset


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------


_imd_client: IMDClient | None = None


def get_imd_client() -> IMDClient:
    """Get the singleton IMD client instance."""
    global _imd_client
    if _imd_client is None:
        _imd_client = IMDClient()
    return _imd_client
