"""Integration tests for soil & weather endpoints.

Tests the full HTTP stack:
- GET /weather/district/{district} (public)
- GET /weather/district/{district}/forecast
- POST /plots/{id}/soil-tests (manual entry)
- GET /plots/{id}/soil-tests
- GET /plots/{id}/weather/summary
"""

from __future__ import annotations

from uuid import uuid4

import pytest

# Sample plot boundary for creating test plots
SAMPLE_BOUNDARY = {
    "type": "Polygon",
    "coordinates": [
        [
            [73.8567, 18.5204],
            [73.8577, 18.5204],
            [73.8577, 18.5214],
            [73.8567, 18.5214],
            [73.8567, 18.5204],
        ]
    ],
}


@pytest.mark.asyncio
class TestDistrictWeatherEndpoints:
    """GET /api/v1/weather/district/* (public)"""

    async def test_get_district_current_weather(self, client):
        """Public endpoint returns current weather for a district."""
        response = await client.get(
            "/api/v1/weather/district/Pune?state=Maharashtra"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["district"] == "Pune"
        assert data["state"] == "Maharashtra"
        assert "temperature_c" in data
        assert "humidity_pct" in data
        assert "weather_main" in data
        assert "source" in data
        # In dev mode, source should be 'imd' (synthetic)
        assert data["source"] == "imd"

    async def test_get_district_weather_no_auth_required(self, client):
        """Weather endpoint is public — no auth required."""
        # No auth headers
        response = await client.get(
            "/api/v1/weather/district/Mumbai?state=Maharashtra"
        )
        assert response.status_code == 200

    async def test_get_district_forecast(self, client):
        """Public endpoint returns 7-day forecast."""
        response = await client.get(
            "/api/v1/weather/district/Pune/forecast?state=Maharashtra"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["district"] == "Pune"
        assert len(data["forecasts"]) == 7
        # First forecast should be today
        from datetime import date

        assert data["forecasts"][0]["forecast_date"] == date.today().isoformat()

    async def test_get_district_alerts_empty(self, client):
        """District alerts endpoint returns alerts list (may be empty)."""
        response = await client.get(
            "/api/v1/weather/district/Pune/alerts?state=Maharashtra"
        )
        assert response.status_code == 200
        data = response.json()
        assert "alerts" in data
        assert "total" in data
        assert isinstance(data["alerts"], list)


@pytest.mark.asyncio
class TestPlotSoilTestEndpoints:
    """POST /plots/{id}/soil-tests, GET /plots/{id}/soil-tests"""

    async def test_create_soil_test_requires_auth(self, client):
        random_plot_id = uuid4()
        response = await client.post(
            f"/api/v1/plots/{random_plot_id}/soil-tests",
            json={"test_date": "2026-07-19"},
        )
        assert response.status_code in (401, 403)

    async def test_create_soil_test_for_nonexistent_plot_404(
        self, client, auth_headers
    ):
        random_plot_id = uuid4()
        response = await client.post(
            f"/api/v1/plots/{random_plot_id}/soil-tests",
            json={"test_date": "2026-07-19"},
            headers=auth_headers,
        )
        assert response.status_code == 404

    async def test_create_and_list_soil_test(self, client, auth_headers):
        """Farmer can create a soil test and list it."""
        # First create a plot
        plot_response = await client.post(
            "/api/v1/plots",
            json={
                "survey_number": "SOIL-TEST-001",
                "village": "Khanapur",
                "district": "Pune",
                "state": "Maharashtra",
                "boundary": SAMPLE_BOUNDARY,
            },
            headers=auth_headers,
        )
        assert plot_response.status_code == 201
        plot_id = plot_response.json()["id"]

        # Create a soil test
        create_response = await client.post(
            f"/api/v1/plots/{plot_id}/soil-tests",
            json={
                "test_date": "2026-07-19",
                "lab_name": "District Soil Testing Lab",
                "nitrogen_n": 150.5,
                "phosphorus_p": 12.5,
                "potassium_k": 110.0,
                "ph": 6.5,
                "electrical_conductivity": 0.8,
                "organic_carbon": 0.65,
            },
            headers=auth_headers,
        )
        assert create_response.status_code == 201
        test_data = create_response.json()
        assert test_data["source"] == "lab_manual"
        assert test_data["lab_name"] == "District Soil Testing Lab"
        assert float(test_data["nitrogen_n"]) == 150.5
        assert float(test_data["ph"]) == 6.5
        # Fertilizer recommendation should be auto-generated
        assert test_data["fertilizer_recommendation"] is not None
        assert "kg N/ha" in test_data["fertilizer_recommendation"]

        # List soil tests — should have at least 1 (plus possibly ISRIC auto)
        list_response = await client.get(
            f"/api/v1/plots/{plot_id}/soil-tests", headers=auth_headers
        )
        assert list_response.status_code == 200
        list_data = list_response.json()
        assert list_data["total"] >= 1

    async def test_create_soil_test_invalid_ph_rejected(self, client, auth_headers):
        """pH > 14 should be rejected."""
        # Create plot
        plot_response = await client.post(
            "/api/v1/plots",
            json={
                "survey_number": "SOIL-INVALID-001",
                "village": "Khanapur",
                "district": "Pune",
                "state": "Maharashtra",
                "boundary": SAMPLE_BOUNDARY,
            },
            headers=auth_headers,
        )
        plot_id = plot_response.json()["id"]

        # Try to create soil test with invalid pH
        response = await client.post(
            f"/api/v1/plots/{plot_id}/soil-tests",
            json={
                "test_date": "2026-07-19",
                "ph": 15.5,  # Invalid
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    async def test_create_soil_test_partial_texture_rejected(
        self, client, auth_headers
    ):
        """Providing some texture % but not all three should be rejected."""
        plot_response = await client.post(
            "/api/v1/plots",
            json={
                "survey_number": "SOIL-TEXTURE-001",
                "village": "Khanapur",
                "district": "Pune",
                "state": "Maharashtra",
                "boundary": SAMPLE_BOUNDARY,
            },
            headers=auth_headers,
        )
        plot_id = plot_response.json()["id"]

        response = await client.post(
            f"/api/v1/plots/{plot_id}/soil-tests",
            json={
                "test_date": "2026-07-19",
                "clay_pct": 30,  # Only one of three
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    async def test_soil_test_recommendation_for_acidic_soil(
        self, client, auth_headers
    ):
        """Acidic soil (pH < 5.5) should trigger lime amendment recommendation."""
        plot_response = await client.post(
            "/api/v1/plots",
            json={
                "survey_number": "SOIL-ACIDIC-001",
                "village": "Khanapur",
                "district": "Pune",
                "state": "Maharashtra",
                "boundary": SAMPLE_BOUNDARY,
            },
            headers=auth_headers,
        )
        plot_id = plot_response.json()["id"]

        response = await client.post(
            f"/api/v1/plots/{plot_id}/soil-tests",
            json={
                "test_date": "2026-07-19",
                "ph": 5.0,  # Acidic
                "nitrogen_n": 150,
                "phosphorus_p": 12,
                "potassium_k": 110,
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        test_data = response.json()
        # Should have amendment recommendation mentioning lime
        assert test_data["amendment_recommendation"] is not None
        assert "lime" in test_data["amendment_recommendation"].lower()


@pytest.mark.asyncio
class TestPlotWeatherEndpoints:
    """GET /plots/{id}/weather/* (require auth + plot ownership)"""

    async def test_get_plot_weather_summary(self, client, auth_headers):
        """Get aggregated weather summary for a plot."""
        # Create plot in Pune
        plot_response = await client.post(
            "/api/v1/plots",
            json={
                "survey_number": "WEATHER-SUMMARY-001",
                "village": "Khanapur",
                "district": "Pune",
                "state": "Maharashtra",
                "boundary": SAMPLE_BOUNDARY,
            },
            headers=auth_headers,
        )
        plot_id = plot_response.json()["id"]

        # Get summary
        response = await client.get(
            f"/api/v1/plots/{plot_id}/weather/summary", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["plot_id"] == plot_id
        assert data["district"] == "Pune"
        assert "current" in data
        assert "forecast" in data
        assert "active_alerts" in data
        assert len(data["forecast"]) == 7

    async def test_get_plot_weather_without_auth_fails(self, client):
        random_plot_id = uuid4()
        response = await client.get(
            f"/api/v1/plots/{random_plot_id}/weather/current"
        )
        assert response.status_code in (401, 403)

    async def test_get_plot_weather_for_nonexistent_plot_404(
        self, client, auth_headers
    ):
        random_plot_id = uuid4()
        response = await client.get(
            f"/api/v1/plots/{random_plot_id}/weather/current",
            headers=auth_headers,
        )
        assert response.status_code == 404

    async def test_get_plot_forecast(self, client, auth_headers):
        """Get 7-day forecast for a plot."""
        plot_response = await client.post(
            "/api/v1/plots",
            json={
                "survey_number": "WEATHER-FORECAST-001",
                "village": "Khanapur",
                "district": "Pune",
                "state": "Maharashtra",
                "boundary": SAMPLE_BOUNDARY,
            },
            headers=auth_headers,
        )
        plot_id = plot_response.json()["id"]

        response = await client.get(
            f"/api/v1/plots/{plot_id}/weather/forecast", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["plot_id"] == plot_id
        assert len(data["forecasts"]) == 7

    async def test_get_plot_alerts(self, client, auth_headers):
        """Get active alerts for a plot's district."""
        plot_response = await client.post(
            "/api/v1/plots",
            json={
                "survey_number": "WEATHER-ALERTS-001",
                "village": "Khanapur",
                "district": "Pune",
                "state": "Maharashtra",
                "boundary": SAMPLE_BOUNDARY,
            },
            headers=auth_headers,
        )
        plot_id = plot_response.json()["id"]

        response = await client.get(
            f"/api/v1/plots/{plot_id}/weather/alerts", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "alerts" in data
        assert "total" in data
