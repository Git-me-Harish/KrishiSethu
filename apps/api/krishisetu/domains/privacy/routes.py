"""Privacy domain routes — Data Subject Rights (DPDP Act 2023).

User endpoints (under /privacy):
- POST   /privacy/dsr                    — file a new DSR (access/correction/erasure/portability)
- GET    /privacy/dsr                    — list my DSRs
- GET    /privacy/dsr/{dsr_id}           — get a specific DSR
- POST   /privacy/erasure/confirm        — confirm account erasure (requires confirmation phrase)
- POST   /privacy/grievances             — file a grievance
- GET    /privacy/grievances             — list my grievances
- GET    /privacy/grievances/{id}        — get a specific grievance

Officer endpoints (under /privacy/officer):
- GET    /privacy/officer/dsr            — list all DSRs
- PATCH  /privacy/officer/dsr/{id}       — update DSR status
- GET    /privacy/officer/grievances     — list all grievances
- PATCH  /privacy/officer/grievances/{id} — update grievance status
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from krishisetu.core.database import get_db
from krishisetu.core.dependencies import CurrentUser, require_role
from krishisetu.core.logging import get_logger
from krishisetu.domains.identity.models import UserRole
from krishisetu.domains.privacy.models import DSRStatus, DSRType, GrievanceStatus
from krishisetu.domains.privacy.schemas import (
    DSRCreateRequest,
    DSRResponse,
    DSRUpdateRequest,
    ErasureConfirmRequest,
    GrievanceCreateRequest,
    GrievanceResponse,
    GrievanceUpdateRequest,
)
from krishisetu.domains.privacy.services import (
    create_dsr,
    create_grievance,
    execute_erasure,
    get_dsr,
    get_grievance,
    list_all_dsrs,
    list_all_grievances,
    list_my_dsrs,
    list_my_grievances,
    update_dsr,
    update_grievance,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/privacy", tags=["privacy"])
officer_router = APIRouter(prefix="/privacy/officer", tags=["privacy-officer"])


# ---------------------------------------------------------------------------
# DSR — Data Subject Requests
# ---------------------------------------------------------------------------

@router.post("/dsr", response_model=DSRResponse, status_code=201)
async def file_dsr(
    payload: DSRCreateRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> DSRResponse:
    """File a new Data Subject Request.

    Types:
    - access: Request a copy of all data we have about you (30-day SLA)
    - correction: Request correction of inaccurate data (15-day SLA)
    - erasure: Request permanent deletion (use /erasure/confirm to confirm)
    - portability: Request machine-readable export (30-day SLA)
    """
    dsr = await create_dsr(
        db,
        current_user.id,
        payload.request_type,
        description=payload.description,
        requested_changes=payload.requested_changes,
        request=request,
    )
    return DSRResponse.model_validate(dsr)


@router.get("/dsr", response_model=list[DSRResponse])
async def list_dsrs(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[DSRResponse]:
    """List all DSRs filed by the current user."""
    dsrs = await list_my_dsrs(db, current_user.id)
    return [DSRResponse.model_validate(d) for d in dsrs]


@router.get("/dsr/{dsr_id}", response_model=DSRResponse)
async def get_dsr_detail(
    dsr_id: Annotated[UUID, Path()],
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DSRResponse:
    """Get details of a specific DSR filed by the current user."""
    dsr = await get_dsr(db, dsr_id, current_user.id)
    if dsr is None:
        raise HTTPException(status_code=404, detail="DSR not found")
    return DSRResponse.model_validate(dsr)


# ---------------------------------------------------------------------------
# Erasure confirmation (final step)
# ---------------------------------------------------------------------------

@router.post("/erasure/confirm", status_code=202)
async def confirm_erasure(
    payload: ErasureConfirmRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> dict:
    """Confirm permanent account erasure.

    This is a one-way operation. The user must type "DELETE MY ACCOUNT"
    exactly as confirmation. Once executed:
    - All personal data is permanently deleted
    - Payment records are anonymized (kept for tax compliance, 7 years)
    - Audit logs are anonymized (kept for security monitoring)
    - The user is immediately logged out
    """
    if payload.confirm_phrase != "DELETE MY ACCOUNT":
        raise HTTPException(
            status_code=400,
            detail='Confirmation phrase must be exactly "DELETE MY ACCOUNT"',
        )

    # File a DSR for audit trail
    await create_dsr(
        db,
        current_user.id,
        DSRType.ERASURE,
        description=f"User confirmed erasure. Reason: {payload.reason or 'not provided'}",
        request=request,
    )

    # Execute the erasure
    await execute_erasure(
        db,
        current_user.id,
        reason=payload.reason,
        request=request,
    )

    return {
        "status": "deleted",
        "message": "Your account and all personal data have been permanently deleted.",
    }


# ---------------------------------------------------------------------------
# Grievances
# ---------------------------------------------------------------------------

@router.post("/grievances", response_model=GrievanceResponse, status_code=201)
async def file_grievance(
    payload: GrievanceCreateRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> GrievanceResponse:
    """File a grievance under DPDP Section 13.

    The platform must acknowledge within 24 hours and resolve within 30 days.
    If unresolved, the user can escalate to the Data Protection Board of India.
    """
    grievance = await create_grievance(
        db,
        current_user.id,
        category=payload.category,
        subject=payload.subject,
        description=payload.description,
        request=request,
    )
    return GrievanceResponse.model_validate(grievance)


@router.get("/grievances", response_model=list[GrievanceResponse])
async def list_grievances(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[GrievanceResponse]:
    """List all grievances filed by the current user."""
    grievances = await list_my_grievances(db, current_user.id)
    return [GrievanceResponse.model_validate(g) for g in grievances]


@router.get("/grievances/{grievance_id}", response_model=GrievanceResponse)
async def get_grievance_detail(
    grievance_id: Annotated[UUID, Path()],
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GrievanceResponse:
    """Get details of a specific grievance."""
    grievance = await get_grievance(db, grievance_id, current_user.id)
    if grievance is None:
        raise HTTPException(status_code=404, detail="Grievance not found")
    return GrievanceResponse.model_validate(grievance)


# ---------------------------------------------------------------------------
# Officer endpoints — DSR & grievance management
# ---------------------------------------------------------------------------

@officer_router.get("/dsr", response_model=list[DSRResponse])
async def officer_list_dsrs(
    _: Annotated[CurrentUser, Depends(require_role(UserRole.ADMIN, UserRole.AGRI_OFFICER))],
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: Annotated[DSRStatus | None, Query(alias="status")] = None,
) -> list[DSRResponse]:
    """Officer: list all DSRs, optionally filtered by status."""
    dsrs = await list_all_dsrs(db, status=status_filter)
    return [DSRResponse.model_validate(d) for d in dsrs]


@officer_router.patch("/dsr/{dsr_id}", response_model=DSRResponse)
async def officer_update_dsr(
    dsr_id: Annotated[UUID, Path()],
    payload: DSRUpdateRequest,
    officer: Annotated[CurrentUser, Depends(require_role(UserRole.ADMIN, UserRole.AGRI_OFFICER))],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> DSRResponse:
    """Officer: update a DSR's status (assign, complete, reject)."""
    updated = await update_dsr(
        db,
        dsr_id,
        status=payload.status,
        resolution_notes=payload.resolution_notes,
        rejection_reason=payload.rejection_reason,
        export_url=payload.export_url,
        officer_id=officer.id,
        request=request,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="DSR not found")
    return DSRResponse.model_validate(updated)


@officer_router.get("/grievances", response_model=list[GrievanceResponse])
async def officer_list_grievances(
    _: Annotated[CurrentUser, Depends(require_role(UserRole.ADMIN, UserRole.AGRI_OFFICER))],
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: Annotated[GrievanceStatus | None, Query(alias="status")] = None,
) -> list[GrievanceResponse]:
    """Officer: list all grievances."""
    grievances = await list_all_grievances(db, status=status_filter)
    return [GrievanceResponse.model_validate(g) for g in grievances]


@officer_router.patch("/grievances/{grievance_id}", response_model=GrievanceResponse)
async def officer_update_grievance(
    grievance_id: Annotated[UUID, Path()],
    payload: GrievanceUpdateRequest,
    officer: Annotated[CurrentUser, Depends(require_role(UserRole.ADMIN, UserRole.AGRI_OFFICER))],
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> GrievanceResponse:
    """Officer: update a grievance's status."""
    updated = await update_grievance(
        db,
        grievance_id,
        status=payload.status,
        resolution=payload.resolution,
        escalation_reference=payload.escalation_reference,
        officer_id=officer.id,
        request=request,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Grievance not found")
    return GrievanceResponse.model_validate(updated)


__all__ = ["officer_router", "router"]
