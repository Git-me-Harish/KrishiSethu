"""Privacy domain models (DPDP data subject rights).

Tables:
- data_subject_requests — formal DSR requests (access, correction, erasure,
  portability) submitted by users. Each has a status lifecycle.
- grievances — complaints filed under DPDP Section 13 (grievance redressal).
  The platform must acknowledge within 24h and resolve within 30 days.

DPDP rights implemented:
- Section 11: Right to access (what data we have)
- Section 12: Right to correction / erasure
- Section 13: Right of grievance redressal
- Section 14: Right to nominate (allows user to nominate someone to exercise
  rights on their behalf in case of death/incapacity — future enhancement)
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from krishisetu.core.database import Base


class DSRType(str, Enum):
    """Type of Data Subject Request."""

    ACCESS = "access"            # "What data do you have about me?"
    CORRECTION = "correction"    # "Fix this field"
    ERASURE = "erasure"          # "Delete my account and all data"
    PORTABILITY = "portability"  # "Export my data in machine-readable form"
    RESTRICTION = "restriction"  # "Stop processing but keep my data"


class DSRStatus(str, Enum):
    """Lifecycle of a DSR."""

    SUBMITTED = "submitted"      # User just filed it
    ACKNOWLEDGED = "acknowledged"  # System auto-acked within 24h
    IN_REVIEW = "in_review"      # Officer picked it up
    PROCESSING = "processing"    # Action in progress (e.g. export generating)
    AWAITING_VERIFICATION = "awaiting_verification"  # Waiting on user to confirm
    COMPLETED = "completed"
    REJECTED = "rejected"        # Refused (e.g. legal obligation to retain)
    WITHDRAWN = "withdrawn"      # User cancelled the request


class GrievanceStatus(str, Enum):
    """Lifecycle of a DPDP grievance."""

    FILED = "filed"
    ACKNOWLEDGED = "acknowledged"
    IN_REVIEW = "in_review"
    RESOLVED = "resolved"
    ESCALATED = "escalated"  # User escalated to Data Protection Board
    REJECTED = "rejected"


class DataSubjectRequest(Base):
    """A formal Data Subject Request filed by a user.

    Maps to: privacy.data_subject_requests
    """

    __tablename__ = "data_subject_requests"
    __table_args__ = {"schema": "privacy"}

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        server_default=func.gen_random_uuid(),
        primary_key=True,
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("identity.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    request_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(30),
        server_default=func.text("'submitted'"),
        nullable=False,
        index=True,
    )
    # Free-text description from the user (e.g. "Please correct my bank account")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # For correction requests: the field(s) and proposed new value(s)
    requested_changes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # For access/portability: the generated export URL (presigned S3, time-limited)
    export_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    export_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Tracking timestamps (DPDP SLA compliance)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.NOW(), nullable=False
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # The deadline (submitted + 30 days for access / 15 for correction)
    due_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    # The officer assigned to handle this request (admin / agri_officer)
    assigned_to: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("identity.users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Officer's resolution notes
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)


class Grievance(Base):
    """A formal grievance filed under DPDP Section 13.

    Maps to: privacy.grievances

    DPDP requires:
    - Acknowledge within 24 hours
    - Resolve within 30 days (or explain delay in writing)
    - User can escalate to Data Protection Board of India if unresolved
    """

    __tablename__ = "grievances"
    __table_args__ = {"schema": "privacy"}

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        server_default=func.gen_random_uuid(),
        primary_key=True,
        nullable=False,
    )
    grievance_number: Mapped[str] = mapped_column(
        String(30), nullable=False, unique=True, index=True
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("identity.users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="E.g. 'unauthorized_access', 'consent_violation', 'data_quality'",
    )
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        server_default=func.text("'filed'"),
        nullable=False,
        index=True,
    )
    filed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.NOW(), nullable=False
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    due_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    assigned_to: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("identity.users.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolution: Mapped[str | None] = mapped_column(Text, nullable=True)
    escalation_reference: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Reference number if escalated to Data Protection Board",
    )
    attachments: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)


__all__ = [
    "DataSubjectRequest",
    "Grievance",
    "DSRType",
    "DSRStatus",
    "GrievanceStatus",
]
