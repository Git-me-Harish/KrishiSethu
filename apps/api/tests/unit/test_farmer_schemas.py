"""Unit tests for farmer domain — schemas, GeoJSON validation, repository helpers.

These tests don't require a database — they test pure functions and schema
validation.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from krishisetu.domains.farmer.schemas import (
    GeoJSONPolygon,
    PlotCreate,
    CropCycleCreate,
)
from krishisetu.domains.farmer.repository import (
    geojson_to_wkt,
    _wkt_to_geojson,
)


# ---------------------------------------------------------------------------
# GeoJSON validation
# ---------------------------------------------------------------------------


class TestGeoJSONPolygonValidation:
    """Test the GeoJSONPolygon Pydantic schema validation."""

    def test_valid_polygon_accepted(self):
        """A valid polygon with 4+ points and closed ring is accepted."""
        polygon = GeoJSONPolygon(
            type="Polygon",
            coordinates=[
                [[72.8, 19.1], [72.81, 19.1], [72.81, 19.11], [72.8, 19.11], [72.8, 19.1]]
            ],
        )
        assert polygon.type == "Polygon"
        assert len(polygon.coordinates) == 1
        assert len(polygon.coordinates[0]) == 5

    def test_unclosed_ring_rejected(self):
        """A ring that doesn't close (first != last) is rejected."""
        with pytest.raises(ValidationError, match="must be closed"):
            GeoJSONPolygon(
                type="Polygon",
                coordinates=[[[72.8, 19.1], [72.81, 19.1], [72.81, 19.11]]],
            )

    def test_too_few_points_rejected(self):
        """A ring with fewer than 4 points is rejected."""
        with pytest.raises(ValidationError, match="at least 4 positions"):
            GeoJSONPolygon(
                type="Polygon",
                coordinates=[[[72.8, 19.1], [72.8, 19.1]]],
            )

    def test_invalid_longitude_rejected(self):
        """Longitude outside [-180, 180] is rejected."""
        with pytest.raises(ValidationError, match="Longitude"):
            GeoJSONPolygon(
                type="Polygon",
                coordinates=[[[200, 19.1], [201, 19.1], [201, 19.11], [200, 19.11], [200, 19.1]]],
            )

    def test_invalid_latitude_rejected(self):
        """Latitude outside [-90, 90] is rejected."""
        with pytest.raises(ValidationError, match="Latitude"):
            GeoJSONPolygon(
                type="Polygon",
                coordinates=[[[72.8, 95], [72.81, 95], [72.81, 96], [72.8, 96], [72.8, 95]]],
            )

    def test_polygon_with_hole_accepted(self):
        """A polygon with an exterior ring and a hole is accepted."""
        polygon = GeoJSONPolygon(
            type="Polygon",
            coordinates=[
                # Exterior
                [[72.8, 19.1], [72.85, 19.1], [72.85, 19.15], [72.8, 19.15], [72.8, 19.1]],
                # Hole
                [[72.82, 19.12], [72.83, 19.12], [72.83, 19.13], [72.82, 19.13], [72.82, 19.12]],
            ],
        )
        assert len(polygon.coordinates) == 2

    def test_wrong_geometry_type_rejected(self):
        """A non-Polygon geometry type is rejected by the Literal type."""
        with pytest.raises(ValidationError):
            GeoJSONPolygon(
                type="Point",  # type: ignore[arg-type]
                coordinates=[[[72.8, 19.1], [72.81, 19.1], [72.81, 19.11], [72.8, 19.11], [72.8, 19.1]]],
            )


# ---------------------------------------------------------------------------
# PlotCreate schema validation
# ---------------------------------------------------------------------------


class TestPlotCreateSchema:
    """Test the PlotCreate Pydantic schema with business rules."""

    VALID_BOUNDARY = {
        "type": "Polygon",
        "coordinates": [
            [[72.8, 19.1], [72.81, 19.1], [72.81, 19.11], [72.8, 19.11], [72.8, 19.1]]
        ],
    }

    def test_valid_plot_create(self):
        """A valid plot creation request is accepted."""
        plot = PlotCreate(
            survey_number="142/3",
            village="Khanapur",
            district="Pune",
            state="Maharashtra",
            boundary=self.VALID_BOUNDARY,
        )
        assert plot.survey_number == "142/3"
        assert plot.ownership_type.value == "owned"

    def test_leased_plot_requires_lessor_name(self):
        """A leased plot must have lessor_name."""
        with pytest.raises(ValidationError, match="lessor_name is required"):
            PlotCreate(
                survey_number="142/3",
                village="Khanapur",
                district="Pune",
                state="Maharashtra",
                boundary=self.VALID_BOUNDARY,
                ownership_type="leased",
            )

    def test_leased_plot_requires_lease_dates(self):
        """A leased plot must have lease_start_date and lease_end_date."""
        with pytest.raises(ValidationError, match="lease_start_date"):
            PlotCreate(
                survey_number="142/3",
                village="Khanapur",
                district="Pune",
                state="Maharashtra",
                boundary=self.VALID_BOUNDARY,
                ownership_type="leased",
                lessor_name="Suresh Patil",
            )

    def test_lease_end_before_start_rejected(self):
        """Lease end date must be after start date."""
        with pytest.raises(ValidationError, match="lease_end_date must be after"):
            PlotCreate(
                survey_number="142/3",
                village="Khanapur",
                district="Pune",
                state="Maharashtra",
                boundary=self.VALID_BOUNDARY,
                ownership_type="leased",
                lessor_name="Suresh Patil",
                lease_start_date="2026-06-01",
                lease_end_date="2026-05-31",
            )

    def test_invalid_pincode_rejected(self):
        """Pincodes must be 6 digits starting with 1-9."""
        with pytest.raises(ValidationError):
            PlotCreate(
                survey_number="142/3",
                village="Khanapur",
                district="Pune",
                state="Maharashtra",
                pincode="012345",  # starts with 0
                boundary=self.VALID_BOUNDARY,
            )

    def test_empty_survey_number_rejected(self):
        """Survey number cannot be empty."""
        with pytest.raises(ValidationError):
            PlotCreate(
                survey_number="",
                village="Khanapur",
                district="Pune",
                state="Maharashtra",
                boundary=self.VALID_BOUNDARY,
            )


# ---------------------------------------------------------------------------
# CropCycleCreate schema validation
# ---------------------------------------------------------------------------


class TestCropCycleCreateSchema:
    """Test the CropCycleCreate schema."""

    def test_valid_crop_cycle(self):
        """A valid crop cycle is accepted."""
        from uuid import uuid4

        cycle = CropCycleCreate(
            crop_id=uuid4(),
            season="kharif",
            season_year=2026,
            area_ha=Decimal("1.5"),
        )
        assert cycle.season.value == "kharif"
        assert cycle.area_ha == Decimal("1.5")

    def test_invalid_season_rejected(self):
        """Invalid season is rejected."""
        from uuid import uuid4

        with pytest.raises(ValidationError):
            CropCycleCreate(
                crop_id=uuid4(),
                season="invalid",  # type: ignore[arg-type]
                season_year=2026,
                area_ha=Decimal("1.5"),
            )

    def test_year_out_of_range_rejected(self):
        """Years outside [2000, 2100] are rejected."""
        from uuid import uuid4

        with pytest.raises(ValidationError):
            CropCycleCreate(
                crop_id=uuid4(),
                season="kharif",
                season_year=1999,
                area_ha=Decimal("1.5"),
            )

    def test_zero_area_rejected(self):
        """Area must be positive."""
        from uuid import uuid4

        with pytest.raises(ValidationError):
            CropCycleCreate(
                crop_id=uuid4(),
                season="kharif",
                season_year=2026,
                area_ha=Decimal("0"),
            )

    def test_harvest_before_sowing_rejected(self):
        """Expected harvest date must be after sowing date."""
        from uuid import uuid4

        with pytest.raises(ValidationError, match="expected_harvest_date must be after"):
            CropCycleCreate(
                crop_id=uuid4(),
                season="kharif",
                season_year=2026,
                sowing_date="2026-07-15",
                expected_harvest_date="2026-07-14",
                area_ha=Decimal("1.5"),
            )


# ---------------------------------------------------------------------------
# GeoJSON <-> WKT conversion
# ---------------------------------------------------------------------------


class TestGeoJSONWKTConversion:
    """Test the GeoJSON <-> WKT conversion helpers."""

    def test_geojson_to_wkt_simple_polygon(self):
        """Convert a simple GeoJSON polygon to WKT."""
        geojson = {
            "type": "Polygon",
            "coordinates": [
                [[72.8, 19.1], [72.81, 19.1], [72.81, 19.11], [72.8, 19.11], [72.8, 19.1]]
            ],
        }
        wkt = geojson_to_wkt(geojson)
        assert wkt.startswith("SRID=4326;POLYGON(")
        assert "72.8 19.1" in wkt
        assert "72.81 19.11" in wkt

    def test_geojson_to_wkt_polygon_with_hole(self):
        """Convert a polygon with a hole to WKT."""
        geojson = {
            "type": "Polygon",
            "coordinates": [
                [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
                [[2, 2], [8, 2], [8, 8], [2, 8], [2, 2]],
            ],
        }
        wkt = geojson_to_wkt(geojson)
        # WKT for polygon with hole: POLYGON((exterior), (hole))
        assert wkt.count("(") >= 3  # outer + 2 rings
        assert wkt.count(")") >= 3

    def test_geojson_to_wkt_invalid_type_rejected(self):
        """Non-Polygon GeoJSON is rejected."""
        with pytest.raises(ValueError, match="Expected GeoJSON Polygon"):
            geojson_to_wkt({"type": "Point", "coordinates": [72.8, 19.1]})

    def test_wkt_to_geojson_roundtrip(self):
        """Convert WKT back to GeoJSON and verify structure."""
        original = {
            "type": "Polygon",
            "coordinates": [
                [[72.8, 19.1], [72.81, 19.1], [72.81, 19.11], [72.8, 19.11], [72.8, 19.1]]
            ],
        }
        wkt = geojson_to_wkt(original)
        # Strip the SRID prefix for the reverse conversion
        wkt_only = wkt.split(";", 1)[1] if wkt.startswith("SRID=") else wkt
        parsed = _wkt_to_geojson(wkt_only)
        assert parsed["type"] == "Polygon"
        assert len(parsed["coordinates"]) == 1
        assert len(parsed["coordinates"][0]) == 5

    def test_wkt_to_geojson_with_srid_prefix(self):
        """WKT with SRID prefix is correctly stripped."""
        wkt = "SRID=4326;POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))"
        parsed = _wkt_to_geojson(wkt)
        assert parsed["type"] == "Polygon"
        assert len(parsed["coordinates"][0]) == 5
