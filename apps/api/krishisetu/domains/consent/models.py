"""Consent domain models (DPDP Act 2023 compliance).

The consent table records every consent grant and withdrawal. Under India's
Digital Personal Data Protection Act 2023, consent must be:
- Free, specific, informed, and unambiguous
- Limited to a specific purpose
- Revocable at any time
- Recorded with a timestamp and a reference to the consent notice version

This schema supports all four requirements:
- purpose: specific purpose code (enum) — limits scope
- notice_version: which consent notice the user agreed to
- granted_at / withdrawn_at: timestamps for both directions
- actor_id: who granted/withdrew (the user, or an admin on their behalf)
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import ClassVar
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from krishisetu.core.database import Base


class ConsentPurpose(str, Enum):
    """Enumerated purposes for which the platform processes personal data.

    Each purpose is a discrete, named reason for data processing. Adding a
    new purpose requires a code change (so it goes through review) and a
    user-facing consent notice update.
    """

    IDENTITY_VERIFICATION = "identity_verification"  # Aadhaar e-KYC
    DISEASE_DIAGNOSIS = "disease_diagnosis"          # ML on photos
    WEATHER_ADVISORY = "weather_advisory"            # location-based weather
    NDVI_MONITORING = "ndvi_monitoring"              # satellite imagery of plots
    INSURANCE_PROCESSING = "insurance_processing"    # underwriting & claims
    MARKETPLACE_TRANSACTIONS = "marketplace_transactions"  # orders, payments
    SCHEME_MATCHING = "scheme_matching"              # eligibility engine
    VOICE_PROCESSING = "voice_processing"            # ASR + NLU on voice queries
    COMMUNICATION = "communication"                  # SMS, notifications
    RESEARCH_ANONYMIZED = "research_anonymized"      # aggregated, no PII
    SERVICE_IMPROVEMENT = "service_improvement"      # product analytics


class ConsentStatus(str, Enum):
    """State of a consent record."""

    GRANTED = "granted"
    WITHDRAWN = "withdrawn"
    EXPIRED = "expired"


class Consent(Base):
    """A user's consent for a specific data-processing purpose.

    Maps to: privacy.consent_records

    A user can have at most ONE active consent per purpose. Re-granting
    consent for a purpose that was previously withdrawn creates a NEW row
    (the old row remains for audit history).
    """

    __tablename__ = "consent_records"
    __table_args__ = (
        # Partial unique index: at most one ACTIVE grant per (user, purpose).
        # Implemented as a partial unique INDEX (not UniqueConstraint) because
        # UniqueConstraint does not accept postgresql_where.
        Index(
            "consent_one_active_per_purpose",
            "user_id",
            "purpose",
            unique=True,
            postgresql_where=func.text("status = 'granted'"),
        ),
        {"schema": "privacy"},
    )

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
    purpose: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(20),
        server_default=func.text("'granted'"),
        nullable=False,
        index=True,
    )
    notice_version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Version of the consent notice the user agreed to (e.g. '2026.07.01')",
    )
    notice_text_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
        comment="SHA-256 of the exact notice text shown — for legal provenance",
    )
    granted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.NOW(),
        nullable=False,
    )
    withdrawn_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Optional expiry (e.g. for time-limited research consent)",
    )
    granted_from_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    withdrawn_from_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column(
        "metadata",
        JSONB,
        nullable=True,
        comment="Additional context (e.g. language selected, screen size)",
    )
    # Track which actor revoked (could be the user or an admin)
    withdrawn_by: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("identity.users.id", ondelete="SET NULL"),
        nullable=True,
    )
    withdrawal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class ConsentNotice(Base):
    """Versioned consent notice text — what the user actually saw.

    Maintained separately so we can reproduce the exact notice shown to any
    user at any point in time (DPDP audit requirement).
    """

    __tablename__ = "consent_notices"
    __table_args__: ClassVar[dict[str, str]] = {"schema": "privacy"}

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        server_default=func.gen_random_uuid(),
        primary_key=True,
        nullable=False,
    )
    version: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    purpose: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    full_text: Mapped[str] = mapped_column(Text, nullable=False)
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    language: Mapped[str] = mapped_column(String(5), nullable=False, default="en")
    effective_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.NOW(), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, server_default=func.text("true"), nullable=False
    )


__all__ = ["Consent", "ConsentNotice", "ConsentPurpose", "ConsentStatus"]
