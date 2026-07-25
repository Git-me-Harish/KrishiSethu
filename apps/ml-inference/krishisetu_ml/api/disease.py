"""Disease prediction endpoint.

POST /predict/disease
- Accepts an image file (multipart/form-data)
- Runs YOLOv8 disease classification
- Returns top prediction + full distribution + model provenance
"""

from __future__ import annotations

import io
import time
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field

from krishisetu_ml.core.config import settings
from krishisetu_ml.core.logging import get_logger
from krishisetu_ml.models.disease_classifier import (
    get_disease_classifier,
    MIN_CONFIDENCE_THRESHOLD,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/predict", tags=["inference"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class PredictionItem(BaseModel):
    """A single disease prediction."""

    label: str = Field(..., description="Human-readable class label")
    confidence: float = Field(..., description="Confidence score [0, 1]")
    disease_slug: str = Field(..., description="URL-friendly slug matching catalog")


class DiseasePredictionResponse(BaseModel):
    """Full prediction response."""

    top_prediction: PredictionItem
    all_predictions: list[PredictionItem]
    model_name: str
    model_version: str
    inference_time_ms: int
    is_reliable: bool = Field(
        ..., description="True if confidence >= 0.70 threshold"
    )
    min_confidence_threshold: float = MIN_CONFIDENCE_THRESHOLD


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post(
    "/disease",
    response_model=DiseasePredictionResponse,
    status_code=status.HTTP_200_OK,
)
async def predict_disease(
    file: UploadFile = File(
        ...,
        description="Image file (JPEG, PNG, or WebP). Max 10MB.",
    ),
) -> DiseasePredictionResponse:
    """Classify a crop disease from a leaf photo.

    The image is preprocessed (resized to 640x640, normalized) and passed
    through a YOLOv8 classification model. The output is softmax-calibrated
    with temperature scaling for reliable confidence scores.

    Returns the top prediction plus the full class distribution (top-5).
    """
    start_time = time.perf_counter()

    # --- Validate content type ---
    allowed_types = {"image/jpeg", "image/png", "image/webp"}
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported content type: {file.content_type}. "
            f"Allowed: {', '.join(sorted(allowed_types))}",
        )

    # --- Read file contents ---
    contents = await file.read()
    max_size = settings().MAX_IMAGE_SIZE_MB * 1024 * 1024
    if len(contents) > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image too large: {len(contents)} bytes. Max: {max_size} bytes.",
        )

    if not contents:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Empty image file",
        )

    # --- Decode image ---
    try:
        image = Image.open(io.BytesIO(contents))
    except UnidentifiedImageError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not decode image: {e}",
        ) from e

    # --- Run inference ---
    try:
        classifier = get_disease_classifier()
        result = classifier.predict(image)
    except FileNotFoundError as e:
        logger.error("predict.model_not_found", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Model not loaded. Service may be starting up.",
        ) from e
    except Exception as e:
        logger.exception("predict.inference_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Inference failed: {e}",
        ) from e

    total_time_ms = int((time.perf_counter() - start_time) * 1000)

    logger.info(
        "predict.completed",
        top_label=result.top_prediction.label,
        top_confidence=result.top_prediction.confidence,
        is_reliable=result.is_reliable,
        model_version=result.model_version,
        inference_time_ms=result.inference_time_ms,
        total_time_ms=total_time_ms,
    )

    # Convert to response schema
    all_predictions = [
        PredictionItem(
            label=p.label,
            confidence=p.confidence,
            disease_slug=p.disease_slug,
        )
        for p in result.all_predictions
    ]

    return DiseasePredictionResponse(
        top_prediction=PredictionItem(
            label=result.top_prediction.label,
            confidence=result.top_prediction.confidence,
            disease_slug=result.top_prediction.disease_slug,
        ),
        all_predictions=all_predictions,
        model_name=result.model_name,
        model_version=result.model_version,
        inference_time_ms=result.inference_time_ms,
        is_reliable=result.is_reliable,
    )
