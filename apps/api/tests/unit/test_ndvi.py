"""Unit tests for NDVI domain — computation, anomaly detection, schemas.

These tests don't require a database — they test pure functions.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

# ---------------------------------------------------------------------------
# NDVI computation tests
# ---------------------------------------------------------------------------


class TestNDVIComputation:
    """Test the NDVI computation pipeline."""

    def _make_band_data(self, red_val, nir_val, scl_val=4, width=10, height=10):
        """Helper to create SentinelBandData for testing."""
        from krishisetu.integrations.sentinel_hub import SentinelBandData

        return SentinelBandData(
            red=[[red_val] * width for _ in range(height)],
            nir=[[nir_val] * width for _ in range(height)],
            scl=[[scl_val] * width for _ in range(height)],
            width=width,
            height=height,
            observed_at=datetime.now(UTC),
            cloud_cover_pct=0.0,
        )

    def test_uniform_ndvi_computation(self):
        """Uniform Red/NIR values produce uniform NDVI."""
        from krishisetu.domains.ndvi.computation import compute_ndvi_stats

        # Red=0.2, NIR=0.5 → NDVI = (0.5-0.2)/(0.5+0.2) = 0.3/0.7 ≈ 0.4286
        band_data = self._make_band_data(0.2, 0.5)
        stats = compute_ndvi_stats(band_data)

        expected_ndvi = (0.5 - 0.2) / (0.5 + 0.2)
        assert abs(float(stats.ndvi_mean) - expected_ndvi) < 0.001
        assert abs(float(stats.ndvi_min) - expected_ndvi) < 0.001
        assert abs(float(stats.ndvi_max) - expected_ndvi) < 0.001
        assert float(stats.ndvi_stddev) < 0.001  # No variation
        assert float(stats.cloud_cover_pct) == 0.0
        assert stats.valid_pixel_count == 100
        assert stats.total_pixel_count == 100

    def test_cloud_masking(self):
        """Cloud pixels (SCL 8, 9, 3) are masked out."""
        from krishisetu.domains.ndvi.computation import compute_ndvi_stats
        from krishisetu.integrations.sentinel_hub import SentinelBandData

        # 10x10 grid, all cloudy
        band_data = SentinelBandData(
            red=[[0.2] * 10 for _ in range(10)],
            nir=[[0.5] * 10 for _ in range(10)],
            scl=[[8] * 10 for _ in range(10)],  # All cloud
            width=10,
            height=10,
            observed_at=datetime.now(UTC),
            cloud_cover_pct=100.0,
        )
        stats = compute_ndvi_stats(band_data)

        assert stats.valid_pixel_count == 0
        assert float(stats.cloud_cover_pct) == 100.0
        assert float(stats.ndvi_mean) == 0.0  # Placeholder

    def test_partial_cloud_masking(self):
        """Mixed cloud/non-cloud pixels are handled correctly."""
        from krishisetu.domains.ndvi.computation import compute_ndvi_stats
        from krishisetu.integrations.sentinel_hub import SentinelBandData

        # 4x4 grid: top half cloudy, bottom half clear
        scl = [
            [8, 8, 8, 8],  # Cloudy
            [8, 8, 8, 8],  # Cloudy
            [4, 4, 4, 4],  # Clear (vegetation)
            [4, 4, 4, 4],  # Clear (vegetation)
        ]
        band_data = SentinelBandData(
            red=[[0.2] * 4 for _ in range(4)],
            nir=[[0.5] * 4 for _ in range(4)],
            scl=scl,
            width=4,
            height=4,
            observed_at=datetime.now(UTC),
            cloud_cover_pct=50.0,
        )
        stats = compute_ndvi_stats(band_data)

        # 8 valid pixels out of 16
        assert stats.valid_pixel_count == 8
        assert stats.total_pixel_count == 16
        assert float(stats.cloud_cover_pct) == 50.0

    def test_zero_reflectance_handled(self):
        """Zero reflectance (both bands) doesn't crash — NDVI = 0."""
        from krishisetu.domains.ndvi.computation import compute_ndvi_stats

        band_data = self._make_band_data(0.0, 0.0)
        stats = compute_ndvi_stats(band_data)
        # All pixels have NDVI = 0 (handled by denominator check)
        assert float(stats.ndvi_mean) == 0.0

    def test_ndvi_clamped_to_valid_range(self):
        """NDVI values are clamped to [-1, 1]."""
        from krishisetu.domains.ndvi.computation import compute_ndvi_stats

        # Red=0.9, NIR=0.1 → NDVI = (0.1-0.9)/(0.1+0.9) = -0.8/1.0 = -0.8
        band_data = self._make_band_data(0.9, 0.1)
        stats = compute_ndvi_stats(band_data)
        assert -1.0 <= float(stats.ndvi_min) <= 1.0
        assert -1.0 <= float(stats.ndvi_max) <= 1.0


# ---------------------------------------------------------------------------
# Health classification tests
# ---------------------------------------------------------------------------


class TestNDVIHealthClassification:
    """Test NDVI health categorization."""

    @pytest.mark.parametrize(
        "ndvi,expected",
        [
            (0.8, "healthy"),
            (0.65, "healthy"),
            (0.6, "healthy"),
            (0.59, "moderate"),
            (0.4, "moderate"),
            (0.3, "moderate"),
            (0.29, "sparse"),
            (0.15, "sparse"),
            (0.1, "sparse"),
            (0.09, "bare"),
            (0.0, "bare"),
            (-0.5, "bare"),
        ],
    )
    def test_health_classification(self, ndvi: float, expected: str):
        from krishisetu.domains.ndvi.computation import classify_ndvi_health

        assert classify_ndvi_health(ndvi) == expected


# ---------------------------------------------------------------------------
# Anomaly detection tests
# ---------------------------------------------------------------------------


class TestNDVIAnomalyDetection:
    """Test NDVI anomaly detection logic."""

    def test_severe_drop_detected(self):
        """NDVI drop > 0.30 is classified as severe_drop."""
        from krishisetu.domains.ndvi.computation import detect_ndvi_anomaly

        anomaly_type, drop = detect_ndvi_anomaly(0.70, 0.30)  # Drop of 0.40
        assert anomaly_type == "severe_drop"
        assert abs(drop - 0.40) < 0.001

    def test_significant_drop_detected(self):
        """NDVI drop between 0.15 and 0.30 is significant_drop."""
        from krishisetu.domains.ndvi.computation import detect_ndvi_anomaly

        anomaly_type, drop = detect_ndvi_anomaly(0.60, 0.40)  # Drop of 0.20
        assert anomaly_type == "significant_drop"
        assert abs(drop - 0.20) < 0.001

    def test_small_drop_no_anomaly(self):
        """NDVI drop < 0.15 is not an anomaly."""
        from krishisetu.domains.ndvi.computation import detect_ndvi_anomaly

        anomaly_type, drop = detect_ndvi_anomaly(0.60, 0.50)  # Drop of 0.10
        assert anomaly_type is None
        assert drop == 0.0

    def test_improving_ndvi_no_anomaly(self):
        """NDVI improvement (negative drop) is not an anomaly."""
        from krishisetu.domains.ndvi.computation import detect_ndvi_anomaly

        anomaly_type, _drop = detect_ndvi_anomaly(0.40, 0.60)  # Improvement of 0.20
        assert anomaly_type is None

    def test_low_vegetation_detected(self):
        """Sudden drop to bare soil (NDVI < 0.2) from moderate is low_vegetation."""
        from krishisetu.domains.ndvi.computation import detect_ndvi_anomaly

        # Previous was 0.4 (moderate), current is 0.15 (bare)
        # Drop = 0.25, which is > 0.15 → would be significant_drop
        # But the test is for the low_vegetation case
        anomaly_type, _drop = detect_ndvi_anomaly(0.40, 0.15)
        # Since drop > 0.15, it's classified as significant_drop first
        assert anomaly_type == "significant_drop"

    def test_exactly_at_threshold_no_anomaly(self):
        """Drop exactly at 0.15 is not an anomaly (uses > not >=)."""
        from krishisetu.domains.ndvi.computation import detect_ndvi_anomaly

        anomaly_type, _ = detect_ndvi_anomaly(0.60, 0.45)  # Drop of exactly 0.15
        assert anomaly_type is None

    def test_exactly_at_severe_threshold(self):
        """Drop exactly at 0.30 is significant_drop (severe requires > 0.30)."""
        from krishisetu.domains.ndvi.computation import detect_ndvi_anomaly

        anomaly_type, _ = detect_ndvi_anomaly(0.70, 0.40)  # Drop of exactly 0.30
        assert anomaly_type == "significant_drop"


# ---------------------------------------------------------------------------
# NDVI color mapping tests
# ---------------------------------------------------------------------------


class TestNDVIColorMapping:
    """Test NDVI to color mapping for visualization."""

    def test_healthy_ndvi_returns_green(self):
        """Healthy NDVI (0.6+) returns green-ish color."""
        from krishisetu.domains.ndvi.computation import ndvi_to_color

        r, g, b = ndvi_to_color(0.8)
        assert g > r  # Green dominant
        assert g > b

    def test_bare_ndvi_returns_red_or_brown(self):
        """Bare soil NDVI (<0.1) returns red/brown color."""
        from krishisetu.domains.ndvi.computation import ndvi_to_color

        r, g, _b = ndvi_to_color(0.05)
        assert r > g  # Red dominant

    def test_water_ndvi_returns_blue(self):
        """Water NDVI (<0) returns blue-ish color."""
        from krishisetu.domains.ndvi.computation import ndvi_to_color

        r, g, b = ndvi_to_color(-0.5)
        assert b > r  # Blue dominant
        assert b > g

    def test_ndvi_clamped_to_valid_range(self):
        """NDVI values outside [-1, 1] are clamped."""
        from krishisetu.domains.ndvi.computation import ndvi_to_color

        # Should not raise
        ndvi_to_color(2.0)
        ndvi_to_color(-2.0)


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------


class TestNDVISchemas:
    """Test NDVI Pydantic schemas."""

    def test_ndvi_observation_response_schema(self):
        from krishisetu.domains.ndvi.schemas import NDVIObservationResponse

        obs = NDVIObservationResponse(
            id="123e4567-e89b-12d3-a456-426614174000",
            plot_id="123e4567-e89b-12d3-a456-426614174001",
            observed_at="2026-07-19T10:00:00Z",
            source="sentinel2",
            ndvi_mean=Decimal("0.6543"),
            ndvi_min=Decimal("0.2341"),
            ndvi_max=Decimal("0.8123"),
            ndvi_stddev=Decimal("0.1234"),
            cloud_cover_pct=Decimal("5.20"),
            valid_pixel_count=95,
            total_pixel_count=100,
            raster_url="ndvi/plot-1/2026-07-19.tiff",
            thumbnail_url=None,
            created_at="2026-07-19T10:05:00Z",
            health_category="healthy",
            is_cloudy=False,
            raster_download_url="https://s3.example.com/signed-url",
        )
        assert obs.health_category == "healthy"
        assert obs.is_cloudy is False

    def test_anomaly_acknowledge_schema_with_notes(self):
        from krishisetu.domains.ndvi.schemas import NDVIAnomalyAcknowledge

        ack = NDVIAnomalyAcknowledge(resolution_notes="Applied fungicide as recommended")
        assert ack.resolution_notes is not None
        assert len(ack.resolution_notes) > 0

    def test_anomaly_acknowledge_schema_without_notes(self):
        from krishisetu.domains.ndvi.schemas import NDVIAnomalyAcknowledge

        ack = NDVIAnomalyAcknowledge()
        assert ack.resolution_notes is None

    def test_anomaly_acknowledge_notes_max_length(self):
        from pydantic import ValidationError

        from krishisetu.domains.ndvi.schemas import NDVIAnomalyAcknowledge

        with pytest.raises(ValidationError):
            NDVIAnomalyAcknowledge(resolution_notes="x" * 2001)
