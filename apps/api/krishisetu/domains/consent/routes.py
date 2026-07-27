"""Consent domain routes.

Endpoints:
- GET    /consent              — current consent status (granted / withdrawn / not asked)
- GET    /consent/history      — full consent history (granted + withdrawn)
- POST   /consent/grant        — grant consent for one or more purposes
- POST   /consent/withdraw     — withdraw consent for one or more purposes
- GET    /consent/notices      — list active consent notices (one per purpose)
- GET    /consent/notices/{purpose}  — get the active notice for a specific purpose

All endpoints require authentication (the consent state is per-user).
Admins can additionally query any user's consent via /admin/consent/{user_id}.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Request
from sqlalchemy.ext.asyncio import AsyncSession

from krishisetu.core.database import get_db
from krishisetu.core.dependencies import CurrentUser, require_role
from krishisetu.domains.consent.models import ConsentPurpose
from krishisetu.domains.consent.schemas import (
    ConsentGrantRequest,
    ConsentRecord,
    ConsentStatusResponse,
    ConsentWithdrawRequest,
)
from krishisetu.domains.consent.services import (
    get_consent_status,
    grant_consent,
    list_consent_history,
    withdraw_consent,
)
from krishisetu.domains.identity.models import UserRole

router = APIRouter(prefix="/consent", tags=["consent"])


@router.get("", response_model=ConsentStatusResponse)
async def get_my_consent_status(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConsentStatusResponse:
    """Get the current user's consent state across all purposes."""
    return await get_consent_status(db, current_user.id)


@router.get("/history", response_model=list[ConsentRecord])
async def get_my_consent_history(
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ConsentRecord]:
    """Get the current user's full consent history (granted + withdrawn)."""
    records = await list_consent_history(db, current_user.id)
    return [ConsentRecord.model_validate(r) for r in records]


@router.post("/grant", response_model=list[ConsentRecord], status_code=201)
async def grant_my_consent(
    payload: ConsentGrantRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> list[ConsentRecord]:
    """Grant consent for one or more purposes."""
    created = await grant_consent(
        db,
        current_user.id,
        payload,
        request=request,
        actor_id=current_user.id,
    )
    return [ConsentRecord.model_validate(c) for c in created]


@router.post("/withdraw", response_model=list[ConsentRecord])
async def withdraw_my_consent(
    payload: ConsentWithdrawRequest,
    current_user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    request: Request,
) -> list[ConsentRecord]:
    """Withdraw consent for one or more purposes.

    Note: withdrawing consent for a purpose may disable related features
    immediately. For example, withdrawing `disease_diagnosis` will prevent
    new disease report submissions until consent is re-granted.
    """
    withdrawn = await withdraw_consent(
        db,
        current_user.id,
        payload,
        request=request,
        actor_id=current_user.id,
    )
    return [ConsentRecord.model_validate(w) for w in withdrawn]


# ---------------------------------------------------------------------------
# Admin endpoints — query any user's consent state
# ---------------------------------------------------------------------------

admin_router = APIRouter(prefix="/admin/consent", tags=["admin"])


@admin_router.get("/{user_id}", response_model=ConsentStatusResponse)
async def get_user_consent_status(
    user_id: Annotated[UUID, Path()],
    _: Annotated[CurrentUser, Depends(require_role(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConsentStatusResponse:
    """Admin: get any user's consent status."""
    return await get_consent_status(db, user_id)


@admin_router.get("/{user_id}/history", response_model=list[ConsentRecord])
async def get_user_consent_history(
    user_id: Annotated[UUID, Path()],
    _: Annotated[CurrentUser, Depends(require_role(UserRole.ADMIN))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ConsentRecord]:
    """Admin: get any user's full consent history."""
    records = await list_consent_history(db, user_id)
    return [ConsentRecord.model_validate(r) for r in records]


__all__ = ["ConsentPurpose", "admin_router", "router"]
