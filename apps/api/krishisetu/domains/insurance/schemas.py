"""Pydantic schemas for the insurance domain."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class InsuranceProductTypeEnum(str, Enum):
    PMFBY = "pmfby"
    RWBCIS = "rwbcis"
    STATE_SCHEME = "state_scheme"
    COMMERCIAL = "commercial"


class ClaimTypeEnum(str, Enum):
    LOCALIZED_RISK = "localized_risk"
    WIDESPREAD_RISK = "widespread_risk"
    PREVENTIVE_SOWING = "preventive_sowing"
    POST_HARVEST = "post_harvest"
    MID_SEASON_ADVERSITY = "mid_season_adversity"


class ClaimStatusEnum(str, Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    EVIDENCE_REQUESTED = "evidence_requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    PAYOUT_DISBURSED = "payout_disbursed"
    WITHDRAWN = "withdrawn"


class PolicyStatusEnum(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class EvidenceTypeEnum(str, Enum):
    NDVI_DROP = "ndvi_drop"
    DISEASE_REPORT = "disease_report"
    WEATHER_ALERT = "weather_alert"
    OFFICER_INSPECTION = "officer_inspection"
    PHOTO_EVIDENCE = "photo_evidence"
    YIELD_DATA = "yield_data"
    BANK_DOCUMENT = "bank_document"


# ---------------------------------------------------------------------------
# Insurance Product schemas
# ---------------------------------------------------------------------------


class InsuranceProductResponse(BaseModel):
    """Insurance product catalog entry."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    name: str
    product_type: InsuranceProductTypeEnum
    insurer_name: str
    crop_slug: str
    crop_name: str
    season: str
    season_year: int
    state: str
    district: str | None
    sum_insured_per_ha: Decimal
    farmer_premium_rate: Decimal
    farmer_premium_min: Decimal | None
    farmer_premium_max: Decimal | None
    coverage_start_date: date
    coverage_end_date: date
    claim_cutoff_yield: Decimal | None
    description: str | None
    is_active: bool


class InsuranceProductListResponse(BaseModel):
    """Paginated product listing."""

    products: list[InsuranceProductResponse]
    total: int


class InsuranceProductPremiumEstimate(BaseModel):
    """Premium estimate for a specific plot."""

    product_id: UUID
    plot_id: UUID
    area_ha: Decimal
    sum_insured: Decimal
    premium_amount: Decimal
    premium_rate: Decimal
    farmer_premium_rate_pct: float  # e.g., 2.0 for 2%


# ---------------------------------------------------------------------------
# Insurance Policy schemas
# ---------------------------------------------------------------------------


class PolicyCreateRequest(BaseModel):
    """Request body for enrolling in an insurance policy."""

    product_id: UUID
    plot_id: UUID
    crop_cycle_id: UUID | None = None
    bank_account_number: str | None = Field(default=None, min_length=8, max_length=30)
    bank_ifsc: str | None = Field(default=None, min_length=8, max_length=15)

    @model_validator(mode="after")
    def validate_bank_details(self) -> PolicyCreateRequest:
        """Bank account and IFSC must be provided together (or both omitted)."""
        if (self.bank_account_number is None) != (self.bank_ifsc is None):
            raise ValueError(
                "Both bank_account_number and bank_ifsc must be provided together "
                "(or both omitted for later entry)"
            )
        return self


class PolicyResponse(BaseModel):
    """Insurance policy with computed fields."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    policy_number: str
    product_id: UUID
    farmer_id: UUID
    plot_id: UUID
    crop_cycle_id: UUID | None
    sum_insured: Decimal
    area_insured_ha: Decimal
    premium_amount: Decimal
    premium_rate: Decimal
    premium_paid: bool
    premium_paid_at: datetime | None
    payment_reference: str | None
    coverage_start_date: date
    coverage_end_date: date
    status: PolicyStatusEnum
    bank_account_number: str | None
    bank_ifsc: str | None
    created_at: datetime
    updated_at: datetime
    # Joined product info
    product: InsuranceProductResponse | None = None
    # Claim count
    active_claims_count: int = 0


class PolicyListResponse(BaseModel):
    """Paginated policy listing."""

    policies: list[PolicyResponse]
    total: int


class PolicyPremiumPaymentRequest(BaseModel):
    """Request body for marking premium as paid (stub for payment gateway)."""

    payment_reference: str = Field(..., min_length=5, max_length=100)


# ---------------------------------------------------------------------------
# Insurance Claim schemas
# ---------------------------------------------------------------------------


class ClaimCreateRequest(BaseModel):
    """Request body for creating a new insurance claim (draft)."""

    policy_id: UUID
    claim_type: ClaimTypeEnum
    loss_date: date
    loss_description: str = Field(..., min_length=20, max_length=5000)
    estimated_loss_pct: Decimal = Field(..., ge=0, le=100)
    bank_account_number: str | None = Field(default=None, min_length=8, max_length=30)
    bank_ifsc: str | None = Field(default=None, min_length=8, max_length=15)


class ClaimUpdateRequest(BaseModel):
    """Request body for updating a draft claim."""

    claim_type: ClaimTypeEnum | None = None
    loss_date: date | None = None
    loss_description: str | None = Field(default=None, min_length=20, max_length=5000)
    estimated_loss_pct: Decimal | None = Field(default=None, ge=0, le=100)


class ClaimSubmitRequest(BaseModel):
    """Request body for submitting a draft claim."""

    bank_account_number: str = Field(..., min_length=8, max_length=30)
    bank_ifsc: str = Field(..., min_length=8, max_length=15)


class ClaimEvidenceResponse(BaseModel):
    """Evidence attached to a claim."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    claim_id: UUID
    evidence_type: EvidenceTypeEnum
    source_module: str
    source_id: UUID | None
    title: str
    description: str
    evidence_date: datetime
    snapshot_data: dict | None
    file_url: str | None
    is_auto_attached: bool
    file_download_url: str | None = None
    created_at: datetime


class ClaimResponse(BaseModel):
    """Insurance claim with evidence."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    claim_number: str
    policy_id: UUID
    farmer_id: UUID
    claim_type: ClaimTypeEnum
    status: ClaimStatusEnum
    loss_date: date
    loss_description: str
    estimated_loss_pct: Decimal
    claimed_amount: Decimal
    approved_amount: Decimal | None
    payout_transaction_id: str | None
    payout_date: datetime | None
    reviewed_by: UUID | None
    reviewed_at: datetime | None
    review_notes: str | None
    rejection_reason: str | None
    auto_evidence_summary: dict | None
    submitted_at: datetime | None
    created_at: datetime
    updated_at: datetime
    # Joined evidence
    evidence: list[ClaimEvidenceResponse] = Field(default_factory=list)
    # Joined policy info
    policy: PolicyResponse | None = None


class ClaimListResponse(BaseModel):
    """Paginated claim listing."""

    claims: list[ClaimResponse]
    total: int


# ---------------------------------------------------------------------------
# Insurer review schemas
# ---------------------------------------------------------------------------


class InsurerReviewRequest(BaseModel):
    """Request body for insurer to review a claim."""

    action: str = Field(..., description="approve, reject, request_evidence")
    approved_amount: Decimal | None = Field(
        default=None, ge=0, description="Required if action=approve"
    )
    review_notes: str | None = Field(default=None, max_length=5000)
    rejection_reason: str | None = Field(default=None, max_length=5000)
    evidence_request_notes: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def validate_action(self) -> InsurerReviewRequest:
        if self.action not in ("approve", "reject", "request_evidence"):
            raise ValueError("action must be one of: approve, reject, request_evidence")
        if self.action == "approve" and self.approved_amount is None:
            raise ValueError("approved_amount is required when action=approve")
        if self.action == "reject" and not self.rejection_reason:
            raise ValueError("rejection_reason is required when action=reject")
        if self.action == "request_evidence" and not self.evidence_request_notes:
            raise ValueError("evidence_request_notes is required when action=request_evidence")
        return self


class InsurerClaimListResponse(BaseModel):
    """Claims assigned to an insurer for review."""

    claims: list[ClaimResponse]
    total: int


# ---------------------------------------------------------------------------
# Insurance stats
# ---------------------------------------------------------------------------


class InsuranceStatsResponse(BaseModel):
    """Summary stats for farmer's insurance."""

    total_policies: int
    active_policies: int
    expired_policies: int
    total_sum_insured: Decimal
    total_premium_paid: Decimal
    total_claims: int
    pending_claims: int
    approved_claims: int
    total_claimed_amount: Decimal
    total_approved_amount: Decimal
