"""SQLAlchemy ORM models for the schemes domain.

Tables:
- schemes.scheme_catalog           (master data — govt scheme definitions)
- schemes.scheme_applications      (farmer applications with status workflow)

Design notes:
- Scheme catalog stores eligibility rules as JSONB (structured rules engine)
- Applications store a snapshot of farmer data at submission time (so changes
  to farmer profile don't invalidate the application)
- The eligibility engine evaluates rules against farmer profile data
  (role, aadhaar_verified, land_holding, district, state, etc.)
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


class SchemeCategory(str, Enum):
    """Category of government scheme."""

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


class SchemeLevel(str, Enum):
    """Level of government administering the scheme."""

    CENTRAL = "central"
    STATE = "state"
    CENTRAL_STATE = "central_state"


class ApplicationStatus(str, Enum):
    """Status of a scheme application."""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    RESUBMISSION_REQUESTED = "resubmission_requested"
    WITHDRAWN = "withdrawn"
    BENEFIT_DISBURSED = "benefit_disbursed"


# ---------------------------------------------------------------------------
# SchemeCatalog (master data)
# ---------------------------------------------------------------------------


class SchemeCatalog(Base):
    """A government scheme available to farmers.

    Each scheme has:
    - Eligibility rules (JSONB) — structured rules evaluated by the engine
    - Benefits description (amount, frequency, form)
    - Application process (online/offline, documents required)
    - Coverage (central/state/district)

    Eligibility rules format (JSONB):
    {
        "role": "farmer",
        "aadhaar_verified": true,
        "conditions": [
            {"field": "total_land_holding_ha", "op": "gt", "value": 0},
            {"field": "state", "op": "in", "value": ["Maharashtra", "Punjab"]},
            {"field": "occupation_category", "op": "not_in", "value": ["institutional", "government_job"]}
        ]
    }

    The eligibility engine evaluates these against the farmer's profile.
    """

    __tablename__ = "scheme_catalog"
    __table_args__ = (
        UniqueConstraint("code", name="scheme_catalog_code_unique"),
        {"schema": "schemes"},
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        server_default=func.gen_random_uuid(),
        primary_key=True,
        nullable=False,
    )
    code: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="Unique scheme code, e.g., 'pm-kisan', 'kcc', 'pmfby'",
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    name_hi: Mapped[str | None] = mapped_column(String(255), nullable=True)
    short_description: Mapped[str] = mapped_column(String(500), nullable=False)
    full_description: Mapped[str] = mapped_column(Text, nullable=False)

    # Classification
    category: Mapped[SchemeCategory] = mapped_column(
        String(30), nullable=False, index=True,
    )
    level: Mapped[SchemeLevel] = mapped_column(
        String(20), nullable=False, default=SchemeLevel.CENTRAL,
    )
    ministry: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        comment="Ministry/department administering the scheme",
    )

    # Coverage
    states: Mapped[list[str] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment='["Maharashtra", "Punjab"] or null for all states',
    )

    # Benefits
    benefit_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="cash, subsidy, insurance, credit, kind",
    )
    benefit_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True,
        comment="Amount in ₹ (if applicable)",
    )
    benefit_frequency: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
        comment="one_time, yearly, quarterly, monthly",
    )
    benefit_description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Eligibility rules (JSONB — evaluated by the engine)
    eligibility_rules: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment="Structured rules for eligibility engine",
    )

    # Application process
    application_mode: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="online",
        comment="online, offline, mixed",
    )
    documents_required: Mapped[list[str] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment='["aadhaar", "land_records", "bank_details"]',
    )
    application_url: Mapped[str | None] = mapped_column(
        String(512), nullable=True,
        comment="External URL if scheme is applied on another portal",
    )

    # Timeline
    application_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    application_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Status
    is_active: Mapped[bool] = mapped_column(
        Boolean, server_default=func.text("true"), nullable=False, default=True,
    )
    is_featured: Mapped[bool] = mapped_column(
        Boolean, server_default=func.text("false"), nullable=False, default=False,
        comment="Show on homepage / featured schemes",
    )

    # Metadata
    source_url: Mapped[str | None] = mapped_column(
        String(512), nullable=True,
        comment="Official scheme page URL",
    )
    helpline_number: Mapped[str | None] = mapped_column(String(20), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.NOW(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.NOW(), nullable=False,
    )

    # Relationships
    applications: Mapped[list["SchemeApplication"]] = relationship(
        "SchemeApplication", back_populates="scheme"
    )

    def __repr__(self) -> str:
        return f"<SchemeCatalog code={self.code} name={self.name}>"


# ---------------------------------------------------------------------------
# SchemeApplication
# ---------------------------------------------------------------------------


class SchemeApplication(Base):
    """A farmer's application for a government scheme.

    Stores a snapshot of the farmer's data at submission time so that later
    changes to the farmer's profile don't affect the application review.

    Lifecycle:
    - DRAFT: Farmer is composing the application
    - SUBMITTED: Farmer submitted for review
    - UNDER_REVIEW: Officer is reviewing
    - APPROVED: Application approved, benefit processing
    - REJECTED: Application rejected (with reason)
    - RESUBMISSION_REQUESTED: Officer needs more info
    - BENEFIT_DISBURSED: Benefit (cash/subsidy) has been disbursed
    - WITHDRAWN: Farmer withdrew the application
    """

    __tablename__ = "scheme_applications"
    __table_args__ = (
        UniqueConstraint("application_number", name="scheme_applications_number_unique"),
        {"schema": "schemes"},
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        server_default=func.gen_random_uuid(),
        primary_key=True,
        nullable=False,
    )
    application_number: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True,
    )
    scheme_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("schemes.scheme_catalog.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    farmer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("identity.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Status
    status: Mapped[ApplicationStatus] = mapped_column(
        String(30),
        server_default=func.text("'draft'"),
        nullable=False,
        default=ApplicationStatus.DRAFT,
        index=True,
    )

    # Snapshot of farmer data at submission time
    submitted_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        comment="Snapshot of farmer profile + application-specific fields",
    )

    # Eligibility check result (at submission time)
    eligibility_result: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment='{"eligible": true, "matched_conditions": [...], "failed_conditions": [...]}',
    )

    # Documents (S3 keys)
    submitted_documents: Mapped[list[str] | None] = mapped_column(
        JSONB, nullable=True,
        comment='["aadhaar.pdf", "land_records.pdf"]',
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
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Benefit disbursement
    benefit_disbursed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    benefit_reference: Mapped[str | None] = mapped_column(
        String(100), nullable=True,
        comment="Transaction/reference number for disbursed benefit",
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
    scheme: Mapped[SchemeCatalog] = relationship("SchemeCatalog", back_populates="applications")

    @property
    def is_draft(self) -> bool:
        return self.status == ApplicationStatus.DRAFT

    @property
    def is_submitted(self) -> bool:
        return self.status in (
            ApplicationStatus.SUBMITTED,
            ApplicationStatus.UNDER_REVIEW,
            ApplicationStatus.RESUBMISSION_REQUESTED,
        )

    @property
    def is_resolved(self) -> bool:
        return self.status in (
            ApplicationStatus.APPROVED,
            ApplicationStatus.REJECTED,
            ApplicationStatus.BENEFIT_DISBURSED,
            ApplicationStatus.WITHDRAWN,
        )

    def __repr__(self) -> str:
        return (
            f"<SchemeApplication number={self.application_number} "
            f"scheme={self.scheme_id} status={self.status}>"
        )
