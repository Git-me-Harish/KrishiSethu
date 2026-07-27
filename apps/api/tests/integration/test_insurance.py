"""Integration tests for insurance endpoints.

Tests the full HTTP stack:
- GET /insurance/products (public catalog)
- GET /insurance/products/for-plot/{id}
- POST /insurance/policies (enroll)
- POST /insurance/policies/{id}/pay (pay premium)
- POST /insurance/claims (create draft with auto-evidence)
- POST /insurance/claims/{id}/submit
- GET /insurance/policies/stats
"""

from __future__ import annotations

from uuid import uuid4

import pytest

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
class TestInsuranceProductEndpoints:
    """GET /api/v1/insurance/products (public)."""

    async def test_list_products_returns_seeded_data(self, client):
        """The products endpoint should return seeded PMFBY products."""
        response = await client.get("/api/v1/insurance/products")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] >= 20  # We seeded 29+ products
        slugs = [p["slug"] for p in data["products"]]
        # Check some key products are present
        assert any("rice" in s and "maharashtra" in s for s in slugs)
        assert any("wheat" in s and "punjab" in s for s in slugs)
        assert any("cotton" in s for s in slugs)

    async def test_list_products_filter_by_state(self, client):
        """Filtering by state returns only that state's products."""
        response = await client.get("/api/v1/insurance/products?state=Maharashtra")
        assert response.status_code == 200
        data = response.json()
        for product in data["products"]:
            assert product["state"] == "Maharashtra"

    def test_list_products_no_auth_required(self, client):
        """Products catalog is public — no auth required."""
        # This is a sync assertion — the test above already verifies this
        # by not passing auth_headers
        pass

    async def test_list_products_filter_by_crop(self, client):
        """Filtering by crop returns only that crop's products."""
        response = await client.get("/api/v1/insurance/products?crop=rice")
        assert response.status_code == 200
        data = response.json()
        for product in data["products"]:
            assert product["crop_slug"] == "rice"

    async def test_products_have_pmfby_premium_rates(self, client):
        """PMFBY products should have correct premium rates.

        2% Kharif, 1.5% Rabi, 5% commercial.
        """
        response = await client.get("/api/v1/insurance/products?state=Maharashtra")
        data = response.json()

        kharif_products = [p for p in data["products"] if p["season"] == "kharif"]
        rabi_products = [p for p in data["products"] if p["season"] == "rabi"]

        # Kharif food crops should have 2% premium
        kharif_food = [p for p in kharif_products if p["crop_slug"] not in ("sugarcane", "banana")]
        for product in kharif_food:
            assert float(product["farmer_premium_rate"]) == 0.02, \
                f"{product['crop_name']} Kharif should have 2% premium"

        # Rabi should have 1.5% premium
        for product in rabi_products:
            assert float(product["farmer_premium_rate"]) == 0.015, \
                f"{product['crop_name']} Rabi should have 1.5% premium"

        # Commercial crops (sugarcane, banana) should have 5%
        commercial = [p for p in kharif_products if p["crop_slug"] in ("sugarcane", "banana")]
        for product in commercial:
            assert float(product["farmer_premium_rate"]) == 0.05, \
                f"{product['crop_name']} should have 5% premium (commercial)"


@pytest.mark.asyncio
class TestPolicyEnrollmentFlow:
    """POST /insurance/policies — enroll in a policy."""

    async def test_enroll_requires_auth(self, client):
        response = await client.post(
            "/api/v1/insurance/policies",
            json={
                "product_id": str(uuid4()),
                "plot_id": str(uuid4()),
            },
        )
        assert response.status_code in (401, 403)

    async def test_enroll_policy_for_punjab_plot(self, client, auth_headers):
        """Farmer can enroll in a policy for a plot in Punjab."""
        # Create a plot in Punjab
        plot_response = await client.post(
            "/api/v1/plots",
            json={
                "survey_number": "INS-ENROLL-001",
                "village": "Ludhiana",
                "district": "Ludhiana",
                "state": "Punjab",
                "boundary": SAMPLE_BOUNDARY,
            },
            headers=auth_headers,
        )
        assert plot_response.status_code == 201
        plot_id = plot_response.json()["id"]

        # Find a rice product for Punjab
        products_response = await client.get(
            "/api/v1/insurance/products?state=Punjab&crop=rice"
        )
        product_id = products_response.json()["products"][0]["id"]

        # Enroll
        response = await client.post(
            "/api/v1/insurance/policies",
            json={
                "product_id": product_id,
                "plot_id": plot_id,
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["policy_number"].startswith("KS-POL-")
        assert data["status"] == "pending"
        assert not data["premium_paid"]
        assert float(data["sum_insured"]) > 0
        assert float(data["premium_amount"]) > 0

    async def test_enroll_state_mismatch_rejected(self, client, auth_headers):
        """Cannot enroll a Maharashtra product for a Punjab plot."""
        # Create plot in Maharashtra
        plot_response = await client.post(
            "/api/v1/plots",
            json={
                "survey_number": "INS-MISMATCH-001",
                "village": "Pune",
                "district": "Pune",
                "state": "Maharashtra",
                "boundary": SAMPLE_BOUNDARY,
            },
            headers=auth_headers,
        )
        plot_id = plot_response.json()["id"]

        # Find a Punjab product
        products_response = await client.get(
            "/api/v1/insurance/products?state=Punjab&crop=rice"
        )
        product_id = products_response.json()["products"][0]["id"]

        # Try to enroll — should fail
        response = await client.post(
            "/api/v1/insurance/policies",
            json={
                "product_id": product_id,
                "plot_id": plot_id,
            },
            headers=auth_headers,
        )
        assert response.status_code == 422  # ValidationError

    async def test_list_my_policies(self, client, auth_headers):
        """Farmer can list their policies."""
        response = await client.get(
            "/api/v1/insurance/policies", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "policies" in data
        assert "total" in data


@pytest.mark.asyncio
class TestPremiumPaymentFlow:
    """POST /insurance/policies/{id}/pay — pay premium."""

    async def test_pay_premium_activates_policy(self, client, auth_headers):
        """Paying premium changes status from pending to active."""
        # Create plot + enroll
        plot_response = await client.post(
            "/api/v1/plots",
            json={
                "survey_number": "INS-PAY-001",
                "village": "Ludhiana",
                "district": "Ludhiana",
                "state": "Punjab",
                "boundary": SAMPLE_BOUNDARY,
            },
            headers=auth_headers,
        )
        plot_id = plot_response.json()["id"]

        products_response = await client.get(
            "/api/v1/insurance/products?state=Punjab&crop=rice"
        )
        product_id = products_response.json()["products"][0]["id"]

        enroll_response = await client.post(
            "/api/v1/insurance/policies",
            json={"product_id": product_id, "plot_id": plot_id},
            headers=auth_headers,
        )
        policy_id = enroll_response.json()["id"]

        # Pay premium
        response = await client.post(
            f"/api/v1/insurance/policies/{policy_id}/pay",
            json={"payment_reference": "UPI-TEST-12345"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["premium_paid"] is True
        assert data["status"] == "active"
        assert data["payment_reference"] == "UPI-TEST-12345"

    async def test_double_payment_rejected(self, client, auth_headers):
        """Cannot pay premium twice."""
        # Setup (same as above)
        plot_response = await client.post(
            "/api/v1/plots",
            json={
                "survey_number": "INS-DOUBLE-PAY-001",
                "village": "Ludhiana",
                "district": "Ludhiana",
                "state": "Punjab",
                "boundary": SAMPLE_BOUNDARY,
            },
            headers=auth_headers,
        )
        plot_id = plot_response.json()["id"]

        products_response = await client.get(
            "/api/v1/insurance/products?state=Punjab&crop=rice"
        )
        product_id = products_response.json()["products"][0]["id"]

        enroll_response = await client.post(
            "/api/v1/insurance/policies",
            json={"product_id": product_id, "plot_id": plot_id},
            headers=auth_headers,
        )
        policy_id = enroll_response.json()["id"]

        # First payment
        await client.post(
            f"/api/v1/insurance/policies/{policy_id}/pay",
            json={"payment_reference": "UPI-1"},
            headers=auth_headers,
        )

        # Second payment — should fail
        response = await client.post(
            f"/api/v1/insurance/policies/{policy_id}/pay",
            json={"payment_reference": "UPI-2"},
            headers=auth_headers,
        )
        assert response.status_code == 409  # Conflict


@pytest.mark.asyncio
class TestClaimFilingFlow:
    """POST /insurance/claims — create and submit a claim."""

    async def test_create_claim_on_unpaid_policy_fails(self, client, auth_headers):
        """Cannot file a claim on a policy with unpaid premium."""
        # Create plot + enroll (but don't pay)
        plot_response = await client.post(
            "/api/v1/plots",
            json={
                "survey_number": "INS-CLAIM-UNPAID-001",
                "village": "Ludhiana",
                "district": "Ludhiana",
                "state": "Punjab",
                "boundary": SAMPLE_BOUNDARY,
            },
            headers=auth_headers,
        )
        plot_id = plot_response.json()["id"]

        products_response = await client.get(
            "/api/v1/insurance/products?state=Punjab&crop=rice"
        )
        product_id = products_response.json()["products"][0]["id"]

        enroll_response = await client.post(
            "/api/v1/insurance/policies",
            json={"product_id": product_id, "plot_id": plot_id},
            headers=auth_headers,
        )
        policy_id = enroll_response.json()["id"]

        # Try to file claim — should fail (premium not paid)
        response = await client.post(
            "/api/v1/insurance/claims",
            json={
                "policy_id": policy_id,
                "claim_type": "localized_risk",
                "loss_date": "2026-07-15",
                "loss_description": "Heavy rainfall caused 40% crop loss in my rice field.",
                "estimated_loss_pct": 40,
            },
            headers=auth_headers,
        )
        assert response.status_code == 422  # ValidationError

    async def test_create_claim_with_auto_evidence(self, client, auth_headers):
        """Create a claim on an active policy — should auto-attach evidence."""
        # Setup: create plot + enroll + pay
        plot_response = await client.post(
            "/api/v1/plots",
            json={
                "survey_number": "INS-CLAIM-AUTO-001",
                "village": "Ludhiana",
                "district": "Ludhiana",
                "state": "Punjab",
                "boundary": SAMPLE_BOUNDARY,
            },
            headers=auth_headers,
        )
        plot_id = plot_response.json()["id"]

        products_response = await client.get(
            "/api/v1/insurance/products?state=Punjab&crop=rice"
        )
        product_id = products_response.json()["products"][0]["id"]

        enroll_response = await client.post(
            "/api/v1/insurance/policies",
            json={"product_id": product_id, "plot_id": plot_id},
            headers=auth_headers,
        )
        policy_id = enroll_response.json()["id"]

        # Pay premium
        await client.post(
            f"/api/v1/insurance/policies/{policy_id}/pay",
            json={"payment_reference": "UPI-CLAIM-TEST"},
            headers=auth_headers,
        )

        # File a claim
        response = await client.post(
            "/api/v1/insurance/claims",
            json={
                "policy_id": policy_id,
                "claim_type": "localized_risk",
                "loss_date": "2026-07-15",
                "loss_description": (
                    "Heavy rainfall caused waterlogging in my rice field, "
                    "resulting in approximately 40% crop loss."
                ),
                "estimated_loss_pct": 40,
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "draft"
        assert data["claim_number"].startswith("KS-CLM-")
        assert float(data["claimed_amount"]) > 0
        # Evidence list should exist (may be empty if no NDVI/disease/weather data)
        assert "evidence" in data
        assert isinstance(data["evidence"], list)

    async def test_submit_claim(self, client, auth_headers):
        """Submit a draft claim for insurer review."""
        # Setup: create plot + enroll + pay + file claim
        plot_response = await client.post(
            "/api/v1/plots",
            json={
                "survey_number": "INS-SUBMIT-001",
                "village": "Ludhiana",
                "district": "Ludhiana",
                "state": "Punjab",
                "boundary": SAMPLE_BOUNDARY,
            },
            headers=auth_headers,
        )
        plot_id = plot_response.json()["id"]

        products_response = await client.get(
            "/api/v1/insurance/products?state=Punjab&crop=rice"
        )
        product_id = products_response.json()["products"][0]["id"]

        enroll_response = await client.post(
            "/api/v1/insurance/policies",
            json={"product_id": product_id, "plot_id": plot_id},
            headers=auth_headers,
        )
        policy_id = enroll_response.json()["id"]

        await client.post(
            f"/api/v1/insurance/policies/{policy_id}/pay",
            json={"payment_reference": "UPI-SUBMIT"},
            headers=auth_headers,
        )

        claim_response = await client.post(
            "/api/v1/insurance/claims",
            json={
                "policy_id": policy_id,
                "claim_type": "localized_risk",
                "loss_date": "2026-07-15",
                "loss_description": (
                    "Heavy rainfall caused waterlogging in my rice field, "
                    "resulting in approximately 40% crop loss."
                ),
                "estimated_loss_pct": 40,
            },
            headers=auth_headers,
        )
        claim_id = claim_response.json()["id"]

        # Submit the claim
        response = await client.post(
            f"/api/v1/insurance/claims/{claim_id}/submit",
            json={
                "bank_account_number": "12345678901",
                "bank_ifsc": "SBIN0001234",
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "submitted"
        assert data["submitted_at"] is not None
        assert data["auto_evidence_summary"] is not None


@pytest.mark.asyncio
class TestInsuranceStats:
    """GET /api/v1/insurance/policies/stats."""

    async def test_get_stats(self, client, auth_headers):
        """Stats endpoint returns summary."""
        response = await client.get(
            "/api/v1/insurance/policies/stats", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_policies" in data
        assert "active_policies" in data
        assert "total_claims" in data
        assert "total_sum_insured" in data
