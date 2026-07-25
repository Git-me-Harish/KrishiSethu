"""Pydantic schemas for the identity domain.

These schemas serve three purposes:
1. Validate request bodies on incoming API calls (FastAPI auto-validates)
2. Shape response bodies on outgoing API calls (FastAPI auto-serializes)
3. Generate OpenAPI documentation (FastAPI auto-generates from these)

Naming convention:
- `*Create`  — schema for creating a resource (POST body)
- `*Update`  — schema for partial update (PATCH body)
- `*Response`— schema for API response
- `*Public`  — schema for public-facing data (no sensitive fields)
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from krishisetu.domains.identity.models import UserRole


# ---------------------------------------------------------------------------
# Auth request schemas
# ---------------------------------------------------------------------------


class SendOTPRequest(BaseModel):
    """Request body for POST /auth/send-otp."""

    phone: str = Field(
        ...,
        description="Indian mobile number (10 digits, or with +91/91 prefix)",
        examples=["9876543210", "+919876543210"],
    )
    purpose: Literal["signup", "login", "phone_change"] = Field(
        default="login",
        description="Purpose of the OTP — affects rate limits and routing",
    )

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        from krishisetu.core.security import normalize_indian_phone

        return normalize_indian_phone(v)


class VerifyOTPRequest(BaseModel):
    """Request body for POST /auth/verify-otp."""

    phone: str = Field(..., description="10-digit Indian mobile number")
    otp: str = Field(
        ...,
        min_length=6,
        max_length=6,
        pattern=r"^\d{6}$",
        description="6-digit OTP received via SMS",
    )
    full_name: str | None = Field(
        default=None,
        min_length=2,
        max_length=255,
        description="Required for signup (new user). Ignored for login.",
    )
    preferred_language: str = Field(
        default="en",
        max_length=5,
        description="Preferred UI language code (en, hi, mr, ta, te, bn, kn, gu, pa, ml)",
    )

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        from krishisetu.core.security import normalize_indian_phone

        return normalize_indian_phone(v)

    @field_validator("preferred_language")
    @classmethod
    def validate_language(cls, v: str) -> str:
        allowed = {"en", "hi", "mr", "ta", "te", "bn", "kn", "gu", "pa", "ml"}
        if v not in allowed:
            raise ValueError(f"Language must be one of: {', '.join(sorted(allowed))}")
        return v


class RefreshTokenRequest(BaseModel):
    """Request body for POST /auth/refresh."""

    refresh_token: str = Field(..., description="Refresh token issued at login")


class LogoutRequest(BaseModel):
    """Request body for POST /auth/logout."""

    refresh_token: str = Field(..., description="Refresh token to revoke")


# ---------------------------------------------------------------------------
# Auth response schemas
# ---------------------------------------------------------------------------


class TokenResponse(BaseModel):
    """Response for successful authentication (login, signup, refresh)."""

    access_token: str = Field(..., description="Short-lived JWT access token (30 min)")
    refresh_token: str = Field(..., description="Long-lived JWT refresh token (30 days)")
    token_type: Literal["bearer"] = "bearer"
    expires_in: int = Field(
        ...,
        description="Access token expiration in seconds (from now)",
    )
    user: "UserPublic"


class UserPublic(BaseModel):
    """Public-facing user representation (no sensitive fields).

    Returned in auth responses, /me endpoint, and admin user listings.
    Never includes password_hash, aadhaar_hash, or failed_login_count.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    phone: str
    phone_verified: bool
    email: str | None = None
    email_verified: bool
    aadhaar_verified: bool
    full_name: str
    role: UserRole
    is_active: bool
    preferred_language: str
    last_login_at: datetime | None = None
    created_at: datetime


# Resolve forward reference (UserPublic referenced in TokenResponse)
TokenResponse.model_rebuild()


# ---------------------------------------------------------------------------
# Error response schemas
# ---------------------------------------------------------------------------


class AuthErrorResponse(BaseModel):
    """Standard error response for auth endpoints."""

    error: dict[str, object] = Field(
        ...,
        description="Error details including code, message, and request_id",
    )


# ---------------------------------------------------------------------------
# Admin schemas (for /admin/users endpoints)
# ---------------------------------------------------------------------------


class AdminUserUpdate(BaseModel):
    """Schema for admin updating a user (role, active status)."""

    role: UserRole | None = None
    is_active: bool | None = None
    full_name: str | None = Field(default=None, min_length=2, max_length=255)


class AdminUserListResponse(BaseModel):
    """Paginated response for admin user listing."""

    users: list[UserPublic]
    total: int
    page: int
    page_size: int
    has_more: bool
