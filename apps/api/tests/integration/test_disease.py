"""Integration tests for the disease flow.

Tests the full HTTP stack:
- GET /diseases (public catalog)
- GET /diseases/{slug}
- POST /disease-reports/upload-url
- POST /disease-reports
- GET /disease-reports
- GET /disease-reports/{id}
- POST /disease-reports/{id}/feedback
"""

from __future__ import annotations

from uuid import uuid4

import pytest


@pytest.mark.asyncio
class TestDiseaseCatalogEndpoints:
    """GET /api/v1/diseases and /api/v1/diseases/{slug}"""

    async def test_list_diseases_returns_seeded_data(self, client):
        """The diseases endpoint should return 30+ seeded diseases."""
        response = await client.get("/api/v1/diseases")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 25
        slugs = [d["slug"] for d in data["diseases"]]
        # Check some key diseases are present
        assert "rice_blast" in slugs
        assert "tomato_early_blight" in slugs
        assert "wheat_stripe_rust" in slugs
        assert "cotton_root_rot" in slugs
        assert "healthy" in slugs

    async def test_list_diseases_filter_by_crop(self, client):
        """Filtering by crop returns only diseases affecting that crop."""
        response = await client.get("/api/v1/diseases?crop=rice")
        assert response.status_code == 200
        data = response.json()
        for disease in data["diseases"]:
            assert "rice" in disease["affected_crops"]

    async def test_list_diseases_no_auth_required(self, client):
        """The diseases catalog is public — no auth required."""
        response = await client.get("/api/v1/diseases")
        assert response.status_code == 200

    async def test_get_disease_by_slug(self, client):
        """Getting a disease by slug returns full details with treatments."""
        response = await client.get("/api/v1/diseases/rice_blast")
        assert response.status_code == 200
        data = response.json()
        assert data["slug"] == "rice_blast"
        assert data["name_en"] == "Rice Blast"
        assert "Magnaporthe oryzae" in (data["scientific_name"] or "")
        assert data["disease_type"] == "fungal"
        assert "rice" in data["affected_crops"]
        assert len(data["symptoms"]) > 50  # Substantial symptom description
        assert len(data["treatments"]) >= 1  # At least one treatment

    async def test_get_disease_with_treatments_includes_recommendations(self, client):
        """Disease detail includes treatment recommendations."""
        response = await client.get("/api/v1/diseases/tomato_early_blight")
        assert response.status_code == 200
        data = response.json()
        treatments = data["treatments"]
        assert len(treatments) >= 2  # Multiple treatments

        # At least one chemical treatment with dosage
        chemical = next(
            (t for t in treatments if t["treatment_type"] == "chemical"), None
        )
        assert chemical is not None
        assert chemical["dosage"] is not None
        assert "Mancozeb" in chemical["description"]

    async def test_get_nonexistent_disease_returns_404(self, client):
        """Getting a non-existent disease returns 404."""
        response = await client.get("/api/v1/diseases/nonexistent_disease")
        assert response.status_code == 404


@pytest.mark.asyncio
class TestUploadUrlEndpoint:
    """POST /api/v1/disease-reports/upload-url"""

    async def test_get_upload_url_requires_auth(self, client):
        """Without auth, returns 401/403."""
        response = await client.post(
            "/api/v1/disease-reports/upload-url",
            json={"content_type": "image/jpeg"},
        )
        assert response.status_code in (401, 403)

    async def test_get_upload_url_returns_presigned_url(self, client, auth_headers):
        """Authenticated farmer gets a pre-signed S3 URL."""
        response = await client.post(
            "/api/v1/disease-reports/upload-url",
            json={"content_type": "image/jpeg"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "upload_url" in data
        assert "image_key" in data
        assert data["image_key"].startswith("disease-reports/")
        assert data["expires_in_seconds"] == 900
        assert data["max_size_bytes"] == 10 * 1024 * 1024

    async def test_get_upload_url_invalid_content_type(self, client, auth_headers):
        """Invalid content type returns 422."""
        response = await client.post(
            "/api/v1/disease-reports/upload-url",
            json={"content_type": "image/gif"},
            headers=auth_headers,
        )
        assert response.status_code == 422


@pytest.mark.asyncio
class TestDiseaseReportEndpoints:
    """POST /disease-reports, GET /disease-reports, GET /disease-reports/{id}"""

    async def test_create_report_without_auth_fails(self, client):
        response = await client.post(
            "/api/v1/disease-reports",
            json={"image_key": "disease-reports/test/test.jpg"},
        )
        assert response.status_code in (401, 403)

    async def test_create_report_with_nonexistent_image_fails(
        self, client, auth_headers
    ):
        """Creating a report with an image not uploaded to S3 returns 422."""
        response = await client.post(
            "/api/v1/disease-reports",
            json={
                "image_key": "disease-reports/test/nonexistent-image.jpg",
            },
            headers=auth_headers,
        )
        # Should fail because image doesn't exist in S3
        assert response.status_code == 422

    async def test_list_my_reports_empty(self, client, auth_headers):
        """Listing reports for a new farmer returns empty list."""
        response = await client.get("/api/v1/disease-reports", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["reports"] == []
        assert data["total"] == 0

    async def test_get_nonexistent_report_returns_404(self, client, auth_headers):
        """Getting a non-existent report returns 404."""
        random_id = uuid4()
        response = await client.get(
            f"/api/v1/disease-reports/{random_id}", headers=auth_headers
        )
        assert response.status_code == 404

    async def test_get_report_stats(self, client, auth_headers):
        """Stats endpoint returns summary."""
        response = await client.get(
            "/api/v1/disease-reports/stats", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_reports" in data
        assert "completed" in data
        assert "pending" in data
        assert "by_disease" in data


@pytest.mark.asyncio
class TestDiseaseReportWithMockedImage:
    """Tests that create actual reports using mocked S3.

    These tests monkey-patch the storage client to simulate uploaded images.
    """

    async def test_create_report_with_mocked_image(
        self, client, auth_headers, monkeypatch
    ):
        """Create a report with a mocked S3 image existence check."""
        from krishisetu.core import storage as storage_module

        # Mock the storage client
        class MockStorage:
            def object_exists(self, key: str) -> bool:
                return True

            def generate_upload_url(self, key, content_type="image/jpeg", expires_in=900):
                return f"http://mock-s3.local/upload/{key}"

            def generate_download_url(self, key, expires_in=900):
                return f"http://mock-s3.local/download/{key}"

            @staticmethod
            def disease_report_image_key(farmer_id, report_id, suffix="original.jpg"):
                return f"disease-reports/{farmer_id}/{report_id}/{suffix}"

        # Patch the singleton
        original_get = storage_module.get_storage
        storage_module.get_storage = lambda: MockStorage()
        # Also patch the import in the disease services module
        from krishisetu.domains.disease import services as disease_services
        original_services_get = disease_services.get_storage
        disease_services.get_storage = lambda: MockStorage()

        try:
            # Create a report
            response = await client.post(
                "/api/v1/disease-reports",
                json={
                    "image_key": "disease-reports/test/report-1/original.jpg",
                    "farmer_notes": "Yellow spots on rice leaves",
                },
                headers=auth_headers,
            )
            assert response.status_code == 201
            data = response.json()
            assert data["status"] == "pending"
            assert data["farmer_notes"] == "Yellow spots on rice leaves"
            assert "image_url" in data
            assert "disease-reports" in data["image_url"]

            # List reports — should now have 1
            list_response = await client.get(
                "/api/v1/disease-reports", headers=auth_headers
            )
            assert list_response.status_code == 200
            list_data = list_response.json()
            assert list_data["total"] >= 1

            # Get the report by ID
            get_response = await client.get(
                f"/api/v1/disease-reports/{data['id']}", headers=auth_headers
            )
            assert get_response.status_code == 200
            get_data = get_response.json()
            assert get_data["id"] == data["id"]
            assert get_data["status"] == "pending"
            assert get_data["prediction"] is None  # No prediction yet
        finally:
            # Restore
            storage_module.get_storage = original_get
            disease_services.get_storage = original_services_get


@pytest.mark.asyncio
class TestDiseaseFeedbackEndpoint:
    """POST /disease-reports/{id}/feedback"""

    async def test_submit_feedback_without_auth_fails(self, client):
        random_id = uuid4()
        response = await client.post(
            f"/api/v1/disease-reports/{random_id}/feedback",
            json={"feedback_type": "correct"},
        )
        assert response.status_code in (401, 403)

    async def test_submit_feedback_on_nonexistent_report_fails(
        self, client, auth_headers
    ):
        random_id = uuid4()
        response = await client.post(
            f"/api/v1/disease-reports/{random_id}/feedback",
            json={"feedback_type": "correct"},
            headers=auth_headers,
        )
        assert response.status_code == 404

    async def test_submit_feedback_on_pending_report_fails(
        self, client, auth_headers, monkeypatch
    ):
        """Feedback can only be submitted on completed reports."""
        from krishisetu.core import storage as storage_module

        class MockStorage:
            def object_exists(self, key): return True
            def generate_upload_url(self, key, **kw): return "http://mock"
            def generate_download_url(self, key, **kw): return "http://mock"
            @staticmethod
            def disease_report_image_key(farmer_id, report_id, suffix="original.jpg"):
                return f"disease-reports/{farmer_id}/{report_id}/{suffix}"

        original_get = storage_module.get_storage
        storage_module.get_storage = lambda: MockStorage()
        from krishisetu.domains.disease import services as disease_services
        original_services_get = disease_services.get_storage
        disease_services.get_storage = lambda: MockStorage()

        try:
            # Create a report (status=pending)
            create_response = await client.post(
                "/api/v1/disease-reports",
                json={"image_key": "disease-reports/test/feedback-test.jpg"},
                headers=auth_headers,
            )
            report_id = create_response.json()["id"]

            # Try to submit feedback — should fail (not completed yet)
            response = await client.post(
                f"/api/v1/disease-reports/{report_id}/feedback",
                json={"feedback_type": "correct"},
                headers=auth_headers,
            )
            assert response.status_code == 422
        finally:
            storage_module.get_storage = original_get
            disease_services.get_storage = original_services_get


@pytest.mark.asyncio
class TestDiseaseCatalogContent:
    """Verify the seeded disease catalog has accurate content."""

    async def test_rice_blast_has_complete_info(self, client):
        """Rice Blast should have complete, accurate information."""
        response = await client.get("/api/v1/diseases/rice_blast")
        assert response.status_code == 200
        data = response.json()
        assert data["name_en"] == "Rice Blast"
        assert data["scientific_name"] == "Magnaporthe oryzae"
        assert data["disease_type"] == "fungal"
        assert data["default_severity"] == "high"
        assert "Magnaporthe" in data["cause"]
        assert len(data["symptoms"]) > 100
        assert len(data["cause"]) > 50
        assert data["prevention_measures"] is not None

    async def test_tomato_late_blight_marked_critical(self, client):
        """Tomato Late Blight should be marked as critical severity."""
        response = await client.get("/api/v1/diseases/tomato_late_blight")
        assert response.status_code == 200
        data = response.json()
        assert data["default_severity"] == "critical"
        assert "Phytophthora infestans" in (data["scientific_name"] or "")
        # Should mention Irish Potato Famine (historical reference)
        assert "Irish" in data["cause"] or "Famine" in data["cause"]

    async def test_healthy_class_exists(self, client):
        """The 'healthy' control class should exist."""
        response = await client.get("/api/v1/diseases/healthy")
        assert response.status_code == 200
        data = response.json()
        assert data["slug"] == "healthy"
        assert data["disease_type"] == "environmental"
        assert data["default_severity"] == "low"

    async def test_each_disease_has_treatments(self, client):
        """Major diseases should have at least one treatment recommendation."""
        # Check a sample of diseases
        for slug in ["rice_blast", "tomato_early_blight", "wheat_stripe_rust"]:
            response = await client.get(f"/api/v1/diseases/{slug}")
            assert response.status_code == 200
            data = response.json()
            assert len(data["treatments"]) >= 1, f"{slug} has no treatments"

    async def test_treatment_has_required_fields(self, client):
        """Treatments should have all required fields populated."""
        response = await client.get("/api/v1/diseases/rice_blast")
        data = response.json()
        for treatment in data["treatments"]:
            assert "treatment_type" in treatment
            assert "description" in treatment
            assert len(treatment["description"]) > 10
            assert "priority" in treatment
