"""Pydantic schemas for the privacy domain."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from krishisetu.domains.privacy.models import DSRStatus, DSRType, GrievanceStatus


# ---------------------------------------------------------------------------
# DSR schemas
# ---------------------------------------------------------------------------

class DSRCreateRequest(BaseModel):
    """Request to file a new Data Subject Request."""

    request_type: DSRType
    description: str | None = Field(default=None, max_length=2000)
    # For correction: which fields to change and to what
    requested_changes: dict[str, str] | None = Field(
        default=None,
        description="For correction requests: {field_name: new_value}",
    )


class DSRResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    request_type: DSRType
    status: DSRStatus
    description: str | None = None
    requested_changes: dict | None = None
    export_url: str | None = None
    export_expires_at: datetime | None = None
    submitted_at: datetime
    acknowledged_at: datetime | None = None
    completed_at: datetime | None = None
    due_at: datetime
    assigned_to: UUID | None = None
    resolution_notes: str | None = None
    rejection_reason: str | None = None


class DSRUpdateRequest(BaseModel):
    """Officer update for a DSR (assign, complete, reject)."""

    status: DSRStatus
    resolution_notes: str | None = Field(default=None, max_length=2000)
    rejection_reason: str | None = Field(default=None, max_length=1000)
    export_url: str | None = Field(default=None, max_length=1024)


# ---------------------------------------------------------------------------
# Grievance schemas
# ---------------------------------------------------------------------------

class GrievanceCreateRequest(BaseModel):
    """File a new grievance under DPDP Section 13."""

    category: str = Field(
        ...,
        max_length=50,
        description="E.g. 'unauthorized_access', 'consent_violation', 'data_quality'",
    )
    subject: str = Field(..., max_length=200)
    description: str = Field(..., max_length=5000)


class GrievanceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    grievance_number: str
    user_id: UUID
    category: str
    subject: str
    description: str
    status: GrievanceStatus
    filed_at: datetime
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None
    due_at: datetime
    assigned_to: UUID | None = None
    resolution: str | None = None
    escalation_reference: str | None = None


class GrievanceUpdateRequest(BaseModel):
    """Officer update for a grievance."""

    status: GrievanceStatus
    resolution: str | None = Field(default=None, max_length=5000)
    escalation_reference: str | None = Field(default=None, max_length=100)


# ---------------------------------------------------------------------------
# Erasure confirmation
# ---------------------------------------------------------------------------

class ErasureConfirmRequest(BaseModel):
    """Final confirmation for account erasure.

    Requires the user to type a confirmation phrase to prevent accidental
    deletion. This is a one-way operation — once completed, all personal
    data is permanently deleted (only anonymized aggregate data and legally
    required records such as tax/payment history are retained).
    """

    confirm_phrase: str = Field(
        ...,
        description='Must be exactly "DELETE MY ACCOUNT"',
    )
    reason: str | None = Field(default=None, max_length=1000)


__all__ = [
    "DSRCreateRequest",
    "DSRResponse",
    "DSRUpdateRequest",
    "GrievanceCreateRequest",
    "GrievanceResponse",
    "GrievanceUpdateRequest",
    "ErasureConfirmRequest",
]
