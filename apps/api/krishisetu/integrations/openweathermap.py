"""OpenWeatherMap (OWM) API client — fallback weather source.

Used when IMD API is unavailable or for cross-validation. OWM provides:
- Current weather (global coverage)
- 5-day / 3-hour forecast
- Historical weather (last 5 days free, more with paid plan)

API key required: https://openweathermap.org/api

OWM is a paid service for high-volume use. We use it as a fallback only
when IMD is unavailable, and cache aggressively to minimize API calls.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

import httpx

from krishisetu.core.config import settings
from krishisetu.core.logging import get_logger
from krishisetu.integrations.imd import CurrentWeather, DailyForecast

logger = get_logger(__name__)


class OpenWeatherMapClient:
    """OpenWeatherMap API client.

    Requires OPENWEATHERMAP_API_KEY in settings. In development without
    a key, all methods return None (caller should fall back to IMD or
    synthetic data).
    """

    BASE_URL = "https://api.openweathermap.org/data/2.5"
    CURRENT_ENDPOINT = "/weather"
    FORECAST_ENDPOINT = "/forecast"

    def __init__(self) -> None:
        self.api_key = settings().OPENWEATHERMAP_API_KEY
        self.base_url = self.BASE_URL
        self.timeout = 10.0

    @property
    def is_available(self) -> bool:
        """Whether this client can be used (API key configured)."""
        return self.api_key is not None

    async def get_current_weather(
        self, lat: float, lon: float
    ) -> CurrentWeather | None:
        """Fetch current weather by coordinates.

        Returns None if API key not configured or API call fails.
        """
        if not self.is_available:
            return None

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}{self.CURRENT_ENDPOINT}",
                    params={
                        "lat": lat,
                        "lon": lon,
                        "appid": self.api_key.get_secret_value() if self.api_key else "",
                        "units": "metric",  # Celsius, m/s, mm
                    },
                )
            response.raise_for_status()
            data = response.json()
            return self._parse_current(data)
        except Exception as e:
            logger.warning("owm.current_failed", lat=lat, lon=lon, error=str(e))
            return None

    async def get_forecast(
        self, lat: float, lon: float, days: int = 5
    ) -> list[DailyForecast]:
        """Fetch 5-day forecast by coordinates.

        OWM free tier provides 5-day/3-hour forecast. We aggregate to daily.
        """
        if not self.is_available:
            return []

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}{self.FORECAST_ENDPOINT}",
                    params={
                        "lat": lat,
                        "lon": lon,
                        "appid": self.api_key.get_secret_value() if self.api_key else "",
                        "units": "metric",
                        "cnt": min(days * 8, 40),  # 8 entries per day (3-hour intervals)
                    },
                )
            response.raise_for_status()
            data = response.json()
            return self._aggregate_forecast(data, days)
        except Exception as e:
            logger.warning("owm.forecast_failed", lat=lat, lon=lon, error=str(e))
            return []

    def _parse_current(self, data: dict[str, Any]) -> CurrentWeather:
        """Parse OWM current weather response."""
        main = data.get("main", {})
        wind = data.get("wind", {})
        weather_list = data.get("weather", [{}])
        weather = weather_list[0] if weather_list else {}
        sys_data = data.get("sys", {})
        clouds = data.get("clouds", {})
        rain = data.get("rain", {})

        return CurrentWeather(
            temperature_c=Decimal(str(round(main.get("temp", 0), 1))),
            feels_like_c=Decimal(str(round(main.get("feels_like", main.get("temp", 0)), 1))),
            temp_min_c=Decimal(str(round(main.get("temp_min", 0), 1))),
            temp_max_c=Decimal(str(round(main.get("temp_max", 0), 1))),
            precipitation_mm=Decimal(str(rain.get("1h", 0) if rain else 0)),
            humidity_pct=Decimal(str(main.get("humidity", 0))),
            wind_speed_kmph=Decimal(str(round(wind.get("speed", 0) * 3.6, 1))),  # m/s to km/h
            wind_direction_deg=Decimal(str(wind.get("deg", 0))),
            pressure_hpa=Decimal(str(main.get("pressure", 1013))),
            cloud_cover_pct=Decimal(str(clouds.get("all", 0))),
            weather_main=weather.get("main", "Unknown"),
            weather_description=weather.get("description", ""),
            weather_icon=weather.get("icon", ""),
            observed_at=datetime.fromtimestamp(
                data.get("dt", datetime.now(timezone.utc).timestamp()),
                tz=timezone.utc,
            ),
            sunrise_at=datetime.fromtimestamp(
                sys_data.get("sunrise"), tz=timezone.utc
            ) if sys_data.get("sunrise") else None,
            sunset_at=datetime.fromtimestamp(
                sys_data.get("sunset"), tz=timezone.utc
            ) if sys_data.get("sunset") else None,
            raw_data={"source": "owm", **data},
        )

    def _aggregate_forecast(
        self, data: dict[str, Any], days: int
    ) -> list[DailyForecast]:
        """Aggregate OWM 3-hour forecast entries into daily summaries."""
        entries = data.get("list", [])
        daily: dict[date, list[dict]] = {}

        for entry in entries:
            dt = datetime.fromtimestamp(entry["dt"], tz=timezone.utc)
            day = dt.date()
            daily.setdefault(day, []).append(entry)

        forecasts: list[DailyForecast] = []
        for day, day_entries in sorted(daily.items())[:days]:
            temps = [e["main"]["temp"] for e in day_entries]
            humidity_min = min(e["main"]["humidity"] for e in day_entries)
            humidity_max = max(e["main"]["humidity"] for e in day_entries)
            precip = sum(e.get("rain", {}).get("3h", 0) for e in day_entries if e.get("rain"))

            # Pick the most common weather_main for the day
            weather_mains = [e["weather"][0]["main"] for e in day_entries if e.get("weather")]
            weather_main = max(set(weather_mains), key=weather_mains.count) if weather_mains else "Unknown"
            weather_desc = next(
                (e["weather"][0]["description"] for e in day_entries
                 if e.get("weather") and e["weather"][0]["main"] == weather_main),
                "",
            )

            forecasts.append(
                DailyForecast(
                    forecast_date=day,
                    temp_min_c=Decimal(str(round(min(temps), 1))),
                    temp_max_c=Decimal(str(round(max(temps), 1))),
                    precipitation_mm=Decimal(str(round(precip, 1))),
                    precipitation_probability=Decimal("0"),  # OWM doesn't provide this directly
                    humidity_min_pct=Decimal(str(humidity_min)),
                    humidity_max_pct=Decimal(str(humidity_max)),
                    wind_speed_kmph=Decimal(str(round(
                        sum(e["wind"]["speed"] for e in day_entries) / len(day_entries) * 3.6, 1
                    ))),
                    wind_direction_deg=Decimal(str(round(
                        sum(e["wind"]["deg"] for e in day_entries) / len(day_entries), 0
                    ))),
                    weather_main=weather_main,
                    weather_description=weather_desc,
                    weather_icon="01d",  # Placeholder
                    raw_data={"source": "owm"},
                )
            )

        return forecasts


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------


_owm_client: OpenWeatherMapClient | None = None


def get_owm_client() -> OpenWeatherMapClient:
    """Get the singleton OWM client instance."""
    global _owm_client
    if _owm_client is None:
        _owm_client = OpenWeatherMapClient()
    return _owm_client
