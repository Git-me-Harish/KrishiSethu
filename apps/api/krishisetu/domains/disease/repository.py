"""Database access layer for the disease domain.

Handles:
- Disease catalog queries (list, get by slug, with treatments)
- Disease report CRUD (create, list, get by ID with prediction)
- Disease prediction storage (with full provenance)
- Disease feedback storage
- Officer review workflow
- Stats aggregation
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from krishisetu.domains.disease.models import (
    Disease,
    DiseaseFeedback,
    DiseasePrediction,
    DiseaseReport,
    DiseaseReportStatus,
    FeedbackType,
)

# ---------------------------------------------------------------------------
# Disease catalog queries
# ---------------------------------------------------------------------------


async def list_diseases(
    db: AsyncSession,
    *,
    crop_slug: str | None = None,
    disease_type: str | None = None,
    is_active: bool = True,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[Disease], int]:
    """List diseases with optional filters."""
    query = select(Disease).where(Disease.is_active == is_active)
    count_query = select(func.count(Disease.id)).where(Disease.is_active == is_active)

    if crop_slug:
        query = query.where(Disease.affected_crops.contains([crop_slug]))
        count_query = count_query.where(Disease.affected_crops.contains([crop_slug]))

    if disease_type:
        query = query.where(Disease.disease_type == disease_type)
        count_query = count_query.where(Disease.disease_type == disease_type)

    total = (await db.execute(count_query)).scalar_one()

    offset = (page - 1) * page_size
    query = query.order_by(Disease.name_en).offset(offset).limit(page_size)
    result = await db.execute(query)
    return list(result.scalars().all()), total


async def get_disease_by_slug(
    db: AsyncSession,
    slug: str,
    *,
    include_treatments: bool = True,
) -> Disease | None:
    """Fetch a disease by slug, optionally with treatments."""
    query = select(Disease).where(Disease.slug == slug)
    if include_treatments:
        query = query.options(selectinload(Disease.treatments))
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def get_diseases_by_slugs(
    db: AsyncSession,
    slugs: list[str],
) -> dict[str, Disease]:
    """Fetch multiple diseases by slug (returns slug -> Disease dict)."""
    if not slugs:
        return {}
    query = (
        select(Disease)
        .where(Disease.slug.in_(slugs))
        .options(selectinload(Disease.treatments))
    )
    result = await db.execute(query)
    return {d.slug: d for d in result.scalars().all()}


# ---------------------------------------------------------------------------
# Disease report queries
# ---------------------------------------------------------------------------


async def create_disease_report(
    db: AsyncSession,
    *,
    farmer_id: UUID,
    image_url: str,
    plot_id: UUID | None = None,
    crop_cycle_id: UUID | None = None,
    captured_at: datetime | None = None,
    farmer_notes: str | None = None,
    image_metadata: dict[str, Any] | None = None,
) -> DiseaseReport:
    """Create a new disease report (status=pending)."""
    report = DiseaseReport(
        farmer_id=farmer_id,
        image_url=image_url,
        plot_id=plot_id,
        crop_cycle_id=crop_cycle_id,
        captured_at=captured_at,
        farmer_notes=farmer_notes,
        image_metadata=image_metadata,
        status=DiseaseReportStatus.PENDING,
    )
    db.add(report)
    await db.flush()
    await db.refresh(report)
    return report


async def get_disease_report_by_id(
    db: AsyncSession,
    report_id: UUID,
) -> dict[str, Any] | None:
    """Fetch a disease report by ID with prediction (if available)."""
    query = text("""
        SELECT r.id, r.farmer_id, r.plot_id, r.crop_cycle_id,
               r.image_url, r.image_thumbnail_url, r.image_metadata,
               r.captured_at, r.submitted_at, r.farmer_notes,
               r.status, r.failure_reason,
               r.reviewed_by, r.reviewed_at, r.officer_diagnosis,
               r.created_at, r.updated_at,
               p.id as prediction_id, p.disease_slug, p.confidence,
               p.all_predictions, p.model_name, p.model_version,
               p.inference_time_ms, p.is_reliable, p.inferred_at,
               p.heat_map_url
        FROM intelligence.disease_reports r
        LEFT JOIN intelligence.disease_predictions p ON p.report_id = r.id
        WHERE r.id = :report_id
    """)
    result = await db.execute(query, {"report_id": report_id})
    row = result.fetchone()
    if not row:
        return None
    return _row_to_report_dict(row)


async def list_disease_reports_by_farmer(
    db: AsyncSession,
    farmer_id: UUID,
    *,
    status: DiseaseReportStatus | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    """List a farmer's disease reports with optional status filter."""
    count_query = (
        select(func.count(DiseaseReport.id))
        .where(DiseaseReport.farmer_id == farmer_id)
    )
    if status:
        count_query = count_query.where(DiseaseReport.status == status)
    total = (await db.execute(count_query)).scalar_one()

    offset = (page - 1) * page_size

    base_query = """
        SELECT r.id, r.farmer_id, r.plot_id, r.crop_cycle_id,
               r.image_url, r.submitted_at, r.status, r.farmer_notes,
               r.created_at,
               p.disease_slug, p.confidence, p.is_reliable
        FROM intelligence.disease_reports r
        LEFT JOIN intelligence.disease_predictions p ON p.report_id = r.id
        WHERE r.farmer_id = :farmer_id
    """
    params: dict[str, Any] = {
        "farmer_id": farmer_id,
        "limit": page_size,
        "offset": offset,
    }
    if status:
        base_query += " AND r.status = :status"
        params["status"] = status.value

    query = text(
        base_query + " ORDER BY r.created_at DESC LIMIT :limit OFFSET :offset"
    )
    result = await db.execute(query, params)
    reports = [_row_to_list_item_dict(row) for row in result.fetchall()]
    return reports, total


async def list_reports_for_officer_review(
    db: AsyncSession,
    *,
    district: str | None = None,
    state: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    """List disease reports needing officer review (low confidence).

    When `district`/`state` are given, only reports on plots in that district
    are returned (None = unrestricted, admin only).
    """
    params: dict[str, Any] = {"limit": page_size, "offset": (page - 1) * page_size}
    district_clause = ""
    if district and state:
        district_clause = "AND pl.district = :district AND pl.state = :state"
        params["district"] = district
        params["state"] = state

    # district_clause is a fixed "AND col = :param" fragment; values are
    # always bound via params, never interpolated directly into the SQL text.
    count_query = text(f"""
        SELECT COUNT(*)
        FROM intelligence.disease_reports r
        LEFT JOIN farmer.plots pl ON pl.id = r.plot_id
        WHERE r.status = 'officer_review'
        {district_clause}
    """)  # noqa: S608
    count_params = {k: v for k, v in params.items() if k not in ("limit", "offset")}
    total = (await db.execute(count_query, count_params)).scalar_one()

    query = text(f"""
        SELECT r.id, r.farmer_id, r.plot_id, r.crop_cycle_id, r.image_url,
               r.submitted_at, r.status, r.farmer_notes, r.created_at,
               p.disease_slug, p.confidence, p.is_reliable,
               u.full_name as farmer_name, u.phone as farmer_phone,
               pl.village, pl.district
        FROM intelligence.disease_reports r
        LEFT JOIN intelligence.disease_predictions p ON p.report_id = r.id
        JOIN identity.users u ON u.id = r.farmer_id
        LEFT JOIN farmer.plots pl ON pl.id = r.plot_id
        WHERE r.status = 'officer_review'
        {district_clause}
        ORDER BY r.created_at ASC
        LIMIT :limit OFFSET :offset
    """)
    result = await db.execute(query, params)
    reports = [_row_to_officer_list_item_dict(row) for row in result.fetchall()]
    return reports, total


async def update_report_status(
    db: AsyncSession,
    report_id: UUID,
    status: DiseaseReportStatus,
    failure_reason: str | None = None,
) -> None:
    """Update a report's status (used by Celery task)."""
    values: dict[str, Any] = {
        "status": status.value,
        "updated_at": datetime.utcnow(),
    }
    if failure_reason:
        values["failure_reason"] = failure_reason

    await db.execute(
        update(DiseaseReport)
        .where(DiseaseReport.id == report_id)
        .values(**values)
    )
    await db.flush()


async def officer_review_report(
    db: AsyncSession,
    report_id: UUID,
    officer_id: UUID,
    diagnosis: str,
    disease_slug: str | None = None,
) -> dict[str, Any] | None:
    """Officer submits manual diagnosis for a low-confidence report."""
    await db.execute(
        update(DiseaseReport)
        .where(DiseaseReport.id == report_id)
        .values(
            status=DiseaseReportStatus.REVIEWED.value,
            reviewed_by=officer_id,
            reviewed_at=datetime.utcnow(),
            officer_diagnosis=diagnosis,
            updated_at=datetime.utcnow(),
        )
    )
    await db.flush()
    return await get_disease_report_by_id(db, report_id)


# ---------------------------------------------------------------------------
# Disease prediction queries
# ---------------------------------------------------------------------------


async def store_prediction(
    db: AsyncSession,
    *,
    report_id: UUID,
    disease_slug: str,
    confidence: float | Decimal,
    all_predictions: list[dict[str, Any]],
    model_name: str,
    model_version: str,
    inference_time_ms: int,
    is_reliable: bool,
    heat_map_url: str | None = None,
) -> DiseasePrediction:
    """Store a prediction with full provenance."""
    prediction = DiseasePrediction(
        report_id=report_id,
        disease_slug=disease_slug,
        confidence=Decimal(str(confidence)),
        all_predictions=all_predictions,
        model_name=model_name,
        model_version=model_version,
        inference_time_ms=inference_time_ms,
        is_reliable=is_reliable,
        heat_map_url=heat_map_url,
    )
    db.add(prediction)
    await db.flush()
    await db.refresh(prediction)
    return prediction


async def get_prediction_by_report(
    db: AsyncSession, report_id: UUID
) -> DiseasePrediction | None:
    """Fetch the prediction for a report (one-to-one)."""
    result = await db.execute(
        select(DiseasePrediction).where(DiseasePrediction.report_id == report_id)
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Disease feedback queries
# ---------------------------------------------------------------------------


async def create_feedback(
    db: AsyncSession,
    *,
    report_id: UUID,
    farmer_id: UUID,
    feedback_type: FeedbackType,
    suggested_disease_slug: str | None = None,
    notes: str | None = None,
) -> DiseaseFeedback:
    """Store farmer feedback on a prediction."""
    feedback = DiseaseFeedback(
        report_id=report_id,
        farmer_id=farmer_id,
        feedback_type=feedback_type,
        suggested_disease_slug=suggested_disease_slug,
        notes=notes,
    )
    db.add(feedback)
    await db.flush()
    await db.refresh(feedback)
    return feedback


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


async def get_farmer_report_stats(
    db: AsyncSession, farmer_id: UUID
) -> dict[str, Any]:
    """Get summary statistics for a farmer's disease reports."""
    query = text("""
        SELECT
            COUNT(*) as total_reports,
            COUNT(*) FILTER (WHERE status = 'completed') as completed,
            COUNT(*) FILTER (WHERE status IN ('pending', 'processing')) as pending,
            COUNT(*) FILTER (WHERE status = 'failed') as failed,
            COUNT(*) FILTER (WHERE status = 'officer_review') as needs_review
        FROM intelligence.disease_reports
        WHERE farmer_id = :farmer_id
    """)
    result = await db.execute(query, {"farmer_id": farmer_id})
    row = result.fetchone()

    disease_query = text("""
        SELECT p.disease_slug, COUNT(*) as count
        FROM intelligence.disease_predictions p
        JOIN intelligence.disease_reports r ON r.id = p.report_id
        WHERE r.farmer_id = :farmer_id AND r.status = 'completed'
        GROUP BY p.disease_slug
    """)
    disease_result = await db.execute(disease_query, {"farmer_id": farmer_id})
    by_disease = {row[0]: row[1] for row in disease_result.fetchall()}

    return {
        "total_reports": row[0] or 0,
        "completed": row[1] or 0,
        "pending": row[2] or 0,
        "failed": row[3] or 0,
        "needs_review": row[4] or 0,
        "by_disease": by_disease,
    }


# ---------------------------------------------------------------------------
# Row mappers (private)
# ---------------------------------------------------------------------------


def _row_to_report_dict(row: Any) -> dict[str, Any]:
    """Convert a row (with prediction join) to a disease report dict."""
    data: dict[str, Any] = {
        "id": row.id,
        "farmer_id": row.farmer_id,
        "plot_id": row.plot_id,
        "crop_cycle_id": row.crop_cycle_id,
        "image_url": row.image_url,
        "image_thumbnail_url": getattr(row, "image_thumbnail_url", None),
        "image_metadata": getattr(row, "image_metadata", None),
        "captured_at": row.captured_at,
        "submitted_at": row.submitted_at,
        "farmer_notes": row.farmer_notes,
        "status": row.status,
        "failure_reason": getattr(row, "failure_reason", None),
        "reviewed_by": getattr(row, "reviewed_by", None),
        "reviewed_at": getattr(row, "reviewed_at", None),
        "officer_diagnosis": getattr(row, "officer_diagnosis", None),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }

    if hasattr(row, "prediction_id") and row.prediction_id:
        all_preds = row.all_predictions
        if isinstance(all_preds, str):
            try:
                all_preds = json.loads(all_preds)
            except Exception:
                all_preds = []
        elif all_preds is None:
            all_preds = []

        data["prediction"] = {
            "id": row.prediction_id,
            "disease_slug": row.disease_slug,
            "confidence": Decimal(str(row.confidence)) if row.confidence else None,
            "all_predictions": all_preds,
            "model_name": row.model_name,
            "model_version": row.model_version,
            "inference_time_ms": row.inference_time_ms,
            "is_reliable": row.is_reliable,
            "inferred_at": row.inferred_at,
            "heat_map_url": getattr(row, "heat_map_url", None),
        }
    else:
        data["prediction"] = None

    return data


def _row_to_list_item_dict(row: Any) -> dict[str, Any]:
    """Convert a row to a list-item dict."""
    return {
        "id": row.id,
        "farmer_id": row.farmer_id,
        "plot_id": row.plot_id,
        "crop_cycle_id": getattr(row, "crop_cycle_id", None),
        "image_url": row.image_url,
        "submitted_at": row.submitted_at,
        "status": row.status,
        "farmer_notes": row.farmer_notes,
        "created_at": row.created_at,
        "disease_slug": getattr(row, "disease_slug", None),
        "confidence": (
            Decimal(str(row.confidence))
            if hasattr(row, "confidence") and row.confidence is not None
            else None
        ),
        "is_reliable": getattr(row, "is_reliable", None),
    }


def _row_to_officer_list_item_dict(row: Any) -> dict[str, Any]:
    """Convert a row to an officer worklist item."""
    base = _row_to_list_item_dict(row)
    base.update({
        "farmer_name": getattr(row, "farmer_name", None),
        "farmer_phone": getattr(row, "farmer_phone", None),
        "village": getattr(row, "village", None),
        "district": getattr(row, "district", None),
    })
    return base
