"""Integration tests for the auth flow.

These tests exercise the full HTTP stack: FastAPI route → service → repository → DB.
They use the test database (with rollback isolation) and mocked Redis/SMS.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
class TestSendOTPEndpoint:
    """POST /api/v1/auth/send-otp"""

    async def test_send_otp_for_login_returns_202(
        self, client, redis_mock, sms_mock
    ):
        """Sending OTP for login purpose returns 202 with metadata."""
        response = await client.post(
            "/api/v1/auth/send-otp",
            json={"phone": "9876543210", "purpose": "login"},
        )
        assert response.status_code == 202
        data = response.json()
        assert data["phone"] == "9876543210"
        assert data["purpose"] == "login"
        assert data["ttl_seconds"] == 300
        assert data["cooldown_seconds"] == 60
        assert data["max_attempts"] == 3

    async def test_send_otp_for_signup_returns_202(
        self, client, redis_mock, sms_mock
    ):
        """Sending OTP for signup returns 202 (phone not yet registered)."""
        response = await client.post(
            "/api/v1/auth/send-otp",
            json={"phone": "9876543210", "purpose": "signup"},
        )
        assert response.status_code == 202

    async def test_send_otp_normalizes_phone_with_country_code(
        self, client, redis_mock, sms_mock
    ):
        """Phone numbers with +91 prefix are normalized to 10 digits."""
        response = await client.post(
            "/api/v1/auth/send-otp",
            json={"phone": "+919876543210", "purpose": "login"},
        )
        assert response.status_code == 202
        assert response.json()["phone"] == "9876543210"

    async def test_send_otp_rejects_invalid_phone(
        self, client, redis_mock, sms_mock
    ):
        """Invalid phone format returns 422."""
        response = await client.post(
            "/api/v1/auth/send-otp",
            json={"phone": "12345", "purpose": "login"},
        )
        assert response.status_code == 422

    async def test_send_otp_cooldown_enforced(
        self, client, redis_mock, sms_mock
    ):
        """Sending OTP twice within cooldown returns 429."""
        # First send succeeds
        r1 = await client.post(
            "/api/v1/auth/send-otp",
            json={"phone": "9876543210", "purpose": "login"},
        )
        assert r1.status_code == 202

        # Second send within cooldown is rate-limited
        r2 = await client.post(
            "/api/v1/auth/send-otp",
            json={"phone": "9876543210", "purpose": "login"},
        )
        assert r2.status_code == 429
        assert "Retry-After" in r2.headers


@pytest.mark.asyncio
class TestVerifyOTPSignupFlow:
    """POST /api/v1/auth/verify-otp — new user signup"""

    async def test_signup_creates_new_user_and_returns_tokens(
        self, client, db_session, redis_mock, sms_mock
    ):
        """Verifying OTP for a new phone number creates a user and returns tokens."""
        # Send OTP first
        await client.post(
            "/api/v1/auth/send-otp",
            json={"phone": "9876543210", "purpose": "signup"},
        )

        # Get the OTP from the SMS mock
        otp = sms_mock.last_otp("9876543210", "signup")
        assert otp is not None

        # Verify OTP with signup data
        response = await client.post(
            "/api/v1/auth/verify-otp",
            json={
                "phone": "9876543210",
                "otp": otp,
                "full_name": "New Farmer",
                "preferred_language": "hi",
            },
        )
        assert response.status_code == 200
        data = response.json()

        # Token response structure
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] > 0

        # User info
        user = data["user"]
        assert user["phone"] == "9876543210"
        assert user["full_name"] == "New Farmer"
        assert user["role"] == "farmer"
        assert user["preferred_language"] == "hi"
        assert user["phone_verified"] is True
        assert user["aadhaar_verified"] is False

    async def test_signup_without_full_name_fails(
        self, client, redis_mock, sms_mock
    ):
        """Verifying OTP for a new user without full_name returns 422."""
        await client.post(
            "/api/v1/auth/send-otp",
            json={"phone": "9876543210", "purpose": "signup"},
        )
        otp = sms_mock.last_otp("9876543210", "signup")

        response = await client.post(
            "/api/v1/auth/verify-otp",
            json={"phone": "9876543210", "otp": otp},
        )
        assert response.status_code == 422

    async def test_signup_with_existing_phone_returns_409(
        self, client, test_user, redis_mock, sms_mock
    ):
        """Signup with an already-registered phone returns 409."""
        response = await client.post(
            "/api/v1/auth/send-otp",
            json={"phone": "9876543210", "purpose": "signup"},
        )
        assert response.status_code == 409


@pytest.mark.asyncio
class TestVerifyOTPLoginFlow:
    """POST /api/v1/auth/verify-otp — existing user login"""

    async def test_login_returns_tokens_for_existing_user(
        self, client, test_user, redis_mock, sms_mock
    ):
        """Verifying OTP for an existing user logs them in."""
        # test_user fixture created with phone 9876543210
        await client.post(
            "/api/v1/auth/send-otp",
            json={"phone": "9876543210", "purpose": "login"},
        )
        otp = sms_mock.last_otp("9876543210", "login")

        response = await client.post(
            "/api/v1/auth/verify-otp",
            json={"phone": "9876543210", "otp": otp},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["user"]["phone"] == "9876543210"
        assert data["user"]["full_name"] == "Test Farmer"

    async def test_login_with_wrong_otp_returns_422(
        self, client, test_user, redis_mock, sms_mock
    ):
        """Verifying a wrong OTP returns 422 with attempt count."""
        await client.post(
            "/api/v1/auth/send-otp",
            json={"phone": "9876543210", "purpose": "login"},
        )

        response = await client.post(
            "/api/v1/auth/verify-otp",
            json={"phone": "9876543210", "otp": "000000"},
        )
        assert response.status_code == 422

    async def test_login_with_expired_otp_returns_422(
        self, client, redis_mock, sms_mock
    ):
        """Verifying without a prior OTP request returns 422."""
        response = await client.post(
            "/api/v1/auth/verify-otp",
            json={"phone": "9999999999", "otp": "123456"},
        )
        assert response.status_code == 422


@pytest.mark.asyncio
class TestRefreshTokenFlow:
    """POST /api/v1/auth/refresh — token rotation"""

    async def test_refresh_returns_new_token_pair(
        self, client, test_user, redis_mock, sms_mock
    ):
        """Refreshing a valid token returns a new access + refresh pair."""
        # Login first
        await client.post(
            "/api/v1/auth/send-otp",
            json={"phone": "9876543210", "purpose": "login"},
        )
        otp = sms_mock.last_otp("9876543210", "login")
        login_response = await client.post(
            "/api/v1/auth/verify-otp",
            json={"phone": "9876543210", "otp": otp},
        )
        refresh_token = login_response.json()["refresh_token"]

        # Refresh
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert response.status_code == 200
        new_tokens = response.json()
        assert new_tokens["access_token"] != login_response.json()["access_token"]
        assert new_tokens["refresh_token"] != refresh_token

    async def test_refresh_with_revoked_token_returns_401(
        self, client, test_user, redis_mock, sms_mock
    ):
        """Using an already-refreshed token returns 401 (rotation detected)."""
        # Login
        await client.post(
            "/api/v1/auth/send-otp",
            json={"phone": "9876543210", "purpose": "login"},
        )
        otp = sms_mock.last_otp("9876543210", "login")
        login_response = await client.post(
            "/api/v1/auth/verify-otp",
            json={"phone": "9876543210", "otp": otp},
        )
        original_refresh = login_response.json()["refresh_token"]

        # First refresh succeeds
        await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": original_refresh},
        )

        # Second use of the same (now-revoked) token fails
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": original_refresh},
        )
        assert response.status_code == 401


@pytest.mark.asyncio
class TestLogoutFlow:
    """POST /api/v1/auth/logout"""

    async def test_logout_revokes_refresh_token(
        self, client, test_user, redis_mock, sms_mock
    ):
        """Logout revokes the refresh token so it can no longer be used."""
        # Login
        await client.post(
            "/api/v1/auth/send-otp",
            json={"phone": "9876543210", "purpose": "login"},
        )
        otp = sms_mock.last_otp("9876543210", "login")
        login_response = await client.post(
            "/api/v1/auth/verify-otp",
            json={"phone": "9876543210", "otp": otp},
        )
        refresh_token = login_response.json()["refresh_token"]

        # Logout
        logout_response = await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": refresh_token},
        )
        assert logout_response.status_code == 204

        # Refresh should now fail
        refresh_response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert refresh_response.status_code == 401


@pytest.mark.asyncio
class TestMeEndpoint:
    """GET /api/v1/me and PATCH /api/v1/me"""

    async def test_get_me_without_token_returns_401(self, client):
        """Accessing /me without auth returns 401."""
        response = await client.get("/api/v1/me")
        assert response.status_code in (401, 403)

    async def test_get_me_with_valid_token_returns_user(
        self, client, auth_headers, test_user
    ):
        """Accessing /me with a valid token returns the user."""
        response = await client.get("/api/v1/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_user.id)
        assert data["phone"] == test_user.phone

    async def test_update_me_changes_name(
        self, client, auth_headers, test_user, db_session
    ):
        """PATCH /me updates the user's name."""
        response = await client.patch(
            "/api/v1/me",
            json={"full_name": "Updated Name"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["full_name"] == "Updated Name"

    async def test_update_me_invalid_language_returns_422(
        self, client, auth_headers
    ):
        """PATCH /me with invalid language returns 422."""
        response = await client.patch(
            "/api/v1/me",
            json={"preferred_language": "invalid"},
            headers=auth_headers,
        )
        assert response.status_code == 422


@pytest.mark.asyncio
class TestHealthEndpoint:
    """Sanity check — health endpoints should work even without auth."""

    async def test_liveness_returns_200(self, client):
        response = await client.get("/api/v1/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "alive"
        assert "version" in data

    async def test_readiness_returns_200_with_checks(self, client):
        response = await client.get("/api/v1/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert "checks" in data
        # database and redis should be in checks
        assert "database" in data["checks"]
        assert "redis" in data["checks"]
