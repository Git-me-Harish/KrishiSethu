"""Disease identification routes.

Endpoints:
- POST   /disease-reports/upload-url   — Get pre-signed S3 upload URL
- POST   /disease-reports              — Submit a new disease report
- GET    /disease-reports              — List own reports (paginated)
- GET    /disease-reports/{id}         — Get report with prediction + treatments
- GET    /disease-reports/stats        — Summary stats
- POST   /disease-reports/{id}/feedback — Submit feedback on prediction

- GET    /diseases                     — List disease catalog (public)
- GET    /diseases/{slug}              — Get disease detail with treatments (public)

- GET    /officer/disease-reports      — Officer: list reports needing review
- PATCH  /officer/disease-reports/{id}/review — Officer: submit manual diagnosis
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, status

from krishisetu.core.dependencies import CurrentUser, DBSession, require_permissions
from krishisetu.core.logging import get_logger
from krishisetu.domains.disease import services
from krishisetu.domains.disease.models import DiseaseReportStatus
from krishisetu.domains.disease.schemas import (
    DiseaseFeedbackCreate,
    DiseaseFeedbackResponse,
    DiseaseListResponse,
    DiseaseReportCreate,
    DiseaseReportListResponse,
    DiseaseReportResponse,
    DiseaseReportStatsResponse,
    DiseaseResponse,
    OfficerReviewRequest,
    UploadUrlRequest,
    UploadUrlResponse,
)
from krishisetu.domains.identity.permissions import (
    PERM_DISEASE_REPORT_READ_OWN,
    PERM_DISEASE_REPORT_REVIEW,
    PERM_DISEASE_REPORT_SUBMIT,
)

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Farmer-facing routes
# ---------------------------------------------------------------------------

disease_router = APIRouter(prefix="/disease-reports", tags=["disease"])


@disease_router.post(
    "/upload-url",
    response_model=UploadUrlResponse,
    dependencies=[Depends(require_permissions(PERM_DISEASE_REPORT_SUBMIT))],
)
async def get_upload_url(
    payload: UploadUrlRequest,
    current_user: CurrentUser,
) -> UploadUrlResponse:
    """Get a pre-signed S3 URL for uploading a disease photo.

    Workflow:
    1. Call this endpoint with the content_type of your image
    2. Receive a pre-signed URL and an image_key
    3. PUT your image to the pre-signed URL (direct to S3)
    4. Call POST /disease-reports with the image_key

    The upload URL expires after 15 minutes. Max image size is 10MB.
    """
    return await services.generate_upload_url(
        farmer_id=current_user.id,
        content_type=payload.content_type,
    )


@disease_router.post(
    "",
    response_model=DiseaseReportResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions(PERM_DISEASE_REPORT_SUBMIT))],
)
async def submit_disease_report(
    payload: DiseaseReportCreate,
    current_user: CurrentUser,
    db: DBSession,
) -> DiseaseReportResponse:
    """Submit a new disease report.

    The image must already be uploaded to S3 (use POST /disease-reports/upload-url
    to get an upload URL first).

    The report is created with status=pending, and an async ML inference
    task is dispatched. Poll GET /disease-reports/{id} to check status:
    - pending → processing → completed (prediction available)
    - failed (inference failed, see failure_reason)
    - officer_review (low confidence, sent for manual review)
    """
    return await services.submit_disease_report(
        db, current_user.id, payload
    )


@disease_router.get(
    "/stats",
    response_model=DiseaseReportStatsResponse,
    dependencies=[Depends(require_permissions(PERM_DISEASE_REPORT_READ_OWN))],
)
async def get_report_stats(
    current_user: CurrentUser,
    db: DBSession,
) -> DiseaseReportStatsResponse:
    """Get summary statistics for the current farmer's disease reports."""
    return await services.get_disease_report_stats(db, current_user.id)


@disease_router.get(
    "",
    response_model=DiseaseReportListResponse,
    dependencies=[Depends(require_permissions(PERM_DISEASE_REPORT_READ_OWN))],
)
async def list_my_reports(
    current_user: CurrentUser,
    db: DBSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status_filter: DiseaseReportStatus | None = Query(
        default=None, alias="status", description="Filter by status"
    ),
) -> DiseaseReportListResponse:
    """List the current farmer's disease reports."""
    return await services.list_my_disease_reports(
        db,
        current_user.id,
        status=status_filter,
        page=page,
        page_size=page_size,
    )


@disease_router.get(
    "/{report_id}",
    response_model=DiseaseReportResponse,
    dependencies=[Depends(require_permissions(PERM_DISEASE_REPORT_READ_OWN))],
)
async def get_report(
    report_id: Annotated[UUID, Path()],
    current_user: CurrentUser,
    db: DBSession,
) -> DiseaseReportResponse:
    """Get a disease report by ID with prediction and treatment recommendations.

    If the report is still processing, prediction will be null. Poll this
    endpoint until status='completed'.

    The image_url is a pre-signed S3 URL valid for 15 minutes.
    """
    return await services.get_disease_report(
        db, report_id, farmer_id=current_user.id
    )


@disease_router.post(
    "/{report_id}/feedback",
    response_model=DiseaseFeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions(PERM_DISEASE_REPORT_READ_OWN))],
)
async def submit_feedback(
    report_id: Annotated[UUID, Path()],
    payload: DiseaseFeedbackCreate,
    current_user: CurrentUser,
    db: DBSession,
) -> DiseaseFeedbackResponse:
    """Submit feedback on a disease prediction.

    Helps improve the model over time:
    - correct: prediction was accurate
    - incorrect: prediction was wrong (provide suggested_disease_slug)
    - partially_correct: prediction was partially right
    """
    return await services.submit_feedback(
        db, report_id, current_user.id, payload
    )


# ---------------------------------------------------------------------------
# Disease catalog (public — no auth required)
# ---------------------------------------------------------------------------

diseases_router = APIRouter(prefix="/diseases", tags=["diseases"])


@diseases_router.get("", response_model=DiseaseListResponse)
async def list_diseases(
    db: DBSession,
    crop: str | None = Query(default=None, description="Filter by crop slug, e.g., 'rice'"),
    disease_type: str | None = Query(
        default=None,
        description="Filter by type: fungal, bacterial, viral, pest, nematode, nutrient, environmental",
    ),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> DiseaseListResponse:
    """List diseases in the catalog.

    Public endpoint — does not require authentication.
    Used by the disease result page to display disease information.
    """
    return await services.list_diseases(
        db,
        crop_slug=crop,
        disease_type=disease_type,
        page=page,
        page_size=page_size,
    )


@diseases_router.get("/{slug}", response_model=DiseaseResponse)
async def get_disease(
    slug: Annotated[str, Path()],
    db: DBSession,
) -> DiseaseResponse:
    """Get a disease by slug with full details and treatment recommendations.

    Public endpoint.
    """
    return await services.get_disease(db, slug)


# ---------------------------------------------------------------------------
# Officer routes
# ---------------------------------------------------------------------------

officer_disease_router = APIRouter(
    prefix="/officer/disease-reports",
    tags=["officer"],
    dependencies=[Depends(require_permissions(PERM_DISEASE_REPORT_REVIEW))],
)


@officer_disease_router.get(
    "/review-queue",
    response_model=DiseaseReportListResponse,
)
async def officer_review_queue(
    current_user: CurrentUser,
    db: DBSession,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> DiseaseReportListResponse:
    """List disease reports needing officer review (low-confidence predictions).

    These are reports where the ML model's confidence was below the 70%
    threshold, requiring manual diagnosis by an agricultural officer.
    """
    return await services.officer_list_review_queue(
        db, current_user.id, page=page, page_size=page_size
    )


@officer_disease_router.patch(
    "/{report_id}/review",
    response_model=DiseaseReportResponse,
)
async def officer_review_report(
    report_id: Annotated[UUID, Path()],
    payload: OfficerReviewRequest,
    current_user: CurrentUser,
    db: DBSession,
) -> DiseaseReportResponse:
    """Submit manual diagnosis for a low-confidence disease report.

    The officer's diagnosis replaces the ML prediction as the authoritative
    diagnosis. The report status changes from 'officer_review' to 'reviewed'.
    """
    return await services.officer_review_report(
        db, report_id, current_user.id, payload
    )
