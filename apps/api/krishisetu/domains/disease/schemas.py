"""Pydantic schemas for the disease domain.

API contracts for:
- Disease catalog (public read)
- Disease report submission (create + get pre-signed upload URL)
- Disease report listing and detail
- Disease prediction response (with treatment recommendations)
- Farmer feedback submission
- Officer review workflow
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Enums (mirrors of model enums)
# ---------------------------------------------------------------------------


class DiseaseSeverityEnum(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class DiseaseReportStatusEnum(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    OFFICER_REVIEW = "officer_review"
    REVIEWED = "reviewed"


class TreatmentTypeEnum(str, Enum):
    ORGANIC = "organic"
    CHEMICAL = "chemical"
    BIOLOGICAL = "biological"
    CULTURAL = "cultural"
    PREVENTIVE = "preventive"


class FeedbackTypeEnum(str, Enum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    PARTIALLY_CORRECT = "partially_correct"


# ---------------------------------------------------------------------------
# Disease catalog schemas (public)
# ---------------------------------------------------------------------------


class DiseaseTreatmentResponse(BaseModel):
    """Treatment recommendation for a disease."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    treatment_type: TreatmentTypeEnum
    description: str
    dosage: str | None
    application_method: str | None
    timing: str | None
    precautions: str | None
    is_primary: bool
    priority: int
    source: str | None


class DiseaseResponse(BaseModel):
    """Disease catalog entry with treatments."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name_en: str
    name_hi: str | None
    scientific_name: str | None
    disease_type: str
    affected_crops: list[str]
    default_severity: DiseaseSeverityEnum
    symptoms: str
    cause: str
    spread_mechanism: str | None
    favorable_conditions: str | None
    prevention_measures: str | None
    treatments: list[DiseaseTreatmentResponse] = Field(default_factory=list)


class DiseaseListItemResponse(BaseModel):
    """Compact disease representation for list views."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name_en: str
    name_hi: str | None
    disease_type: str
    affected_crops: list[str]
    default_severity: DiseaseSeverityEnum


class DiseaseListResponse(BaseModel):
    """Paginated disease catalog response."""

    diseases: list[DiseaseListItemResponse]
    total: int


# ---------------------------------------------------------------------------
# Disease report schemas (farmer-facing)
# ---------------------------------------------------------------------------


class DiseaseReportCreate(BaseModel):
    """Request body for POST /disease-reports.

    The farmer first requests a pre-signed upload URL (GET /disease-reports/upload-url),
    uploads the image directly to S3, then creates the report with the S3 key.
    """

    plot_id: UUID | None = Field(
        default=None,
        description="Plot where the affected crop is growing (optional but recommended)",
    )
    crop_cycle_id: UUID | None = Field(
        default=None,
        description="Specific crop cycle affected (links to insurance claims)",
    )
    image_key: str = Field(
        ...,
        description="S3 object key returned by the upload-url endpoint",
        max_length=512,
    )
    image_content_type: str = Field(
        default="image/jpeg",
        description="MIME type of the uploaded image",
    )
    captured_at: datetime | None = Field(
        default=None,
        description="When the photo was taken (from EXIF if available)",
    )
    farmer_notes: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional farmer description of symptoms observed",
    )


class UploadUrlRequest(BaseModel):
    """Request body for POST /disease-reports/upload-url."""

    content_type: Literal["image/jpeg", "image/png", "image/webp"] = Field(
        default="image/jpeg",
        description="MIME type of the image you will upload",
    )


class UploadUrlResponse(BaseModel):
    """Response with pre-signed S3 upload URL."""

    upload_url: str = Field(..., description="Pre-signed S3 URL — PUT your image here")
    image_key: str = Field(..., description="S3 object key to use when creating the report")
    expires_in_seconds: int = Field(..., description="URL validity duration")
    max_size_bytes: int = Field(
        default=10 * 1024 * 1024,
        description="Maximum image size in bytes (10MB)",
    )


class DiseaseReportResponse(BaseModel):
    """Disease report with prediction (if available)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    farmer_id: UUID
    plot_id: UUID | None
    crop_cycle_id: UUID | None
    image_url: str = Field(..., description="Pre-signed download URL (15-min validity)")
    captured_at: datetime | None
    submitted_at: datetime
    farmer_notes: str | None
    status: DiseaseReportStatusEnum
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime
    prediction: "DiseasePredictionResponse | None" = None


class DiseasePredictionResponse(BaseModel):
    """ML prediction with treatment recommendations."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    disease_slug: str
    confidence: Decimal
    all_predictions: list[dict[str, object]]
    model_name: str
    model_version: str
    inference_time_ms: int
    is_reliable: bool
    inferred_at: datetime
    # Joined disease info (optional — only if disease exists in catalog)
    disease: "DiseaseResponse | None" = None
    # Treatment recommendations (joined from disease_treatments)
    treatments: list[DiseaseTreatmentResponse] = Field(default_factory=list)


# Resolve forward references
DiseaseReportResponse.model_rebuild()
DiseasePredictionResponse.model_rebuild()


class DiseaseReportListResponse(BaseModel):
    """Paginated disease report listing."""

    reports: list[DiseaseReportResponse]
    total: int
    page: int
    page_size: int
    has_more: bool


# ---------------------------------------------------------------------------
# Feedback schemas
# ---------------------------------------------------------------------------


class DiseaseFeedbackCreate(BaseModel):
    """Request body for POST /disease-reports/{id}/feedback."""

    feedback_type: FeedbackTypeEnum
    suggested_disease_slug: str | None = Field(
        default=None,
        max_length=100,
        description="If feedback_type=incorrect, the actual disease slug (must exist in catalog)",
    )
    notes: str | None = Field(default=None, max_length=1000)


class DiseaseFeedbackResponse(BaseModel):
    """Feedback response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    report_id: UUID
    feedback_type: FeedbackTypeEnum
    suggested_disease_slug: str | None
    notes: str | None
    created_at: datetime


# ---------------------------------------------------------------------------
# Officer review schemas
# ---------------------------------------------------------------------------


class OfficerReviewRequest(BaseModel):
    """Request body for PATCH /officer/disease-reports/{id}/review."""

    diagnosis: str = Field(..., min_length=10, max_length=2000)
    disease_slug: str | None = Field(
        default=None,
        max_length=100,
        description="Officer's confirmed disease slug (must exist in catalog)",
    )


class DiseaseReportStatsResponse(BaseModel):
    """Stats for the farmer's disease reports."""

    total_reports: int
    completed: int
    pending: int
    failed: int
    needs_review: int
    by_disease: dict[str, int] = Field(
        default_factory=dict,
        description="Counts by disease_slug for completed reports",
    )
