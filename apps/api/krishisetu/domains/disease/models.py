"""SQLAlchemy ORM models for the disease domain.

Tables:
- intelligence.diseases             (master data — disease catalog)
- intelligence.disease_treatments   (treatment recommendations per disease)
- intelligence.disease_reports      (farmer-submitted photos + metadata)
- intelligence.disease_predictions  (ML model predictions with full provenance)
- intelligence.disease_feedback     (farmer feedback on prediction accuracy)

Design principles:
- All ML predictions stored with full provenance (model_name, model_version,
  inference_time, all_predictions JSONB) for audit and rollback
- Image URLs stored as strings (S3 pre-signed URLs generated on demand)
- Disease catalog is versioned via is_active flag (allows updates without
  breaking historical predictions)
- Feedback stored separately from predictions (one-to-many) to support
  multiple feedback events per prediction (e.g., initial correct, later
  corrected after officer review)
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, ClassVar
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from krishisetu.core.database import Base

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class DiseaseSeverity(str, Enum):
    """Severity levels for a disease."""

    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class DiseaseReportStatus(str, Enum):
    """Status of a disease report (async pipeline)."""

    PENDING = "pending"            # Report submitted, awaiting inference
    PROCESSING = "processing"      # ML inference in progress
    COMPLETED = "completed"        # Inference done, prediction available
    FAILED = "failed"              # Inference failed (model error, bad image)
    OFFICER_REVIEW = "officer_review"  # Low-confidence, sent for manual review
    REVIEWED = "reviewed"          # Officer has reviewed


class TreatmentType(str, Enum):
    """Type of treatment recommendation."""

    ORGANIC = "organic"
    CHEMICAL = "chemical"
    BIOLOGICAL = "biological"
    CULTURAL = "cultural"  # Field management practices
    PREVENTIVE = "preventive"  # Prevention measures


class FeedbackType(str, Enum):
    """Farmer feedback on a prediction."""

    CORRECT = "correct"
    INCORRECT = "incorrect"
    PARTIALLY_CORRECT = "partially_correct"


# ---------------------------------------------------------------------------
# Disease (master data)
# ---------------------------------------------------------------------------


class Disease(Base):
    """Master data: crop diseases.

    Includes both biotic (fungal, bacterial, viral, pest) and abiotic
    (nutrient deficiency, environmental stress) conditions.

    Sourced from ICAR (Indian Council of Agricultural Research) and
    extension publications. Each disease has:
    - Slug (URL-friendly identifier matching ML model labels)
    - Symptoms (textual description for officer/farmer reference)
    - Cause (pathogen or environmental factor)
    - Affected crops (comma-separated slugs matching farmer.crops)
    - Severity default (LOW to CRITICAL)
    - Treatment recommendations (via DiseaseTreatment relation)
    """

    __tablename__ = "diseases"
    __table_args__ = (
        UniqueConstraint("slug", name="diseases_slug_unique"),
        {"schema": "intelligence"},
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        server_default=func.gen_random_uuid(),
        primary_key=True,
        nullable=False,
    )
    slug: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="URL-friendly ID matching ML model labels, e.g., 'rice_blast'",
    )
    name_en: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        comment="English name",
    )
    name_hi: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
        comment="Hindi name (Devanagari)",
    )
    scientific_name: Mapped[str | None] = mapped_column(
        String(300),
        nullable=True,
        comment="Pathogen scientific name, e.g., 'Magnaporthe oryzae'",
    )

    # Classification
    disease_type: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        comment="fungal, bacterial, viral, pest, nematode, nutrient, environmental",
    )
    affected_crops: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment='Array of crop slugs, e.g., ["rice", "wheat"]',
    )

    # Clinical info
    symptoms: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Detailed symptom description for identification",
    )
    cause: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="What causes the disease (pathogen, conditions)",
    )
    spread_mechanism: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="How the disease spreads (wind, water, soil, vectors)",
    )
    favorable_conditions: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Environmental conditions that favor disease development",
    )

    # Severity
    default_severity: Mapped[DiseaseSeverity] = mapped_column(
        String(20),
        server_default=func.text("'moderate'"),
        nullable=False,
        default=DiseaseSeverity.MODERATE,
    )

    # Prevention
    prevention_measures: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Steps to prevent the disease",
    )

    # Lifecycle
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        server_default=func.text("true"),
        nullable=False,
        default=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.NOW(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.NOW(),
        nullable=False,
    )

    # Relationships
    treatments: Mapped[list[DiseaseTreatment]] = relationship(
        "DiseaseTreatment",
        back_populates="disease",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Disease slug={self.slug} name={self.name_en}>"


# ---------------------------------------------------------------------------
# DiseaseTreatment
# ---------------------------------------------------------------------------


class DiseaseTreatment(Base):
    """Treatment recommendation for a disease.

    A disease can have multiple treatments of different types:
    - Organic (e.g., neem oil spray)
    - Chemical (e.g., fungicide application)
    - Biological (e.g., Trichoderma application)
    - Cultural (e.g., crop rotation, field sanitation)
    - Preventive (e.g., seed treatment before sowing)

    Each treatment links to a marketplace product (Phase 3) when applicable,
    enabling one-click ordering from the disease result page.
    """

    __tablename__ = "disease_treatments"
    __table_args__: ClassVar[dict[str, str]] = {"schema": "intelligence"}

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        server_default=func.gen_random_uuid(),
        primary_key=True,
        nullable=False,
    )
    disease_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("intelligence.diseases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    treatment_type: Mapped[TreatmentType] = mapped_column(
        String(30),
        nullable=False,
        comment="organic, chemical, biological, cultural, preventive",
    )
    description: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="What to do (e.g., 'Apply Mancozeb 75% WP at 2.5g/L')",
    )
    dosage: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Dosage instructions (e.g., '2.5g per liter of water')",
    )
    application_method: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="How to apply (foliar spray, soil drench, seed treatment, etc.)",
    )
    timing: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="When to apply (e.g., 'At first symptom appearance, repeat after 7-10 days')",
    )
    precautions: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Safety precautions (PPE, waiting period before harvest)",
    )

    # Marketplace link (Phase 3) — nullable for non-product treatments (cultural)
    product_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        nullable=True,
        comment="FK to commerce.products for one-click ordering",
    )

    # Priority (1 = primary, 2 = secondary, etc.)
    priority: Mapped[int] = mapped_column(
        Integer,
        server_default=func.text("1"),
        nullable=False,
        default=1,
    )
    is_primary: Mapped[bool] = mapped_column(
        Boolean,
        server_default=func.text("false"),
        nullable=False,
        default=False,
    )

    # Source citation
    source: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Citation, e.g., 'ICAR IPM Package, 2023'",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.NOW(),
        nullable=False,
    )

    # Relationships
    disease: Mapped[Disease] = relationship("Disease", back_populates="treatments")

    def __repr__(self) -> str:
        return f"<DiseaseTreatment disease={self.disease_id} type={self.treatment_type}>"


# ---------------------------------------------------------------------------
# DiseaseReport (farmer-submitted)
# ---------------------------------------------------------------------------


class DiseaseReport(Base):
    """A farmer-submitted photo of an affected crop.

    The async pipeline:
    1. Farmer uploads image (gets pre-signed S3 URL)
    2. POST /disease-reports creates a report with status=pending
    3. Celery task picks up the report, calls ML inference service
    4. Prediction stored in disease_predictions
    5. Status updated to completed (or failed/officer_review)
    6. Farmer notified via push notification

    The report is linked to a plot (so we can correlate with NDVI drops and
    weather events for insurance claims) and a crop cycle (to know which
    crop is being grown).
    """

    __tablename__ = "disease_reports"
    __table_args__: ClassVar[dict[str, str]] = {"schema": "intelligence"}

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        server_default=func.gen_random_uuid(),
        primary_key=True,
        nullable=False,
    )

    # Ownership
    farmer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("identity.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    plot_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("farmer.plots.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
        comment="Plot where the affected crop is growing",
    )
    crop_cycle_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("farmer.crop_cycles.id", ondelete="SET NULL"),
        nullable=True,
        comment="Specific crop cycle affected",
    )

    # Image
    image_url: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        comment="S3 object key (not full URL — pre-signed URL generated on demand)",
    )
    image_thumbnail_url: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        comment="S3 key for compressed thumbnail (generated server-side)",
    )
    image_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="EXIF data, dimensions, file size, etc.",
    )

    # Context
    captured_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="When the photo was taken (from EXIF), null if not available",
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.NOW(),
        nullable=False,
    )
    farmer_notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Farmer's description of symptoms (optional)",
    )

    # Status
    status: Mapped[DiseaseReportStatus] = mapped_column(
        String(30),
        server_default=func.text("'pending'"),
        nullable=False,
        default=DiseaseReportStatus.PENDING,
        index=True,
    )
    failure_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="If status=failed, why (model error, invalid image, etc.)",
    )

    # Officer review (for low-confidence cases)
    reviewed_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("identity.users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    officer_diagnosis: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Officer's manual diagnosis if ML was uncertain",
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.NOW(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.NOW(),
        nullable=False,
    )

    # Relationships
    prediction: Mapped[DiseasePrediction | None] = relationship(
        "DiseasePrediction",
        back_populates="report",
        uselist=False,
        cascade="all, delete-orphan",
    )
    feedback: Mapped[list[DiseaseFeedback]] = relationship(
        "DiseaseFeedback",
        back_populates="report",
        cascade="all, delete-orphan",
    )

    @property
    def is_completed(self) -> bool:
        return self.status == DiseaseReportStatus.COMPLETED

    @property
    def needs_review(self) -> bool:
        return self.status == DiseaseReportStatus.OFFICER_REVIEW

    def __repr__(self) -> str:
        return (
            f"<DiseaseReport id={self.id} farmer={self.farmer_id} "
            f"status={self.status}>"
        )


# ---------------------------------------------------------------------------
# DiseasePrediction (ML output with full provenance)
# ---------------------------------------------------------------------------


class DiseasePrediction(Base):
    """ML model prediction for a disease report.

    Stores full provenance for audit and rollback:
    - model_name, model_version (which model produced this)
    - inference_time_ms (latency tracking)
    - all_predictions (full distribution, not just top-1)
    - heat_map_url (Grad-CAM visualization, Phase 2)

    This enables:
    - A/B testing (compare predictions from different model versions)
    - Rollback (if a model version is found to be defective, identify
      affected predictions)
    - Drift monitoring (track prediction distribution over time)
    - Retraining (use feedback to label training data)
    """

    __tablename__ = "disease_predictions"
    __table_args__: ClassVar[dict[str, str]] = {"schema": "intelligence"}

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        server_default=func.gen_random_uuid(),
        primary_key=True,
        nullable=False,
    )
    report_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("intelligence.disease_reports.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # One prediction per report
        index=True,
    )

    # Prediction
    disease_slug: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        index=True,
        comment="Top predicted disease slug (matches intelligence.diseases.slug)",
    )
    confidence: Mapped[Decimal] = mapped_column(
        Numeric(5, 4),
        nullable=False,
        comment="Confidence score [0, 1] after temperature calibration",
    )

    # Full distribution
    all_predictions: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB,
        nullable=False,
        comment='Array of {label, confidence, disease_slug} for all classes',
    )

    # Model provenance
    model_name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="disease_classifier",
    )
    model_version: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Semantic version, e.g., v1.2.0",
    )
    inference_time_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Inference latency in milliseconds",
    )

    # Reliability
    is_reliable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="True if confidence >= 0.70 threshold",
    )

    # Visualization (Phase 2)
    heat_map_url: Mapped[str | None] = mapped_column(
        String(512),
        nullable=True,
        comment="S3 key for Grad-CAM heatmap showing affected regions",
    )

    inferred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.NOW(),
        nullable=False,
    )

    # Relationships
    report: Mapped[DiseaseReport] = relationship(
        "DiseaseReport", back_populates="prediction"
    )

    def __repr__(self) -> str:
        return (
            f"<DiseasePrediction report={self.report_id} "
            f"disease={self.disease_slug} confidence={self.confidence} "
            f"model={self.model_version}>"
        )


# ---------------------------------------------------------------------------
# DiseaseFeedback
# ---------------------------------------------------------------------------


class DiseaseFeedback(Base):
    """Farmer feedback on a prediction (for model improvement).

    A farmer can mark a prediction as correct, incorrect, or partially
    correct. If incorrect, they can suggest the correct disease.

    This data is used for:
    - Computing model accuracy in production
    - Identifying classes with low precision/recall for retraining
    - Generating labeled training data (with officer verification)
    """

    __tablename__ = "disease_feedback"
    __table_args__: ClassVar[dict[str, str]] = {"schema": "intelligence"}

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        server_default=func.gen_random_uuid(),
        primary_key=True,
        nullable=False,
    )
    report_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("intelligence.disease_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    farmer_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("identity.users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Feedback
    feedback_type: Mapped[FeedbackType] = mapped_column(
        String(30),
        nullable=False,
        comment="correct, incorrect, partially_correct",
    )
    suggested_disease_slug: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="If incorrect, what the farmer thinks is the actual disease",
    )
    notes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Optional free-text feedback",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.NOW(),
        nullable=False,
    )

    # Relationships
    report: Mapped[DiseaseReport] = relationship(
        "DiseaseReport", back_populates="feedback"
    )

    def __repr__(self) -> str:
        return (
            f"<DiseaseFeedback report={self.report_id} "
            f"type={self.feedback_type}>"
        )
