"""Schemes routes.

Endpoints:
Public (no auth):
- GET /schemes                    — List schemes (public catalog)
- GET /schemes/{code}             — Get scheme detail by code

Farmer (require auth):
- GET  /schemes/eligible          — List schemes with eligibility check for current user
- GET  /schemes/stats             — Scheme application stats
- POST /schemes/applications      — Create application (draft)
- GET  /schemes/applications      — List own applications
- GET  /schemes/applications/{id} — Get application detail
- POST /schemes/applications/{id}/submit   — Submit application
- POST /schemes/applications/{id}/withdraw — Withdraw application

Officer:
- GET   /officer/schemes/applications         — List applications for review
- PATCH /officer/schemes/applications/{id}/review — Review application
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, status

from krishisetu.core.dependencies import (
    CurrentUser,
    CurrentUserOptional,
    DBSession,
    require_permissions,
)
from krishisetu.core.logging import get_logger
from krishisetu.domains.identity.permissions import (
    PERM_SCHEME_APPLICATION_REVIEW,
    PERM_SCHEME_APPLY,
    PERM_SCHEME_BROWSE,
)
from krishisetu.domains.schemes import services
from krishisetu.domains.schemes.models import ApplicationStatus
from krishisetu.domains.schemes.schemas import (
    OfficerReviewRequest,
    SchemeApplicationCreate,
    SchemeApplicationListResponse,
    SchemeApplicationResponse,
    SchemeApplicationSubmit,
    SchemeListResponse,
    SchemeResponse,
    SchemeStatsResponse,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Public scheme catalog routes
# ---------------------------------------------------------------------------

schemes_router = APIRouter(prefix="/schemes", tags=["schemes"])


@schemes_router.get("", response_model=SchemeListResponse)
async def list_schemes(
    db: DBSession,
    current_user: CurrentUserOptional,
    category: str | None = Query(default=None, description="Filter by category"),
    state: str | None = Query(default=None, description="Filter by state"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> SchemeListResponse:
    """List available government schemes.

    Public endpoint — no auth required. If authenticated, eligibility is
    evaluated for each scheme and annotated in the response.
    """
    farmer_id = current_user.id if current_user else None
    return await services.list_schemes(
        db, farmer_id, category=category, state=state, page=page, page_size=page_size
    )


@schemes_router.get("/stats", response_model=SchemeStatsResponse,
                     dependencies=[Depends(require_permissions(PERM_SCHEME_BROWSE))])
async def get_scheme_stats(
    current_user: CurrentUser,
    db: DBSession,
) -> SchemeStatsResponse:
    """Get scheme stats for the current farmer."""
    return await services.get_scheme_stats(db, current_user.id)


@schemes_router.get("/{scheme_code}", response_model=SchemeResponse)
async def get_scheme(
    scheme_code: Annotated[str, Path()],
    db: DBSession,
    current_user: CurrentUserOptional,
) -> SchemeResponse:
    """Get scheme detail by code.

    Public endpoint. If authenticated, eligibility is evaluated.
    """
    from krishisetu.domains.schemes import repository as repo

    scheme = await repo.get_scheme_by_code(db, scheme_code)
    if not scheme:
        from krishisetu.core.exceptions import NotFoundError
        raise NotFoundError("Scheme", scheme_code)

    farmer_id = current_user.id if current_user else None
    return await services.get_scheme(db, scheme.id, farmer_id)


# ---------------------------------------------------------------------------
# Farmer application routes
# ---------------------------------------------------------------------------

@schemes_router.post(
    "/applications",
    response_model=SchemeApplicationResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions(PERM_SCHEME_APPLY))],
)
async def create_application(
    payload: SchemeApplicationCreate,
    current_user: CurrentUser,
    db: DBSession,
) -> SchemeApplicationResponse:
    """Create a new scheme application (draft).

    The platform automatically:
    1. Compiles a snapshot of the farmer's profile
    2. Evaluates eligibility rules
    3. Stores the eligibility result

    The farmer can review the auto-compiled data, add additional fields,
    then submit via POST /schemes/applications/{id}/submit.
    """
    return await services.create_application(db, current_user.id, payload)


@schemes_router.get(
    "/applications",
    response_model=SchemeApplicationListResponse,
    dependencies=[Depends(require_permissions(PERM_SCHEME_BROWSE))],
)
async def list_my_applications(
    current_user: CurrentUser,
    db: DBSession,
    status_filter: ApplicationStatus | None = Query(
        default=None, alias="status", description="Filter by status"
    ),
) -> SchemeApplicationListResponse:
    """List the farmer's scheme applications."""
    return await services.list_my_applications(
        db, current_user.id, status=status_filter
    )


@schemes_router.get(
    "/applications/{app_id}",
    response_model=SchemeApplicationResponse,
    dependencies=[Depends(require_permissions(PERM_SCHEME_BROWSE))],
)
async def get_application(
    app_id: Annotated[UUID, Path()],
    current_user: CurrentUser,
    db: DBSession,
) -> SchemeApplicationResponse:
    """Get an application by ID."""
    return await services.get_application(db, app_id, current_user.id)


@schemes_router.post(
    "/applications/{app_id}/submit",
    response_model=SchemeApplicationResponse,
    dependencies=[Depends(require_permissions(PERM_SCHEME_APPLY))],
)
async def submit_application(
    app_id: Annotated[UUID, Path()],
    payload: SchemeApplicationSubmit,
    current_user: CurrentUser,
    db: DBSession,
) -> SchemeApplicationResponse:
    """Submit a draft application for review.

    Re-evaluates eligibility at submission time (farmer data may have changed
    since the draft was created).
    """
    return await services.submit_application(db, app_id, current_user.id, payload)


@schemes_router.post(
    "/applications/{app_id}/withdraw",
    response_model=SchemeApplicationResponse,
    dependencies=[Depends(require_permissions(PERM_SCHEME_APPLY))],
)
async def withdraw_application(
    app_id: Annotated[UUID, Path()],
    current_user: CurrentUser,
    db: DBSession,
) -> SchemeApplicationResponse:
    """Withdraw an application."""
    return await services.withdraw_application(db, app_id, current_user.id)


# ---------------------------------------------------------------------------
# Officer routes
# ---------------------------------------------------------------------------

officer_router = APIRouter(
    prefix="/officer/schemes",
    tags=["officer"],
    dependencies=[Depends(require_permissions(PERM_SCHEME_APPLICATION_REVIEW))],
)


@officer_router.get(
    "/applications",
    response_model=SchemeApplicationListResponse,
)
async def officer_list_applications(
    current_user: CurrentUser,
    db: DBSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: ApplicationStatus | None = Query(
        default=None, alias="status", description="Filter by status"
    ),
) -> SchemeApplicationListResponse:
    """List scheme applications for officer review (officer's district only)."""
    return await services.officer_list_applications(
        db, current_user, status=status_filter, page=page, page_size=page_size
    )


@officer_router.patch(
    "/applications/{app_id}/review",
    response_model=SchemeApplicationResponse,
)
async def officer_review_application(
    app_id: Annotated[UUID, Path()],
    payload: OfficerReviewRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> SchemeApplicationResponse:
    """Review a scheme application (approve, reject, request_resubmission, disburse)."""
    return await services.officer_review_application(
        db, app_id, current_user, payload
    )
