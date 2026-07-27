"""Disease domain — business logic services.

Orchestrates:
- Pre-signed URL generation for image uploads
- Disease report creation + Celery task dispatch
- Disease report retrieval with prediction + treatment enrichment
- Farmer feedback submission
- Officer review workflow
- Disease catalog queries
- Stats aggregation

Key flows:
- Submit: GET upload-url -> PUT image to S3 -> POST /disease-reports -> Celery task
- Poll: GET /disease-reports/{id} returns status (pending -> processing -> completed)
- Feedback: POST /disease-reports/{id}/feedback (correct/incorrect)
"""

from __future__ import annotations

import uuid
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from krishisetu.core.exceptions import (
    NotFoundError,
    ValidationError,
)
from krishisetu.core.file_upload_security import (
    FileValidationError,
    UploadContext,
    max_size_for,
    validate_file_bytes,
)
from krishisetu.core.logging import get_logger
from krishisetu.core.storage import get_storage
from krishisetu.domains.disease import repository as repo
from krishisetu.domains.disease.models import (
    DiseaseReportStatus,
    FeedbackType,
)
from krishisetu.domains.disease.schemas import (
    DiseaseFeedbackCreate,
    DiseaseFeedbackResponse,
    DiseaseListItemResponse,
    DiseaseListResponse,
    DiseasePredictionResponse,
    DiseaseReportCreate,
    DiseaseReportListResponse,
    DiseaseReportResponse,
    DiseaseReportStatsResponse,
    DiseaseResponse,
    DiseaseTreatmentResponse,
    OfficerReviewRequest,
    UploadUrlResponse,
)
from krishisetu.domains.farmer import repository as farmer_repo
from krishisetu.domains.farmer.officer_scope import (
    require_within_jurisdiction,
    resolve_officer_jurisdiction,
)
from krishisetu.domains.identity.models import User

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Upload URL generation
# ---------------------------------------------------------------------------


async def generate_upload_url(
    farmer_id: UUID,
    content_type: str = "image/jpeg",
) -> UploadUrlResponse:
    """Generate a pre-signed S3 URL for image upload.

    The farmer uses this URL with HTTP PUT to upload the image directly to
    S3, bypassing the API. The URL expires after 15 minutes.

    Returns the S3 key (which the farmer includes in the subsequent
    POST /disease-reports request) and the upload URL.
    """
    storage = get_storage()

    # Generate a temporary report_id for the S3 key (the actual report
    # is created in POST /disease-reports, which uses this key)
    temp_report_id = uuid.uuid4()
    image_key = storage.disease_report_image_key(
        farmer_id=farmer_id,
        report_id=temp_report_id,
        suffix=_suffix_for_content_type(content_type),
    )

    upload_url = storage.generate_upload_url(
        key=image_key,
        content_type=content_type,
        expires_in=900,  # 15 minutes
        max_size_bytes=max_size_for(UploadContext.DISEASE_IMAGE),
    )

    logger.info(
        "disease.upload_url.generated",
        farmer_id=str(farmer_id),
        image_key=image_key,
    )

    return UploadUrlResponse(
        upload_url=upload_url,
        image_key=image_key,
        expires_in_seconds=900,
        max_size_bytes=10 * 1024 * 1024,
    )


def _validate_own_image_key(image_key: str, farmer_id: UUID) -> None:
    """Reject an image key that does not live under the caller's own prefix.

    Keys are generated as `disease-reports/{farmer_id}/{report_id}/{suffix}`.
    Anything else would let a farmer point a report — and therefore a
    pre-signed download URL — at another user's object.
    """
    expected_prefix = f"disease-reports/{farmer_id}/"
    if (
        not image_key
        or not image_key.startswith(expected_prefix)
        or ".." in image_key
    ):
        raise ValidationError(
            "image_key must be an upload key issued to this account "
            "(disease-reports/{farmer_id}/...)."
        )


def _suffix_for_content_type(content_type: str) -> str:
    """Map content type to file suffix."""
    return {
        "image/jpeg": "original.jpg",
        "image/png": "original.png",
        "image/webp": "original.webp",
    }.get(content_type, "original.jpg")


# ---------------------------------------------------------------------------
# Disease report submission
# ---------------------------------------------------------------------------


async def submit_disease_report(
    db: AsyncSession,
    farmer_id: UUID,
    payload: DiseaseReportCreate,
) -> DiseaseReportResponse:
    """Create a new disease report and dispatch inference task.

    Steps:
    1. Verify the image exists in S3 (defensive — client should have uploaded)
    2. If plot_id provided, verify it belongs to the farmer
    3. If crop_cycle_id provided, verify it belongs to the plot
    4. Create the report (status=pending)
    5. Dispatch Celery task for async inference
    6. Return the report (without prediction yet — client polls)
    """
    storage = get_storage()

    # The image key is client-supplied and ends up in a pre-signed download
    # URL, so it must stay inside the caller's own prefix.
    _validate_own_image_key(payload.image_key, farmer_id)

    # Verify image was uploaded, and that what was uploaded is really an
    # image of an acceptable size (the pre-signed PUT itself cannot enforce
    # either — see core.storage.generate_upload_url).
    size = storage.object_size(payload.image_key)
    if size is None:
        raise ValidationError(
            "Image not found. Please upload the image first using the upload URL."
        )

    max_size = max_size_for(UploadContext.DISEASE_IMAGE)
    if size > max_size:
        storage.delete_object(payload.image_key)
        raise ValidationError(
            f"Image exceeds the {max_size // (1024 * 1024)} MB limit."
        )

    try:
        validate_file_bytes(
            await storage.download_bytes_async(payload.image_key),
            filename=payload.image_key.rsplit("/", 1)[-1],
            context=UploadContext.DISEASE_IMAGE,
        )
    except FileValidationError:
        storage.delete_object(payload.image_key)
        raise

    # Verify plot ownership (if provided)
    if payload.plot_id:
        plot = await farmer_repo.get_plot_by_id(
            db, payload.plot_id, include_boundary=False
        )
        if not plot or plot.farmer_id != farmer_id:
            raise NotFoundError("Plot", str(payload.plot_id))

    # Create the report
    report = await repo.create_disease_report(
        db,
        farmer_id=farmer_id,
        image_url=payload.image_key,
        plot_id=payload.plot_id,
        crop_cycle_id=payload.crop_cycle_id,
        captured_at=payload.captured_at,
        farmer_notes=payload.farmer_notes,
    )

    # Dispatch Celery task for async inference
    # Import here to avoid circular dependency
    from krishisetu.workers.tasks.disease import predict_disease

    task = predict_disease.delay(str(report.id))
    logger.info(
        "disease.report.submitted",
        report_id=str(report.id),
        farmer_id=str(farmer_id),
        task_id=task.id,
    )

    # Generate pre-signed download URL for the response
    image_download_url = storage.generate_download_url(report.image_url)

    return _to_report_response(
        {"report": report, "prediction": None},
        image_url_override=image_download_url,
    )


# ---------------------------------------------------------------------------
# Disease report retrieval
# ---------------------------------------------------------------------------


async def get_disease_report(
    db: AsyncSession,
    report_id: UUID,
    *,
    farmer_id: UUID | None = None,
) -> DiseaseReportResponse:
    """Get a disease report by ID with prediction and treatments.

    If farmer_id is provided, verifies ownership (officers can view any).
    """
    report_dict = await repo.get_disease_report_by_id(db, report_id)
    if not report_dict:
        raise NotFoundError("DiseaseReport", str(report_id))

    if farmer_id and report_dict["farmer_id"] != farmer_id:
        raise NotFoundError("DiseaseReport", str(report_id))  # Don't leak existence

    # Generate pre-signed download URL for the image
    storage = get_storage()
    image_url = storage.generate_download_url(report_dict["image_url"])

    # Enrich prediction with disease info + treatments
    prediction_response = None
    if report_dict.get("prediction"):
        pred = report_dict["prediction"]
        disease = await repo.get_disease_by_slug(db, pred["disease_slug"])
        treatments: list[DiseaseTreatmentResponse] = []
        if disease and disease.treatments:
            treatments = [
                DiseaseTreatmentResponse.model_validate(t)
                for t in sorted(disease.treatments, key=lambda t: (t.priority, t.is_primary))
            ]

        prediction_response = DiseasePredictionResponse(
            id=pred["id"],
            disease_slug=pred["disease_slug"],
            confidence=pred["confidence"],
            all_predictions=pred["all_predictions"],
            model_name=pred["model_name"],
            model_version=pred["model_version"],
            inference_time_ms=pred["inference_time_ms"],
            is_reliable=pred["is_reliable"],
            inferred_at=pred["inferred_at"],
            disease=DiseaseResponse.model_validate(disease) if disease else None,
            treatments=treatments,
        )

    return DiseaseReportResponse(
        id=report_dict["id"],
        farmer_id=report_dict["farmer_id"],
        plot_id=report_dict["plot_id"],
        crop_cycle_id=report_dict["crop_cycle_id"],
        image_url=image_url,
        captured_at=report_dict["captured_at"],
        submitted_at=report_dict["submitted_at"],
        farmer_notes=report_dict["farmer_notes"],
        status=report_dict["status"],
        failure_reason=report_dict["failure_reason"],
        created_at=report_dict["created_at"],
        updated_at=report_dict["updated_at"],
        prediction=prediction_response,
    )


async def list_my_disease_reports(
    db: AsyncSession,
    farmer_id: UUID,
    *,
    status: DiseaseReportStatus | None = None,
    page: int = 1,
    page_size: int = 20,
) -> DiseaseReportListResponse:
    """List the current farmer's disease reports."""
    reports, total = await repo.list_disease_reports_by_farmer(
        db, farmer_id, status=status, page=page, page_size=page_size
    )

    # Generate pre-signed URLs for each report
    storage = get_storage()
    report_responses: list[DiseaseReportResponse] = []
    for r in reports:
        image_url = storage.generate_download_url(r["image_url"])
        report_responses.append(
            DiseaseReportResponse(
                id=r["id"],
                farmer_id=r["farmer_id"],
                plot_id=r["plot_id"],
                crop_cycle_id=r["crop_cycle_id"],
                image_url=image_url,
                captured_at=None,
                submitted_at=r["submitted_at"],
                farmer_notes=r["farmer_notes"],
                status=r["status"],
                failure_reason=None,
                created_at=r["created_at"],
                updated_at=r["created_at"],
                prediction=None,  # List view doesn't include prediction
            )
        )

    return DiseaseReportListResponse(
        reports=report_responses,
        total=total,
        page=page,
        page_size=page_size,
        has_more=(page * page_size) < total,
    )


async def get_disease_report_stats(
    db: AsyncSession, farmer_id: UUID
) -> DiseaseReportStatsResponse:
    """Get summary stats for the farmer's disease reports."""
    stats = await repo.get_farmer_report_stats(db, farmer_id)
    return DiseaseReportStatsResponse(**stats)


# ---------------------------------------------------------------------------
# Disease feedback
# ---------------------------------------------------------------------------


async def submit_feedback(
    db: AsyncSession,
    report_id: UUID,
    farmer_id: UUID,
    payload: DiseaseFeedbackCreate,
) -> DiseaseFeedbackResponse:
    """Submit farmer feedback on a prediction.

    The farmer can mark a prediction as correct, incorrect, or partially
    correct. If incorrect, they can suggest the actual disease.

    This data feeds back into model retraining.
    """
    # Verify report exists and belongs to farmer
    report = await repo.get_disease_report_by_id(
        db, report_id, include_prediction=False
    )
    if not report:
        raise NotFoundError("DiseaseReport", str(report_id))
    if report["farmer_id"] != farmer_id:
        raise NotFoundError("DiseaseReport", str(report_id))

    # Only allow feedback on completed reports
    if report["status"] != DiseaseReportStatus.COMPLETED.value:
        raise ValidationError(
            f"Feedback can only be submitted for completed reports. "
            f"Current status: {report['status']}"
        )

    # Validate suggested_disease_slug exists in catalog (if provided)
    if payload.suggested_disease_slug:
        disease = await repo.get_disease_by_slug(
            db, payload.suggested_disease_slug, include_treatments=False
        )
        if not disease:
            raise ValidationError(
                f"Suggested disease '{payload.suggested_disease_slug}' not found in catalog"
            )

    feedback = await repo.create_feedback(
        db,
        report_id=report_id,
        farmer_id=farmer_id,
        feedback_type=FeedbackType(payload.feedback_type),
        suggested_disease_slug=payload.suggested_disease_slug,
        notes=payload.notes,
    )

    logger.info(
        "disease.feedback.submitted",
        report_id=str(report_id),
        farmer_id=str(farmer_id),
        feedback_type=payload.feedback_type,
    )

    return DiseaseFeedbackResponse.model_validate(feedback)


# ---------------------------------------------------------------------------
# Disease catalog (public)
# ---------------------------------------------------------------------------


async def list_diseases(
    db: AsyncSession,
    *,
    crop_slug: str | None = None,
    disease_type: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> DiseaseListResponse:
    """List diseases with optional filters."""
    diseases, total = await repo.list_diseases(
        db,
        crop_slug=crop_slug,
        disease_type=disease_type,
        page=page,
        page_size=page_size,
    )
    return DiseaseListResponse(
        diseases=[DiseaseListItemResponse.model_validate(d) for d in diseases],
        total=total,
    )


async def get_disease(db: AsyncSession, slug: str) -> DiseaseResponse:
    """Get a disease by slug with treatments."""
    disease = await repo.get_disease_by_slug(db, slug, include_treatments=True)
    if not disease:
        raise NotFoundError("Disease", slug)
    return DiseaseResponse.model_validate(disease)


# ---------------------------------------------------------------------------
# Officer review
# ---------------------------------------------------------------------------


async def officer_list_review_queue(
    db: AsyncSession,
    officer: User,
    *,
    page: int = 1,
    page_size: int = 20,
) -> DiseaseReportListResponse:
    """List reports needing review, scoped to the officer's own district."""
    jurisdiction = resolve_officer_jurisdiction(officer)

    reports, total = await repo.list_reports_for_officer_review(
        db,
        district=jurisdiction.district if jurisdiction else None,
        state=jurisdiction.state if jurisdiction else None,
        page=page,
        page_size=page_size,
    )

    storage = get_storage()
    report_responses: list[DiseaseReportResponse] = []
    for r in reports:
        image_url = storage.generate_download_url(r["image_url"])
        report_responses.append(
            DiseaseReportResponse(
                id=r["id"],
                farmer_id=r["farmer_id"],
                plot_id=r["plot_id"],
                crop_cycle_id=r.get("crop_cycle_id"),
                image_url=image_url,
                captured_at=None,
                submitted_at=r["submitted_at"],
                farmer_notes=r["farmer_notes"],
                status=r["status"],
                failure_reason=None,
                created_at=r["created_at"],
                updated_at=r["created_at"],
                prediction=None,
            )
        )

    return DiseaseReportListResponse(
        reports=report_responses,
        total=total,
        page=page,
        page_size=page_size,
        has_more=(page * page_size) < total,
    )


async def officer_review_report(
    db: AsyncSession,
    report_id: UUID,
    officer: User,
    payload: OfficerReviewRequest,
) -> DiseaseReportResponse:
    """Officer submits manual diagnosis for a report in their own district."""
    officer_id = officer.id

    report_dict = await repo.get_disease_report_by_id(db, report_id)
    if not report_dict:
        raise NotFoundError("DiseaseReport", str(report_id))

    jurisdiction = resolve_officer_jurisdiction(officer)
    if jurisdiction is not None:
        plot_id = report_dict.get("plot_id")
        plot = (
            await farmer_repo.get_plot_by_id(db, plot_id, include_boundary=False)
            if plot_id
            else None
        )
        if not plot:
            # No plot on the report — fall back to the farmer's own district.
            in_district = await farmer_repo.farmer_has_plot_in_district(
                db,
                report_dict["farmer_id"],
                jurisdiction.district,
                jurisdiction.state,
            )
            if not in_district:
                raise NotFoundError("DiseaseReport", str(report_id))
        else:
            require_within_jurisdiction(
                jurisdiction, state=plot.state, district=plot.district
            )

    # Validate disease_slug if provided
    if payload.disease_slug:
        disease = await repo.get_disease_by_slug(
            db, payload.disease_slug, include_treatments=False
        )
        if not disease:
            raise ValidationError(
                f"Disease '{payload.disease_slug}' not found in catalog"
            )

    report = await repo.officer_review_report(
        db,
        report_id,
        officer_id,
        payload.diagnosis,
        payload.disease_slug,
    )
    if not report:
        raise NotFoundError("DiseaseReport", str(report_id))

    logger.info(
        "disease.officer_reviewed",
        report_id=str(report_id),
        officer_id=str(officer_id),
        disease_slug=payload.disease_slug,
    )

    return await get_disease_report(db, report_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_report_response(
    data: dict[str, Any],
    *,
    image_url_override: str | None = None,
) -> DiseaseReportResponse:
    """Convert a report dict to a DiseaseReportResponse."""
    report = data["report"]
    return DiseaseReportResponse(
        id=report.id,
        farmer_id=report.farmer_id,
        plot_id=report.plot_id,
        crop_cycle_id=report.crop_cycle_id,
        image_url=image_url_override or report.image_url,
        captured_at=report.captured_at,
        submitted_at=report.submitted_at,
        farmer_notes=report.farmer_notes,
        status=report.status,
        failure_reason=getattr(report, "failure_reason", None),
        created_at=report.created_at,
        updated_at=report.updated_at,
        prediction=None,
    )
