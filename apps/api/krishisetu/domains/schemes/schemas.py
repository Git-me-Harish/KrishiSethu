"""Pydantic schemas for the schemes domain."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SchemeCategoryEnum(str, Enum):
    INCOME_SUPPORT = "income_support"
    CROP_INSURANCE = "crop_insurance"
    CREDIT = "credit"
    INPUT_SUBSIDY = "input_subsidy"
    EQUIPMENT_SUBSIDY = "equipment_subsidy"
    IRRIGATION = "irrigation"
    SOIL_HEALTH = "soil_health"
    MARKET_SUPPORT = "market_support"
    PENSION = "pension"
    OTHER = "other"


class ApplicationStatusEnum(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    RESUBMISSION_REQUESTED = "resubmission_requested"
    WITHDRAWN = "withdrawn"
    BENEFIT_DISBURSED = "benefit_disbursed"


# ---------------------------------------------------------------------------
# Scheme catalog response
# ---------------------------------------------------------------------------


class SchemeResponse(BaseModel):
    """Government scheme with eligibility info."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    code: str
    name: str
    name_hi: str | None
    short_description: str
    full_description: str
    category: str
    level: str
    ministry: str | None
    states: list[str] | None
    benefit_type: str | None
    benefit_amount: Decimal | None
    benefit_frequency: str | None
    benefit_description: str | None
    application_mode: str
    documents_required: list[str] | None
    application_url: str | None
    source_url: str | None
    helpline_number: str | None
    is_featured: bool
    # Eligibility result (only if checked for current user)
    is_eligible: bool | None = None
    eligibility_reasons: list[str] | None = None
    has_applied: bool = False
    application_status: str | None = None


class SchemeListResponse(BaseModel):
    schemes: list[SchemeResponse]
    total: int
    eligible_count: int | None = None


# ---------------------------------------------------------------------------
# Application schemas
# ---------------------------------------------------------------------------


class SchemeApplicationCreate(BaseModel):
    """Request body for creating a scheme application."""

    scheme_id: UUID
    additional_data: dict | None = Field(
        default=None,
        description="Application-specific fields (e.g., crop_name, area, bank_details)",
    )


class SchemeApplicationResponse(BaseModel):
    """Scheme application with scheme info."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    application_number: str
    scheme_id: UUID
    farmer_id: UUID
    status: ApplicationStatusEnum
    submitted_data: dict
    eligibility_result: dict | None
    submitted_documents: list[str] | None
    reviewed_by: UUID | None
    reviewed_at: datetime | None
    review_notes: str | None
    rejection_reason: str | None
    benefit_disbursed_at: datetime | None
    benefit_reference: str | None
    submitted_at: datetime | None
    created_at: datetime
    updated_at: datetime
    # Joined scheme info
    scheme_name: str | None = None
    scheme_code: str | None = None


class SchemeApplicationListResponse(BaseModel):
    applications: list[SchemeApplicationResponse]
    total: int


class SchemeApplicationSubmit(BaseModel):
    """Request body for submitting a draft application."""

    additional_data: dict | None = None
    submitted_documents: list[str] | None = None


class OfficerReviewRequest(BaseModel):
    """Request body for officer reviewing a scheme application."""

    action: str = Field(..., description="approve, reject, request_resubmission")
    review_notes: str | None = Field(default=None, max_length=5000)
    rejection_reason: str | None = Field(default=None, max_length=5000)
    benefit_reference: str | None = Field(default=None, max_length=100)


class SchemeStatsResponse(BaseModel):
    """Stats for farmer's scheme applications."""

    total_schemes_available: int
    eligible_schemes: int
    total_applications: int
    pending_applications: int
    approved_applications: int
