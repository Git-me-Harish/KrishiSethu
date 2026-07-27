"""Unit tests for soil_weather domain.

Covers schemas, ISRIC parsing, IMD synthetic data, and fertilizer recommendations.

These tests don't require a database — they test pure functions.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


class TestSoilTestCreateSchema:
    """Test the SoilTestCreate schema."""

    def test_valid_minimal_soil_test(self):
        from krishisetu.domains.soil_weather.schemas import SoilTestCreate

        test = SoilTestCreate(test_date="2026-07-19")
        assert test.test_date == date(2026, 7, 19)
        assert test.nitrogen_n is None

    def test_valid_full_soil_test(self):
        from krishisetu.domains.soil_weather.schemas import SoilTestCreate

        test = SoilTestCreate(
            test_date="2026-07-19",
            lab_name="District Soil Lab",
            nitrogen_n=Decimal("150.5"),
            phosphorus_p=Decimal("12.5"),
            potassium_k=Decimal("110.0"),
            ph=Decimal("6.5"),
            electrical_conductivity=Decimal("0.8"),
            organic_carbon=Decimal("0.65"),
        )
        assert test.nitrogen_n == Decimal("150.5")
        assert test.ph == Decimal("6.5")

    def test_ph_out_of_range_rejected(self):
        from krishisetu.domains.soil_weather.schemas import SoilTestCreate

        with pytest.raises(ValidationError):
            SoilTestCreate(test_date="2026-07-19", ph=Decimal("15"))

    def test_negative_nutrient_rejected(self):
        from krishisetu.domains.soil_weather.schemas import SoilTestCreate

        with pytest.raises(ValidationError):
            SoilTestCreate(test_date="2026-07-19", nitrogen_n=Decimal("-10"))

    def test_texture_partial_provision_rejected(self):
        """If any texture % is provided, all three must be."""
        from krishisetu.domains.soil_weather.schemas import SoilTestCreate

        with pytest.raises(ValidationError, match="all three"):
            SoilTestCreate(
                test_date="2026-07-19",
                clay_pct=Decimal("30"),
                # Missing sand and silt
            )

    def test_texture_sum_must_be_100(self):
        from krishisetu.domains.soil_weather.schemas import SoilTestCreate

        with pytest.raises(ValidationError, match="sum to ~100"):
            SoilTestCreate(
                test_date="2026-07-19",
                clay_pct=Decimal("30"),
                sand_pct=Decimal("30"),
                silt_pct=Decimal("10"),  # Sum = 70
            )

    def test_texture_sum_100_accepted(self):
        from krishisetu.domains.soil_weather.schemas import SoilTestCreate

        test = SoilTestCreate(
            test_date="2026-07-19",
            clay_pct=Decimal("30"),
            sand_pct=Decimal("40"),
            silt_pct=Decimal("30"),  # Sum = 100
        )
        assert test.clay_pct == Decimal("30")


# ---------------------------------------------------------------------------
# IMD client synthetic data tests
# ---------------------------------------------------------------------------


class TestIMDSyntheticData:
    """Test the IMD client's synthetic data generation (dev mode).

    The synthetic data should be:
    - Deterministic (same input → same output within the same hour)
    - Realistic (within reasonable ranges for Indian climate)
    - Vary by district (different districts get different values)
    """

    def test_synthetic_current_returns_valid_data(self):
        from krishisetu.integrations.imd import IMDClient

        client = IMDClient()
        assert not client.is_live  # In dev mode

        weather = client._generate_current_synthetic(
            "Pune", "Maharashtra", 18.52, 73.85
        )

        # Temperature should be in reasonable range (5-50°C)
        assert 5 <= float(weather.temperature_c) <= 50
        # Humidity should be 0-100%
        assert 0 <= float(weather.humidity_pct) <= 100
        # Wind speed should be positive
        assert float(weather.wind_speed_kmph) >= 0
        # Precipitation should be non-negative
        assert float(weather.precipitation_mm) >= 0
        # Pressure should be in hPa range
        assert 950 <= float(weather.pressure_hpa) <= 1050

    def test_synthetic_current_is_deterministic_within_hour(self):
        """Two calls within the same hour return the same temperature."""
        from krishisetu.integrations.imd import IMDClient

        client = IMDClient()
        w1 = client._generate_current_synthetic("Pune", "Maharashtra", 18.52, 73.85)
        w2 = client._generate_current_synthetic("Pune", "Maharashtra", 18.52, 73.85)
        assert w1.temperature_c == w2.temperature_c

    def test_synthetic_current_differs_by_district(self):
        """Different districts get different weather."""
        from krishisetu.integrations.imd import IMDClient

        client = IMDClient()
        pune = client._generate_current_synthetic("Pune", "Maharashtra", 18.52, 73.85)
        delhi = client._generate_current_synthetic("Delhi", "Delhi", 28.61, 77.21)
        assert pune.temperature_c != delhi.temperature_c

    def test_synthetic_forecast_returns_7_days(self):
        from krishisetu.integrations.imd import IMDClient

        client = IMDClient()
        forecasts = client._generate_forecast_synthetic(
            "Pune", "Maharashtra", 18.52, 73.85, days=7
        )
        assert len(forecasts) == 7

        # Dates should be sequential, starting today
        today = date.today()
        for i, fc in enumerate(forecasts):
            assert fc.forecast_date == today + __import__("datetime").timedelta(days=i)

    def test_synthetic_forecast_agromet_advisory_present(self):
        """Each forecast day should have an agromet advisory."""
        from krishisetu.integrations.imd import IMDClient

        client = IMDClient()
        forecasts = client._generate_forecast_synthetic(
            "Pune", "Maharashtra", 18.52, 73.85, days=3
        )
        for fc in forecasts:
            assert fc.agromet_advisory is not None
            assert len(fc.agromet_advisory) > 10

    def test_northern_district_cooler_in_winter(self):
        """In January, Delhi (28°N) should be cooler than Chennai (13°N)."""
        from unittest.mock import patch

        from krishisetu.integrations.imd import IMDClient

        client = IMDClient()

        # Patch datetime to make it "January"
        class FakeDatetime:
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 1, 15, 12, 0, 0, tzinfo=tz or UTC)

        with patch("krishisetu.integrations.imd.datetime", FakeDatetime):
            delhi = client._generate_current_synthetic("Delhi", "Delhi", 28.61, 77.21)
            chennai = client._generate_current_synthetic("Chennai", "Tamil Nadu", 13.08, 80.27)

        # Delhi (higher latitude, more northern) should be cooler than Chennai
        # in January (winter)
        assert float(delhi.temperature_c) < float(chennai.temperature_c)


# ---------------------------------------------------------------------------
# ISRIC parsing tests
# ---------------------------------------------------------------------------


class TestISRICParsing:
    """Test the ISRIC SoilGrids API response parsing."""

    def test_parse_full_response(self):
        from krishisetu.integrations.isric import ISRICClient

        # Sample ISRIC API response
        sample_response = {
            "properties": {
                "layers": [
                    {
                        "name": "phh2o",
                        "depths": [{"label": "5-15cm", "values": {"mean": 62}}],
                    },
                    {
                        "name": "soc",
                        "depths": [{"label": "5-15cm", "values": {"mean": 15}}],
                    },
                    {
                        "name": "clay",
                        "depths": [{"label": "5-15cm", "values": {"mean": 350}}],
                    },
                    {
                        "name": "sand",
                        "depths": [{"label": "5-15cm", "values": {"mean": 400}}],
                    },
                    {
                        "name": "silt",
                        "depths": [{"label": "5-15cm", "values": {"mean": 250}}],
                    },
                ]
            }
        }

        client = ISRICClient()
        result = client._parse_response(sample_response)

        # phh2o=62 → pH 6.2
        assert result.ph == Decimal("6.20")
        # soc=15 g/kg → 1.5%
        assert result.organic_carbon == Decimal("1.50")
        # clay=350 g/kg → 35%
        assert result.clay_pct == Decimal("35.00")
        assert result.sand_pct == Decimal("40.00")
        assert result.silt_pct == Decimal("25.00")
        # Soil type should be classified
        assert result.soil_type is not None

    def test_classify_clay_soil(self):
        """High clay content classifies as Clay."""
        from krishisetu.integrations.isric import ISRICClient

        client = ISRICClient()
        soil_type = client._classify_soil_texture(45, 30, 25)  # 45% clay
        assert soil_type == "Clay"

    def test_classify_sandy_soil(self):
        """High sand content classifies as Sand."""
        from krishisetu.integrations.isric import ISRICClient

        client = ISRICClient()
        soil_type = client._classify_soil_texture(5, 88, 7)  # 88% sand
        assert soil_type == "Sand"

    def test_classify_loam_soil(self):
        """Balanced texture classifies as Loam."""
        from krishisetu.integrations.isric import ISRICClient

        client = ISRICClient()
        soil_type = client._classify_soil_texture(20, 40, 40)  # Balanced
        assert soil_type == "Loam"

    def test_classify_silt_loam(self):
        """High silt classifies as Silt Loam."""
        from krishisetu.integrations.isric import ISRICClient

        client = ISRICClient()
        soil_type = client._classify_soil_texture(15, 25, 60)  # 60% silt
        assert soil_type == "Silt Loam"


# ---------------------------------------------------------------------------
# Fertilizer recommendation tests
# ---------------------------------------------------------------------------


class TestFertilizerRecommendations:
    """Test the fertilizer recommendation engine."""

    def test_low_npk_generates_high_dose_recommendation(self):
        from krishisetu.domains.soil_weather.services import _generate_fertilizer_recommendation

        rec = _generate_fertilizer_recommendation(
            nitrogen=Decimal("100"),
            phosphorus_p=Decimal("8"),
            potassium_k=Decimal("90"),
            ph=Decimal("6.5"),
            organic_carbon=Decimal("0.6"),
        )
        assert rec is not None
        assert "80-100 kg N/ha" in rec  # Low N
        assert "60-80 kg P2O5/ha" in rec  # Low P
        assert "40-60 kg K2O/ha" in rec  # Low K

    def test_high_npk_generates_low_dose_recommendation(self):
        from krishisetu.domains.soil_weather.services import _generate_fertilizer_recommendation

        rec = _generate_fertilizer_recommendation(
            nitrogen=Decimal("350"),
            phosphorus_p=Decimal("30"),
            potassium_k=Decimal("300"),
            ph=Decimal("6.5"),
            organic_carbon=Decimal("0.8"),
        )
        assert rec is not None
        assert "20-30 kg N/ha" in rec  # High N
        assert "20 kg P2O5/ha" in rec  # High P
        assert "No K application" in rec  # High K

    def test_medium_npk_generates_medium_dose(self):
        from krishisetu.domains.soil_weather.services import _generate_fertilizer_recommendation

        rec = _generate_fertilizer_recommendation(
            nitrogen=Decimal("200"),
            phosphorus_p=Decimal("18"),
            potassium_k=Decimal("180"),
            ph=Decimal("6.8"),
            organic_carbon=Decimal("0.7"),
        )
        assert rec is not None
        assert "40-60 kg N/ha" in rec  # Medium N
        assert "30-40 kg P2O5/ha" in rec  # Medium P
        assert "20-30 kg K2O/ha" in rec  # Medium K

    def test_no_values_returns_none(self):
        from krishisetu.domains.soil_weather.services import _generate_fertilizer_recommendation

        rec = _generate_fertilizer_recommendation(
            nitrogen=None,
            phosphorus_p=None,
            potassium_k=None,
            ph=None,
            organic_carbon=None,
        )
        assert rec is None


class TestAmendmentRecommendations:
    """Test the soil amendment recommendation engine."""

    def test_acidic_soil_recommends_lime(self):
        from krishisetu.domains.soil_weather.services import _generate_amendment_recommendation

        rec = _generate_amendment_recommendation(
            ph=Decimal("5.0"),
            ec=None,
            organic_carbon=None,
        )
        assert rec is not None
        assert "acidic" in rec.lower()
        assert "lime" in rec.lower()

    def test_alkaline_soil_recommends_gypsum(self):
        from krishisetu.domains.soil_weather.services import _generate_amendment_recommendation

        rec = _generate_amendment_recommendation(
            ph=Decimal("9.0"),
            ec=None,
            organic_carbon=None,
        )
        assert rec is not None
        assert "alkaline" in rec.lower()
        assert "gypsum" in rec.lower()

    def test_saline_soil_recommends_drainage(self):
        from krishisetu.domains.soil_weather.services import _generate_amendment_recommendation

        rec = _generate_amendment_recommendation(
            ph=Decimal("7.5"),
            ec=Decimal("3.0"),  # High EC
            organic_carbon=None,
        )
        assert rec is not None
        assert "saline" in rec.lower()
        assert "drainage" in rec.lower()

    def test_low_organic_carbon_recommends_manure(self):
        from krishisetu.domains.soil_weather.services import _generate_amendment_recommendation

        rec = _generate_amendment_recommendation(
            ph=Decimal("6.5"),
            ec=None,
            organic_carbon=Decimal("0.3"),
        )
        assert rec is not None
        assert "organic carbon" in rec.lower()
        assert "manure" in rec.lower() or "compost" in rec.lower()

    def test_optimal_soil_returns_none(self):
        from krishisetu.domains.soil_weather.services import _generate_amendment_recommendation

        rec = _generate_amendment_recommendation(
            ph=Decimal("6.8"),
            ec=Decimal("0.5"),
            organic_carbon=Decimal("0.8"),
        )
        assert rec is None


# ---------------------------------------------------------------------------
# Soil texture classification tests
# ---------------------------------------------------------------------------


class TestSoilTextureClassification:
    """Test the USDA soil texture classification."""

    def test_clay_classification(self):
        from krishisetu.domains.soil_weather.services import _classify_texture

        assert _classify_texture(45, 30, 25) == "Clay"

    def test_sand_classification(self):
        from krishisetu.domains.soil_weather.services import _classify_texture

        assert _classify_texture(5, 90, 5) == "Sand"

    def test_loam_classification(self):
        from krishisetu.domains.soil_weather.services import _classify_texture

        # Loam: ~40% sand, ~40% silt, ~20% clay
        assert _classify_texture(20, 40, 40) == "Loam"

    def test_silt_loam_classification(self):
        from krishisetu.domains.soil_weather.services import _classify_texture

        # Silt Loam: high silt, moderate clay
        assert _classify_texture(15, 25, 60) == "Silt Loam"

    def test_sandy_loam_classification(self):
        from krishisetu.domains.soil_weather.services import _classify_texture

        # Sandy Loam: high sand, low clay
        assert _classify_texture(10, 65, 25) == "Sandy Loam"


# ---------------------------------------------------------------------------
# Alert threshold tests
# ---------------------------------------------------------------------------


class TestWeatherAlertThresholds:
    """Test the weather alert threshold logic."""

    def test_heat_wave_severity_critical(self):
        from decimal import Decimal

        from krishisetu.domains.soil_weather.models import WeatherAlertSeverity, WeatherAlertType
        from krishisetu.domains.soil_weather.services import (
            ALERT_THRESHOLDS,
            _get_severity_by_threshold,
        )

        thresholds = ALERT_THRESHOLDS[WeatherAlertType.HEAT_WAVE]["severity_by_temp"]
        severity = _get_severity_by_threshold(Decimal("46"), thresholds)
        assert severity == WeatherAlertSeverity.CRITICAL

    def test_heat_wave_severity_severe(self):
        from decimal import Decimal

        from krishisetu.domains.soil_weather.models import WeatherAlertSeverity, WeatherAlertType
        from krishisetu.domains.soil_weather.services import (
            ALERT_THRESHOLDS,
            _get_severity_by_threshold,
        )

        thresholds = ALERT_THRESHOLDS[WeatherAlertType.HEAT_WAVE]["severity_by_temp"]
        severity = _get_severity_by_threshold(Decimal("44"), thresholds)
        assert severity == WeatherAlertSeverity.SEVERE

    def test_heat_wave_severity_warning(self):
        from decimal import Decimal

        from krishisetu.domains.soil_weather.models import WeatherAlertSeverity, WeatherAlertType
        from krishisetu.domains.soil_weather.services import (
            ALERT_THRESHOLDS,
            _get_severity_by_threshold,
        )

        thresholds = ALERT_THRESHOLDS[WeatherAlertType.HEAT_WAVE]["severity_by_temp"]
        severity = _get_severity_by_threshold(Decimal("41"), thresholds)
        assert severity == WeatherAlertSeverity.WARNING

    def test_frost_severity_critical_below_zero(self):
        from decimal import Decimal

        from krishisetu.domains.soil_weather.models import WeatherAlertSeverity, WeatherAlertType
        from krishisetu.domains.soil_weather.services import (
            ALERT_THRESHOLDS,
            _get_severity_by_threshold,
        )

        thresholds = ALERT_THRESHOLDS[WeatherAlertType.FROST]["severity_by_temp"]
        # Frost is reverse — lower temp = higher severity
        severity = _get_severity_by_threshold(Decimal("-1"), thresholds, reverse=True)
        assert severity == WeatherAlertSeverity.CRITICAL

    def test_heavy_rain_severity_severe(self):
        from decimal import Decimal

        from krishisetu.domains.soil_weather.models import WeatherAlertSeverity, WeatherAlertType
        from krishisetu.domains.soil_weather.services import (
            ALERT_THRESHOLDS,
            _get_severity_by_threshold,
        )

        thresholds = ALERT_THRESHOLDS[WeatherAlertType.HEAVY_RAIN]["severity_by_mm"]
        severity = _get_severity_by_threshold(Decimal("70"), thresholds)
        assert severity == WeatherAlertSeverity.SEVERE


# ---------------------------------------------------------------------------
# District centroid tests
# ---------------------------------------------------------------------------


class TestDistrictCentroids:
    """Test district centroid lookup."""

    def test_known_district_returns_centroid(self):
        from krishisetu.domains.soil_weather.services import get_district_centroid

        lat, lon = get_district_centroid("Pune", "Maharashtra")
        assert 18.0 < lat < 19.0
        assert 73.0 < lon < 74.0

    def test_unknown_district_falls_back_to_state(self):
        from krishisetu.domains.soil_weather.services import get_district_centroid

        # Unknown district but known state
        lat, _lon = get_district_centroid("Unknown District", "Maharashtra")
        # Should return Maharashtra state centroid
        assert 18.0 < lat < 20.0

    def test_unknown_state_falls_back_to_india_center(self):
        from krishisetu.domains.soil_weather.services import get_district_centroid

        lat, lon = get_district_centroid("Unknown", "Unknown State")
        # Should return center of India
        assert 19.0 < lat < 21.0
        assert 78.0 < lon < 80.0
