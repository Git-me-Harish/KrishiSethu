"""Pydantic schemas for the consent domain."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from krishisetu.domains.consent.models import ConsentPurpose, ConsentStatus


class ConsentGrantRequest(BaseModel):
    """Request to grant consent for one or more purposes."""

    purposes: list[ConsentPurpose] = Field(
        ...,
        min_length=1,
        max_length=20,
        description="Purposes to grant consent for",
    )
    notice_version: str = Field(
        ...,
        description="Version of the consent notice the user agreed to",
    )
    notice_text_hash: str | None = Field(
        default=None,
        description="SHA-256 of the exact notice text shown",
    )
    language: str = Field(default="en", max_length=5)


class ConsentWithdrawRequest(BaseModel):
    """Request to withdraw consent for one or more purposes."""

    purposes: list[ConsentPurpose] = Field(
        ...,
        min_length=1,
        max_length=20,
    )
    reason: str | None = Field(default=None, max_length=1000)


class ConsentRecord(BaseModel):
    """Public representation of a consent record."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    purpose: ConsentPurpose
    status: ConsentStatus
    notice_version: str
    granted_at: datetime
    withdrawn_at: datetime | None = None
    expires_at: datetime | None = None
    withdrawal_reason: str | None = None


class ConsentStatusResponse(BaseModel):
    """Summary of a user's consent state across all purposes."""

    granted: list[ConsentPurpose] = Field(default_factory=list)
    withdrawn: list[ConsentPurpose] = Field(default_factory=list)
    not_yet_asked: list[ConsentPurpose] = Field(default_factory=list)


class ConsentNoticeResponse(BaseModel):
    """A versioned consent notice."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    version: str
    purpose: ConsentPurpose
    title: str
    summary: str
    full_text: str
    language: str
    effective_from: datetime


__all__ = [
    "ConsentGrantRequest",
    "ConsentWithdrawRequest",
    "ConsentRecord",
    "ConsentStatusResponse",
    "ConsentNoticeResponse",
]
