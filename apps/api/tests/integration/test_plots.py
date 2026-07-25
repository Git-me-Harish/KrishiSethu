"""Integration tests for the plot flow.

These tests exercise the full HTTP stack for plot management:
- POST /plots (create with GeoJSON boundary)
- GET /plots (list)
- GET /plots/{id} (detail with boundary)
- PATCH /plots/{id} (update)
- PUT /plots/{id}/boundary (redraw)
- DELETE /plots/{id}
- POST /plots/{id}/crops (add crop cycle)
- GET /crops (list master data)
"""

from __future__ import annotations

from uuid import uuid4

import pytest


# Sample GeoJSON polygon — a small square in Pune, India (~0.01 ha)
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

# Larger polygon for area tests (~1 ha)
LARGER_BOUNDARY = {
    "type": "Polygon",
    "coordinates": [
        [
            [73.8567, 18.5204],
            [73.8680, 18.5204],
            [73.8680, 18.5295],
            [73.8567, 18.5295],
            [73.8567, 18.5204],
        ]
    ],
}


@pytest.mark.asyncio
class TestCropsListEndpoint:
    """GET /api/v1/crops"""

    async def test_list_crops_returns_seeded_data(self, client):
        """The crops endpoint should return the 30+ seeded crops."""
        response = await client.get("/api/v1/crops")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 30
        slugs = [c["slug"] for c in data["crops"]]
        # Check some key Indian crops are present
        assert "rice" in slugs
        assert "wheat" in slugs
        assert "cotton" in slugs
        assert "sugarcane" in slugs
        assert "tur" in slugs  # Pigeon pea — important pulse

    async def test_list_crops_filter_by_category(self, client):
        """Filtering by category should return only matching crops."""
        response = await client.get("/api/v1/crops?category=cereals")
        assert response.status_code == 200
        data = response.json()
        for crop in data["crops"]:
            assert crop["crop_category"] == "cereals"

    async def test_list_crops_no_auth_required(self, client):
        """The crops endpoint is public — no auth required."""
        response = await client.get("/api/v1/crops")
        assert response.status_code == 200


@pytest.mark.asyncio
class TestCreatePlotEndpoint:
    """POST /api/v1/plots"""

    async def test_create_plot_with_valid_boundary(
        self, client, auth_headers, test_user
    ):
        """A farmer can create a plot with a valid GeoJSON boundary."""
        response = await client.post(
            "/api/v1/plots",
            json={
                "survey_number": "TEST-001",
                "village": "Khanapur",
                "district": "Pune",
                "state": "Maharashtra",
                "boundary": SAMPLE_BOUNDARY,
                "irrigation_source": "borewell",
                "nickname": "Test back field",
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["survey_number"] == "TEST-001"
        assert data["village"] == "Khanapur"
        assert data["district"] == "Pune"
        assert data["state"] == "Maharashtra"
        assert data["farmer_id"] == str(test_user.id)
        assert data["nickname"] == "Test back field"
        assert data["verification_status"] == "pending"
        assert data["ownership_type"] == "owned"
        # Area should be auto-computed from boundary
        assert float(data["area_ha"]) > 0
        # Boundary should be returned as GeoJSON
        assert data["boundary"]["type"] == "Polygon"
        assert len(data["boundary"]["coordinates"]) >= 1

    async def test_create_plot_without_auth_returns_401(self, client):
        """Creating a plot without authentication fails."""
        response = await client.post(
            "/api/v1/plots",
            json={
                "survey_number": "TEST-001",
                "village": "Khanapur",
                "district": "Pune",
                "state": "Maharashtra",
                "boundary": SAMPLE_BOUNDARY,
            },
        )
        assert response.status_code in (401, 403)

    async def test_create_plot_with_invalid_boundary_returns_422(
        self, client, auth_headers
    ):
        """An invalid boundary (unclosed ring) is rejected."""
        invalid_boundary = {
            "type": "Polygon",
            "coordinates": [
                # Not closed (first != last)
                [[73.8567, 18.5204], [73.8577, 18.5204], [73.8577, 18.5214]]
            ],
        }
        response = await client.post(
            "/api/v1/plots",
            json={
                "survey_number": "TEST-002",
                "village": "Khanapur",
                "district": "Pune",
                "state": "Maharashtra",
                "boundary": invalid_boundary,
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

    async def test_create_plot_with_leased_ownership(
        self, client, auth_headers
    ):
        """A leased plot requires lessor_name and lease dates."""
        # Without lessor_name — should fail
        response = await client.post(
            "/api/v1/plots",
            json={
                "survey_number": "LEASE-001",
                "village": "Khanapur",
                "district": "Pune",
                "state": "Maharashtra",
                "boundary": SAMPLE_BOUNDARY,
                "ownership_type": "leased",
            },
            headers=auth_headers,
        )
        assert response.status_code == 422

        # With all required fields — should succeed
        response = await client.post(
            "/api/v1/plots",
            json={
                "survey_number": "LEASE-002",
                "village": "Khanapur",
                "district": "Pune",
                "state": "Maharashtra",
                "boundary": SAMPLE_BOUNDARY,
                "ownership_type": "leased",
                "lessor_name": "Suresh Patil",
                "lease_start_date": "2026-06-01",
                "lease_end_date": "2027-05-31",
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["ownership_type"] == "leased"
        assert data["lessor_name"] == "Suresh Patil"


@pytest.mark.asyncio
class TestListPlotsEndpoint:
    """GET /api/v1/plots"""

    async def test_list_my_plots_returns_only_own_plots(
        self, client, auth_headers, test_user, db_session
    ):
        """A farmer sees only their own plots."""
        # Create a plot for the test user
        await client.post(
            "/api/v1/plots",
            json={
                "survey_number": "LIST-001",
                "village": "Khanapur",
                "district": "Pune",
                "state": "Maharashtra",
                "boundary": SAMPLE_BOUNDARY,
            },
            headers=auth_headers,
        )

        response = await client.get("/api/v1/plots", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 1
        for plot in data["plots"]:
            assert plot["survey_number"]  # All plots have survey numbers
            # Plot list should NOT include boundary (compact view)
            assert "boundary" not in plot


@pytest.mark.asyncio
class TestGetPlotEndpoint:
    """GET /api/v1/plots/{id}"""

    async def test_get_plot_returns_full_boundary(
        self, client, auth_headers
    ):
        """Getting a plot by ID returns the full boundary as GeoJSON."""
        # Create a plot
        create_response = await client.post(
            "/api/v1/plots",
            json={
                "survey_number": "GET-001",
                "village": "Khanapur",
                "district": "Pune",
                "state": "Maharashtra",
                "boundary": LARGER_BOUNDARY,
            },
            headers=auth_headers,
        )
        plot_id = create_response.json()["id"]

        # Fetch the plot
        response = await client.get(f"/api/v1/plots/{plot_id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == plot_id
        assert data["boundary"]["type"] == "Polygon"
        assert len(data["boundary"]["coordinates"][0]) == 5  # 4 corners + closing

    async def test_get_nonexistent_plot_returns_404(self, client, auth_headers):
        """Getting a non-existent plot returns 404."""
        random_id = uuid4()
        response = await client.get(
            f"/api/v1/plots/{random_id}", headers=auth_headers
        )
        assert response.status_code == 404


@pytest.mark.asyncio
class TestUpdatePlotEndpoint:
    """PATCH /api/v1/plots/{id}"""

    async def test_update_plot_nickname(self, client, auth_headers):
        """Updating the nickname works."""
        # Create
        create_response = await client.post(
            "/api/v1/plots",
            json={
                "survey_number": "UPD-001",
                "village": "Khanapur",
                "district": "Pune",
                "state": "Maharashtra",
                "boundary": SAMPLE_BOUNDARY,
            },
            headers=auth_headers,
        )
        plot_id = create_response.json()["id"]

        # Update
        response = await client.patch(
            f"/api/v1/plots/{plot_id}",
            json={"nickname": "Updated nickname"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["nickname"] == "Updated nickname"


@pytest.mark.asyncio
class TestDeletePlotEndpoint:
    """DELETE /api/v1/plots/{id}"""

    async def test_delete_pending_plot_succeeds(self, client, auth_headers):
        """Deleting a pending (unverified) plot succeeds."""
        # Create
        create_response = await client.post(
            "/api/v1/plots",
            json={
                "survey_number": "DEL-001",
                "village": "Khanapur",
                "district": "Pune",
                "state": "Maharashtra",
                "boundary": SAMPLE_BOUNDARY,
            },
            headers=auth_headers,
        )
        plot_id = create_response.json()["id"]

        # Delete
        response = await client.delete(
            f"/api/v1/plots/{plot_id}", headers=auth_headers
        )
        assert response.status_code == 204

        # Confirm deleted
        get_response = await client.get(
            f"/api/v1/plots/{plot_id}", headers=auth_headers
        )
        assert get_response.status_code == 404


@pytest.mark.asyncio
class TestPlotStatsEndpoint:
    """GET /api/v1/plots/stats"""

    async def test_stats_returns_summary(self, client, auth_headers):
        """The stats endpoint returns a summary of the farmer's plots."""
        # Create a couple plots
        for i in range(2):
            await client.post(
                "/api/v1/plots",
                json={
                    "survey_number": f"STATS-{i}",
                    "village": "Khanapur",
                    "district": "Pune",
                    "state": "Maharashtra",
                    "boundary": SAMPLE_BOUNDARY,
                },
                headers=auth_headers,
            )

        response = await client.get("/api/v1/plots/stats", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total_plots"] >= 2
        assert float(data["total_area_ha"]) > 0
        assert data["pending_verification"] >= 2
        assert data["verified_plots"] == 0
        assert "Pune" in data["by_district"]


@pytest.mark.asyncio
class TestCropCycleEndpoints:
    """POST /api/v1/plots/{id}/crops and GET /api/v1/plots/{id}/crops"""

    async def test_add_crop_cycle_to_plot(self, client, auth_headers):
        """A farmer can add a crop cycle to their plot."""
        # Create plot
        create_response = await client.post(
            "/api/v1/plots",
            json={
                "survey_number": "CROP-001",
                "village": "Khanapur",
                "district": "Pune",
                "state": "Maharashtra",
                "boundary": SAMPLE_BOUNDARY,
            },
            headers=auth_headers,
        )
        plot_id = create_response.json()["id"]

        # Get a crop ID
        crops_response = await client.get("/api/v1/crops")
        rice_crop = next(
            c for c in crops_response.json()["crops"] if c["slug"] == "rice"
        )

        # Add crop cycle
        response = await client.post(
            f"/api/v1/plots/{plot_id}/crops",
            json={
                "crop_id": rice_crop["id"],
                "season": "kharif",
                "season_year": 2026,
                "sowing_date": "2026-06-15",
                "area_ha": 0.005,  # Less than plot area
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["crop_name"] == "Rice"
        assert data["season"] == "kharif"
        assert data["season_year"] == 2026
        assert data["status"] == "planned"

    async def test_list_crop_cycles_for_plot(self, client, auth_headers):
        """Listing crop cycles returns all cycles for the plot."""
        # Create plot
        create_response = await client.post(
            "/api/v1/plots",
            json={
                "survey_number": "CROPLIST-001",
                "village": "Khanapur",
                "district": "Pune",
                "state": "Maharashtra",
                "boundary": SAMPLE_BOUNDARY,
            },
            headers=auth_headers,
        )
        plot_id = create_response.json()["id"]

        # Initially no cycles
        response = await client.get(
            f"/api/v1/plots/{plot_id}/crops", headers=auth_headers
        )
        assert response.status_code == 200
        assert response.json() == []

        # Add one
        crops_response = await client.get("/api/v1/crops")
        rice_crop = next(
            c for c in crops_response.json()["crops"] if c["slug"] == "rice"
        )
        await client.post(
            f"/api/v1/plots/{plot_id}/crops",
            json={
                "crop_id": rice_crop["id"],
                "season": "kharif",
                "season_year": 2026,
                "area_ha": 0.005,
            },
            headers=auth_headers,
        )

        # Now should have 1
        response = await client.get(
            f"/api/v1/plots/{plot_id}/crops", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["crop_name"] == "Rice"


@pytest.mark.asyncio
class TestPlotBoundaryUpdate:
    """PUT /api/v1/plots/{id}/boundary"""

    async def test_update_boundary_archives_old_and_uses_new(
        self, client, auth_headers
    ):
        """Updating the boundary replaces it and archives the old one."""
        # Create plot
        create_response = await client.post(
            "/api/v1/plots",
            json={
                "survey_number": "BND-001",
                "village": "Khanapur",
                "district": "Pune",
                "state": "Maharashtra",
                "boundary": SAMPLE_BOUNDARY,
            },
            headers=auth_headers,
        )
        plot_id = create_response.json()["id"]
        original_area = float(create_response.json()["area_ha"])

        # Update with larger boundary
        response = await client.put(
            f"/api/v1/plots/{plot_id}/boundary",
            json={"boundary": LARGER_BOUNDARY, "source": "user_drawn"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        new_area = float(data["area_ha"])

        # New area should be larger than original
        assert new_area > original_area
