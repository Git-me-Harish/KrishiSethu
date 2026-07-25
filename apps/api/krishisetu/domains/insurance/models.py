"""SQLAlchemy ORM models for the insurance domain.

Tables:
- insurance.insurance_products    (catalog: PMFBY and state schemes per crop/season)
- insurance.insurance_policies    (farmer's purchased policies, linked to plot+crop)
- insurance.insurance_claims      (filed claims with status workflow)
- insurance.claim_evidence        (auto-attached NDVI/disease/weather evidence)

Design notes:
- Products are season-specific (Kharif 2026, Rabi 2026-27) — farmers buy
  insurance for a specific season's crop
- Policies link to a plot AND a crop cycle (the specific crop being insured)
- Claims can be triggered by: localized risk (farmer's plot), widespread risk
  (district-level yield shortfall), or preventive sowing failure
- Evidence is auto-aggregated from other modules — the farmer doesn't need
  to manually attach NDVI/disease data; the platform compiles it automatically
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from krishisetu.core.database import Base


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class InsuranceProductType(str, Enum):
    """Type of crop insurance product."""

    PMFBY = "pmfby"                  # Pradhan Mantri Fasal Bima Yojana
    RWBCIS = "rwbcis"                # Restructured Weather Based Crop Insurance
    STATE_SCHEME = "state_scheme"    # State-specific scheme
    COMMERCIAL = "commercial"        # Private commercial insurance


class ClaimType(str, Enum):
    """Type of insurance claim."""

    LOCALIZED_RISK = "localized_risk"            # Individual farm loss (hail, pest, etc.)
    WIDESPREAD_RISK = "widespread_risk"           # District-level yield shortfall
    PREVENTIVE_SOWING = "preventive_sowing"       # Sowing failure (no germination)
    POST_HARVEST = "post_harvest"                 # Loss during storage/transport
    MID_SEASON_ADVERSITY = "mid_season_adversity"  # Drought/flood mid-season


class ClaimStatus(str, Enum):
    """Status of an insurance claim (lifecycle)."""

    DRAFT = "draft"                    # Farmer is composing the claim
    SUBMITTED = "submitted"            # Farmer submitted, awaiting insurer review
    UNDER_REVIEW = "under_review"      # Insurer is reviewing
    EVIDENCE_REQUESTED = "evidence_requested"  # Insurer needs more evidence
    APPROVED = "approved"              # Insurer approved the claim
    REJECTED = "rejected"              # Insurer rejected the claim
    PAYOUT_DISBURSED = "payout_disbursed"      # Bank transfer completed
    WITHDRAWN = "withdrawn"            # Farmer withdrew the claim


class PolicyStatus(str, Enum):
    """Status of an insurance policy."""

    PENDING = "pending"            # Enrollment initiated, awaiting premium payment
    ACTIVE = "active"              # Premium paid, policy in effect
    EXPIRED = "expired"            # Season ended, policy no longer valid
    CANCELLED = "cancelled"        # Cancelled by farmer or insurer


class EvidenceType(str, Enum):
    """Type of evidence attached to a claim."""

    NDVI_DROP = "ndvi_drop"                # NDVI anomaly alert
    DISEASE_REPORT = "disease_report"       # Crop disease identification
    WEATHER_ALERT = "weather_alert"         # Extreme weather alert
    OFFICER_INSPECTION = "officer_inspection"  # Agri officer field visit report
    PHOTO_EVIDENCE = "photo_evidence"       # Farmer-uploaded photos
    YIELD_DATA = "yield_data"               # Actual yield vs threshold
    BANK_DOCUMENT = "bank_document"         # Bank account verification


# ---------------------------------------------------------------------------
# InsuranceProduct (catalog)
# ---------------------------------------------------------------------------


class InsuranceProduct(Base):
    """Insurance product catalog entry.

    Each product represents an insurable crop for a specific season in a
    specific state. PMFBY products are defined by the state government and
    empaneled insurers.

    Premium rates are subsidized under PMFBY:
    - Farmers pay: 2% of sum insured (Kharif), 1.5% (Rabi), 5% (commercial/horticultural)
    - Government subsidizes the rest (50% central + state share)
    """

    __tablename__ = "insurance_products"
    __table_args__ = (
        UniqueConstraint(
            "slug", "season", "season_year", "state",
            name="insurance_products_unique"
        ),
        {"schema": "insurance"},
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        server_default=func.gen_random_uuid(),
        primary_key=True,
        nullable=False,
    )
    slug: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True,
        comment="URL-friendly identifier, e.g., 'pmfby-rice-kharif-2026-maharashtra'",
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_type: Mapped[InsuranceProductType] = mapped_column(
        String(30), nullable=False, index=True,
    )
    insurer_name: Mapped[str] = mapped_column(
        String(255), nullable=False,
        comment="Insurance company name, e.g., 'AIC of India', 'ICICI Lombard'",
    )

    # Coverage details
    crop_slug: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True,
        comment="Crop slug (matches farmer.crops.slug)",
    )
    crop_name: Mapped[str] = mapped_column(String(100), nullable=False)
    season: Mapped[str] = mapped_column(
        String(20), nullable=False,
        comment="kharif, rabi, or zaid",
    )
    season_year: Mapped[int] = mapped_column(Integer, nullable=False)

    # Geographic coverage
    state: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    district: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="NULL = all districts in the state",
    )

    # Financial details
    sum_insured_per_ha: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        comment="Maximum payout per hectare (₹/ha)",
    )
    farmer_premium_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        comment="Premium rate as fraction of sum insured (0.02 = 2%)",
    )
    farmer_premium_min: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True,
        comment="Minimum premium amount (₹), if any",
    )
    farmer_premium_max: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True,
        comment="Maximum premium amount (₹), if any",
    )

    # Coverage period
    coverage_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    coverage_end_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Claim triggers
    claim_cutoff_yield: Mapped[Decimal | None] = mapped_column(
        Numeric(8, 2),
        nullable=True,
        comment="Threshold yield (kg/ha) below which widespread risk claim triggers",
    )

    # Metadata
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, server_default=func.text("true"), nullable=False, default=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.NOW(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.NOW(), nullable=False,
    )

    # Relationship
    policies: Mapped[list["InsurancePolicy"]] = relationship(
        "InsurancePolicy", back_populates="product"
    )

    def __repr__(self) -> str:
        return (
            f"<InsuranceProduct slug={self.slug} "
            f"crop={self.crop_slug} season={self.season} {self.season_year}>"
        )


# ---------------------------------------------------------------------------
# InsurancePolicy (farmer's purchased policy)
# ---------------------------------------------------------------------------


class InsurancePolicy(Base):
    """An insurance policy purchased by a farmer for a specific plot+crop.

    Links to:
    - Product (what was purchased)
    - Plot (where the insured crop is growing)
    - Crop cycle (which specific crop rotation is insured)
    - Farmer (who bought it)

    Premium payment status determines whether the policy is ACTIVE.
    """

    __tablename__ = "insurance_policies"
    __table_args__ = (
        UniqueConstraint(
            "policy_number", name="insurance_policies_policy_number_unique"
        ),
        {"schema": "insurance"},
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        server_default=func.gen_random_uuid(),
        primary_key=True,
        nullable=False,
    )
    policy_number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Unique policy number (generated by insurer or platform)",
    )
    product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("insurance.insurance_products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    farmer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("identity.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    plot_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("farmer.plots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    crop_cycle_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("farmer.crop_cycles.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Financial details (snapshot at purchase time — product values may change)
    sum_insured: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        comment="Total sum insured (sum_insured_per_ha × area_ha)",
    )
    area_insured_ha: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), nullable=False,
    )
    premium_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False,
        comment="Premium paid by farmer (₹)",
    )
    premium_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), nullable=False,
        comment="Premium rate applied (fraction of sum insured)",
    )

    # Payment
    premium_paid: Mapped[bool] = mapped_column(
        Boolean, server_default=func.text("false"), nullable=False, default=False,
    )
    premium_paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    payment_reference: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
        comment="Payment gateway reference (UPI/transaction ID)",
    )

    # Coverage
    coverage_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    coverage_end_date: Mapped[date] = mapped_column(Date, nullable=False)

    # Status
    status: Mapped[PolicyStatus] = mapped_column(
        String(20),
        server_default=func.text("'pending'"),
        nullable=False,
        default=PolicyStatus.PENDING,
        index=True,
    )

    # Bank account (for payout)
    bank_account_number: Mapped[str | None] = mapped_column(
        String(30), nullable=True,
        comment="Bank account number for claim payout (DBT)",
    )
    bank_ifsc: Mapped[str | None] = mapped_column(
        String(15), nullable=True,
        comment="Bank IFSC code",
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.NOW(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.NOW(), nullable=False,
    )

    # Relationships
    product: Mapped[InsuranceProduct] = relationship("InsuranceProduct", back_populates="policies")
    claims: Mapped[list["InsuranceClaim"]] = relationship(
        "InsuranceClaim", back_populates="policy", cascade="all, delete-orphan"
    )

    @property
    def is_active(self) -> bool:
        return self.status == PolicyStatus.ACTIVE

    def __repr__(self) -> str:
        return (
            f"<InsurancePolicy number={self.policy_number} "
            f"farmer={self.farmer_id} status={self.status}>"
        )


# ---------------------------------------------------------------------------
# InsuranceClaim
# ---------------------------------------------------------------------------


class InsuranceClaim(Base):
    """An insurance claim filed by a farmer.

    Lifecycle:
    - DRAFT: Farmer is composing (can attach evidence, edit details)
    - SUBMITTED: Farmer submits for insurer review
    - UNDER_REVIEW: Insurer is reviewing
    - EVIDENCE_REQUESTED: Insurer needs more documentation
    - APPROVED: Claim approved, awaiting payout
    - REJECTED: Claim denied (with reason)
    - PAYOUT_DISBURSED: Bank transfer completed
    - WITHDRAWN: Farmer withdrew

    Evidence is auto-aggregated from:
    - NDVI anomaly alerts on the insured plot (within claim period)
    - Disease reports on the insured plot (within claim period)
    - Weather alerts for the plot's district (within claim period)
    - Farmer can also upload additional photo evidence
    """

    __tablename__ = "insurance_claims"
    __table_args__ = (
        UniqueConstraint(
            "claim_number", name="insurance_claims_claim_number_unique"
        ),
        {"schema": "insurance"},
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        server_default=func.gen_random_uuid(),
        primary_key=True,
        nullable=False,
    )
    claim_number: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True,
        comment="Unique claim number (platform-generated)",
    )
    policy_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("insurance.insurance_policies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    farmer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("identity.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Claim details
    claim_type: Mapped[ClaimType] = mapped_column(
        String(30), nullable=False, index=True,
    )
    status: Mapped[ClaimStatus] = mapped_column(
        String(30),
        server_default=func.text("'draft'"),
        nullable=False,
        default=ClaimStatus.DRAFT,
        index=True,
    )

    # Loss details
    loss_date: Mapped[date] = mapped_column(
        Date, nullable=False,
        comment="Date the loss occurred (or was discovered)",
    )
    loss_description: Mapped[str] = mapped_column(
        Text, nullable=False,
        comment="Farmer's description of the loss",
    )
    estimated_loss_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        nullable=False,
        comment="Estimated crop loss percentage (0-100)",
    )
    claimed_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        comment="Amount claimed by farmer (₹)",
    )

    # Payout (set by insurer on approval)
    approved_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True,
        comment="Amount approved by insurer (may be less than claimed)",
    )
    payout_transaction_id: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
        comment="Bank transfer reference number",
    )
    payout_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )

    # Review
    reviewed_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("identity.users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    review_notes: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="Insurer's notes from review",
    )
    rejection_reason: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="If rejected, the reason",
    )

    # Auto-evidence summary (generated when claim is submitted)
    auto_evidence_summary: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Auto-compiled summary: NDVI drops, disease reports, weather alerts",
    )

    # Timestamps
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.NOW(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.NOW(), nullable=False,
    )

    # Relationships
    policy: Mapped[InsurancePolicy] = relationship(
        "InsurancePolicy", back_populates="claims"
    )
    evidence: Mapped[list["ClaimEvidence"]] = relationship(
        "ClaimEvidence", back_populates="claim", cascade="all, delete-orphan"
    )

    @property
    def is_draft(self) -> bool:
        return self.status == ClaimStatus.DRAFT

    @property
    def is_submitted(self) -> bool:
        return self.status in (
            ClaimStatus.SUBMITTED,
            ClaimStatus.UNDER_REVIEW,
            ClaimStatus.EVIDENCE_REQUESTED,
        )

    @property
    def is_resolved(self) -> bool:
        return self.status in (
            ClaimStatus.APPROVED,
            ClaimStatus.REJECTED,
            ClaimStatus.PAYOUT_DISBURSED,
            ClaimStatus.WITHDRAWN,
        )

    def __repr__(self) -> str:
        return (
            f"<InsuranceClaim number={self.claim_number} "
            f"policy={self.policy_id} status={self.status}>"
        )


# ---------------------------------------------------------------------------
# ClaimEvidence
# ---------------------------------------------------------------------------


class ClaimEvidence(Base):
    """Evidence attached to an insurance claim.

    Evidence can be:
    - Auto-attached (from NDVI anomalies, disease reports, weather alerts)
    - Manually attached (farmer uploads photos, officer inspection reports)
    - Bank documents (account verification for DBT)

    Each evidence item references the source module's record (via source_id)
    and stores a snapshot of relevant data at the time of attachment.
    """

    __tablename__ = "claim_evidence"
    __table_args__ = {"schema": "insurance"}

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        server_default=func.gen_random_uuid(),
        primary_key=True,
        nullable=False,
    )
    claim_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("insurance.insurance_claims.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Evidence type and source
    evidence_type: Mapped[EvidenceType] = mapped_column(
        String(30), nullable=False, index=True,
    )
    source_module: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="ndvi, disease, soil_weather, officer, farmer",
    )
    source_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        comment="FK to the source record (e.g., NDVI anomaly alert ID)",
    )

    # Evidence content
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        comment="When the evidence event occurred",
    )

    # Snapshot data (so claim is reviewable even if source is deleted)
    snapshot_data: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Snapshot of key fields from the source record",
    )

    # File attachment (for photos, documents)
    file_url: Mapped[str | None] = mapped_column(
        String(512), nullable=True,
        comment="S3 object key for uploaded files (photos, PDFs)",
    )

    # Auto vs manual
    is_auto_attached: Mapped[bool] = mapped_column(
        Boolean, server_default=func.text("false"), nullable=False, default=False,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.NOW(), nullable=False,
    )

    # Relationship
    claim: Mapped[InsuranceClaim] = relationship(
        "InsuranceClaim", back_populates="evidence"
    )

    def __repr__(self) -> str:
        return (
            f"<ClaimEvidence claim={self.claim_id} "
            f"type={self.evidence_type} auto={self.is_auto_attached}>"
        )
