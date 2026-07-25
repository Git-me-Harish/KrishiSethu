"""Unit tests for krishisetu.core.security.

These tests don't require a database — they test pure functions.
"""

from __future__ import annotations

import pytest
from krishisetu.core.exceptions import AuthenticationError
from krishisetu.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_otp,
    hash_password,
    normalize_indian_phone,
    validate_aadhaar,
    verify_password,
)


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------


class TestPasswordHashing:
    def test_hash_and_verify_roundtrip(self):
        """A password verifies against its hash."""
        password = "mySecretPassword123!"
        hashed = hash_password(password)
        assert hashed != password
        assert verify_password(password, hashed) is True

    def test_wrong_password_fails(self):
        """A wrong password does not verify."""
        hashed = hash_password("correctPassword123")
        assert verify_password("wrongPassword", hashed) is False

    def test_hash_is_unique_per_call(self):
        """Same password produces different hashes (bcrypt salt)."""
        h1 = hash_password("samePassword123")
        h2 = hash_password("samePassword123")
        assert h1 != h2

    def test_short_password_rejected(self):
        """Passwords shorter than 8 characters are rejected."""
        with pytest.raises(ValueError, match="at least 8"):
            hash_password("short")


# ---------------------------------------------------------------------------
# OTP generation
# ---------------------------------------------------------------------------


class TestOTPGeneration:
    def test_otp_is_6_digits(self):
        otp = generate_otp(length=6)
        assert len(otp) == 6
        assert otp.isdigit()

    def test_otp_is_random(self):
        """Two consecutive OTPs are (almost certainly) different."""
        otps = {generate_otp() for _ in range(100)}
        # With 10^6 possible 6-digit OTPs, 100 samples should have very few
        # collisions. Just verify we have at least 90 unique values.
        assert len(otps) >= 90

    def test_otp_within_range(self):
        """OTP is between 000000 and 999999."""
        for _ in range(1000):
            otp = generate_otp(length=6)
            assert 0 <= int(otp) <= 999999

    def test_invalid_length_rejected(self):
        with pytest.raises(ValueError):
            generate_otp(length=3)
        with pytest.raises(ValueError):
            generate_otp(length=10)


# ---------------------------------------------------------------------------
# JWT tokens
# ---------------------------------------------------------------------------


class TestJWTTokens:
    def test_access_token_roundtrip(self):
        """An access token decodes back to the original claims."""
        token = create_access_token(
            user_id="123e4567-e89b-12d3-a456-426614174000",
            role="farmer",
            extra_claims={"name": "Test User"},
        )
        payload = decode_token(token, expected_type="access")
        assert payload["sub"] == "123e4567-e89b-12d3-a456-426614174000"
        assert payload["role"] == "farmer"
        assert payload["type"] == "access"
        assert payload["name"] == "Test User"

    def test_refresh_token_has_jti(self):
        """Refresh tokens carry a unique jti for revocation."""
        token, jti = create_refresh_token("user-id-123")
        payload = decode_token(token, expected_type="refresh")
        assert payload["jti"] == jti
        assert len(jti) > 20  # jti is a 32-byte URL-safe string

    def test_token_type_mismatch_rejected(self):
        """Using an access token where refresh is expected fails."""
        token = create_access_token(user_id="uid", role="farmer")
        with pytest.raises(AuthenticationError, match="Expected refresh token"):
            decode_token(token, expected_type="refresh")

    def test_malformed_token_rejected(self):
        """A malformed token raises AuthenticationError."""
        with pytest.raises(AuthenticationError):
            decode_token("not.a.valid.jwt", expected_type="access")

    def test_refresh_token_rotation_produces_unique_jtis(self):
        """Each call to create_refresh_token produces a unique jti."""
        jtis = set()
        for _ in range(50):
            _, jti = create_refresh_token("uid")
            jtis.add(jti)
        assert len(jtis) == 50


# ---------------------------------------------------------------------------
# Phone normalization
# ---------------------------------------------------------------------------


class TestPhoneNormalization:
    @pytest.mark.parametrize(
        "input_phone,expected",
        [
            ("9876543210", "9876543210"),
            ("+919876543210", "9876543210"),
            ("919876543210", "9876543210"),
            ("09876543210", "9876543210"),
            ("+91 98765 43210", "9876543210"),
            ("+91-98765-43210", "9876543210"),
            (" 9876543210 ", "9876543210"),
        ],
    )
    def test_valid_normalization(self, input_phone: str, expected: str):
        assert normalize_indian_phone(input_phone) == expected

    @pytest.mark.parametrize(
        "invalid_phone",
        [
            "1234567890",  # Starts with 1 (invalid for Indian mobile)
            "5676543210",  # Starts with 5
            "98765432",     # Too short
            "98765432101",  # Too long (no country code)
            "abcdefghij",   # Non-numeric
        ],
    )
    def test_invalid_rejected(self, invalid_phone: str):
        with pytest.raises(ValueError):
            normalize_indian_phone(invalid_phone)


# ---------------------------------------------------------------------------
# Aadhaar validation (Verhoeff checksum)
# ---------------------------------------------------------------------------


class TestAadhaarValidation:
    def test_valid_aadhaar_accepted(self):
        """A known-valid Aadhaar number passes Verhoeff check.

        Source: UIDAI sample Aadhaar numbers used in test environments.
        """
        # This is a sample Aadhaar number with valid Verhoeff checksum
        # (not a real person's number — used in UIDAI test data)
        valid = "234123412346"
        result = validate_aadhaar(valid)
        assert result == valid

    def test_invalid_checksum_rejected(self):
        """A number with wrong checksum is rejected."""
        with pytest.raises(ValueError, match="Verhoeff"):
            validate_aadhaar("234123412341")  # Last digit changed

    def test_wrong_length_rejected(self):
        with pytest.raises(ValueError, match="12 digits"):
            validate_aadhaar("1234567890")

    def test_leading_zero_rejected(self):
        with pytest.raises(ValueError, match="cannot start with 0"):
            validate_aadhaar("012345678901")

    def test_strips_non_digits(self):
        """Aadhaar with spaces or dashes is normalized."""
        result = validate_aadhaar("2341 2341 2346")
        assert result == "234123412346"
