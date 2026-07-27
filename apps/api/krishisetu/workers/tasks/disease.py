"""Disease inference Celery task.

This task is enqueued when a farmer submits a disease report. It:
1. Downloads the uploaded image from S3
2. Calls the ML inference service (/predict/disease endpoint)
3. Stores the prediction in the database with full provenance
4. Updates the report status to 'completed' (or 'failed' / 'officer_review')
5. (Phase 2) Sends a push notification to the farmer

The task is routed to the 'ml-realtime' queue and runs on ML workers
(which may have GPU access). Retries with exponential backoff on transient
failures (network errors, ML service unavailable).

Idempotency: if the same task is run twice (e.g., after worker crash), the
second run will detect the existing prediction and skip inference.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx
from celery import Task
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from krishisetu.core.config import settings
from krishisetu.core.database import AsyncSessionLocal
from krishisetu.core.logging import get_logger
from krishisetu.core.storage import get_storage
from krishisetu.domains.disease.models import (
    DiseasePrediction,
    DiseaseReport,
    DiseaseReportStatus,
)
from krishisetu.workers.celery_app import celery_app

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------


@celery_app.task(
    name="krishisetu.workers.tasks.disease.predict_disease",
    bind=True,  # Pass self (Task instance) as first arg
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def predict_disease(self: Task, report_id: str) -> dict[str, Any]:
    """Run disease inference on a submitted report.

    Args:
        report_id: UUID string of the DiseaseReport to process.

    Returns:
        Dict with prediction summary (for Celery result backend).
    """
    logger.info("disease.task.started", report_id=report_id, task_id=self.request.id)

    try:
        result = asyncio.run(_run_prediction_async(UUID(report_id)))
        logger.info(
            "disease.task.completed",
            report_id=report_id,
            disease=result.get("disease_slug"),
            confidence=result.get("confidence"),
            inference_time_ms=result.get("inference_time_ms"),
        )
        return result
    except Exception as exc:
        logger.error(
            "disease.task.failed",
            report_id=report_id,
            error=str(exc),
            error_type=type(exc).__name__,
            attempt=self.request.retries + 1,
        )

        # Update report status to failed if this was the last retry
        if self.request.retries >= self.max_retries:
            asyncio.run(_mark_report_failed(UUID(report_id), str(exc)))
            return {"status": "failed", "error": str(exc)}

        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=30 * (2 ** self.request.retries)) from exc


# ---------------------------------------------------------------------------
# Async implementation (Celery is sync, so we bridge with asyncio.run)
# ---------------------------------------------------------------------------


async def _run_prediction_async(report_id: UUID) -> dict[str, Any]:
    """Async implementation of the disease prediction task.

    Steps:
    1. Fetch the report from the database
    2. Mark status as 'processing'
    3. Download the image from S3
    4. Call the ML inference service
    5. Store the prediction in the database
    6. Update report status to 'completed' (or 'officer_review')
    """
    async with AsyncSessionLocal() as db:
        # --- 1. Fetch report ---
        report = await _get_report(db, report_id)
        if not report:
            raise ValueError(f"Disease report {report_id} not found")

        # Idempotency check — if already completed, skip
        if report.status == DiseaseReportStatus.COMPLETED:
            logger.info("disease.task.already_completed", report_id=str(report_id))
            return {"status": "already_completed", "report_id": str(report_id)}

        # --- 2. Mark as processing ---
        await _update_report_status(db, report_id, DiseaseReportStatus.PROCESSING)

        # --- 3. Download image from S3 ---
        storage = get_storage()
        try:
            image_bytes = await storage.download_bytes_async(report.image_url)
        except Exception as e:
            await _mark_report_failed(report_id, f"Failed to download image: {e}")
            raise RuntimeError(f"Image download failed: {e}") from e

        if not image_bytes:
            await _mark_report_failed(report_id, "Image is empty")
            raise ValueError("Image is empty")

        # Validate image size
        max_size = (
            settings().MAX_IMAGE_SIZE_MB * 1024 * 1024
            if hasattr(settings(), "MAX_IMAGE_SIZE_MB")
            else 10 * 1024 * 1024
        )
        if len(image_bytes) > max_size:
            await _mark_report_failed(report_id, f"Image too large: {len(image_bytes)} bytes")
            raise ValueError(f"Image exceeds size limit ({len(image_bytes)} > {max_size})")

        # --- 4. Call ML inference service ---
        prediction_data = await _call_inference_service(image_bytes)

        # --- 5. Store prediction in database ---
        await _store_prediction(db, report_id, prediction_data)

        # --- 6. Update report status ---
        is_reliable = prediction_data["top_prediction"]["confidence"] >= 0.70
        new_status = (
            DiseaseReportStatus.COMPLETED if is_reliable
            else DiseaseReportStatus.OFFICER_REVIEW
        )
        await _update_report_status(db, report_id, new_status)

        # Commit the transaction
        await db.commit()

        return {
            "status": "completed",
            "report_id": str(report_id),
            "disease_slug": prediction_data["top_prediction"]["disease_slug"],
            "confidence": prediction_data["top_prediction"]["confidence"],
            "model_version": prediction_data["model_version"],
            "inference_time_ms": prediction_data["inference_time_ms"],
            "is_reliable": is_reliable,
        }


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------


async def _get_report(db: AsyncSession, report_id: UUID) -> DiseaseReport | None:
    """Fetch a disease report by ID."""
    result = await db.execute(
        select(DiseaseReport).where(DiseaseReport.id == report_id)
    )
    return result.scalar_one_or_none()


async def _update_report_status(
    db: AsyncSession, report_id: UUID, status: DiseaseReportStatus
) -> None:
    """Update a report's status."""
    await db.execute(
        update(DiseaseReport)
        .where(DiseaseReport.id == report_id)
        .values(status=status.value, updated_at=datetime.now(UTC))
    )
    await db.flush()


async def _mark_report_failed(report_id: UUID, reason: str) -> None:
    """Mark a report as failed with a reason (separate session)."""
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(DiseaseReport)
            .where(DiseaseReport.id == report_id)
            .values(
                status=DiseaseReportStatus.FAILED.value,
                failure_reason=reason,
                updated_at=datetime.now(UTC),
            )
        )
        await db.commit()
    logger.warning("disease.report.failed", report_id=str(report_id), reason=reason)


async def _store_prediction(
    db: AsyncSession,
    report_id: UUID,
    prediction_data: dict[str, Any],
) -> DiseasePrediction:
    """Store the prediction in the database with full provenance."""
    top = prediction_data["top_prediction"]

    # Convert all_predictions list to JSONB-compatible format
    all_predictions_json = [
        {
            "label": p["label"],
            "confidence": float(p["confidence"]),
            "disease_slug": p["disease_slug"],
        }
        for p in prediction_data["all_predictions"]
    ]

    prediction = DiseasePrediction(
        report_id=report_id,
        disease_slug=top["disease_slug"],
        confidence=Decimal(str(top["confidence"])),
        all_predictions=all_predictions_json,
        model_name=prediction_data["model_name"],
        model_version=prediction_data["model_version"],
        inference_time_ms=prediction_data["inference_time_ms"],
        is_reliable=top["confidence"] >= 0.70,
    )
    db.add(prediction)
    await db.flush()
    return prediction


# ---------------------------------------------------------------------------
# ML service client
# ---------------------------------------------------------------------------


async def _call_inference_service(image_bytes: bytes) -> dict[str, Any]:
    """Call the ML inference service to classify the disease.

    The ML service exposes POST /predict/disease which accepts the image
    as multipart/form-data and returns the prediction.

    Returns:
        Dict with:
        - top_prediction: {label, confidence, disease_slug}
        - all_predictions: list of {label, confidence, disease_slug}
        - model_name: str
        - model_version: str
        - inference_time_ms: int
    """
    ml_url = settings().ML_INFERENCE_URL.rstrip("/")
    endpoint = f"{ml_url}/predict/disease"
    timeout = (
        settings().INFERENCE_TIMEOUT_SECONDS
        if hasattr(settings(), "INFERENCE_TIMEOUT_SECONDS")
        else 30
    )

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.post(
                endpoint,
                files={"file": ("image.jpg", image_bytes, "image/jpeg")},
                headers={
                    "X-ML-Service-Token": settings().ML_SERVICE_TOKEN.get_secret_value()
                },
            )
        except httpx.ConnectError as e:
            raise RuntimeError(f"ML service unavailable at {endpoint}: {e}") from e
        except httpx.TimeoutException as e:
            raise RuntimeError(f"ML service timed out after {timeout}s: {e}") from e

    if response.status_code == 503:
        raise RuntimeError("ML service is overloaded — retry later")
    if response.status_code == 422:
        # Invalid image — don't retry, this is a permanent failure
        error_detail = response.json().get("detail", "Invalid image")
        raise ValueError(f"ML service rejected image: {error_detail}")
    if response.status_code != 200:
        raise RuntimeError(
            f"ML service returned {response.status_code}: {response.text[:200]}"
        )

    data = response.json()

    return {
        "top_prediction": {
            "label": data["top_prediction"]["label"],
            "confidence": float(data["top_prediction"]["confidence"]),
            "disease_slug": data["top_prediction"]["disease_slug"],
        },
        "all_predictions": data["all_predictions"],
        "model_name": data["model_name"],
        "model_version": data["model_version"],
        "inference_time_ms": data["inference_time_ms"],
    }
