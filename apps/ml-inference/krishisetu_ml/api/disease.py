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
from krishisetu_ml.core.uploads import read_upload_limited
from krishisetu_ml.models.disease_classifier import (
    get_disease_classifier,
    MIN_CONFIDENCE_THRESHOLD,
)

logger = get_logger(__name__)

# --- Decompression-bomb defence ---------------------------------------------
# Image.open() is lazy: a 4 KB PNG can declare 60000x60000 and only allocate
# ~10 GB later, inside classifier.predict(). Cap what Pillow will decode at
# all, and reject oversized dimensions explicitly right after open().
MAX_IMAGE_PIXELS = 40_000_000  # 40 MP — far above any phone camera photo
MAX_IMAGE_DIMENSION = 10_000  # px, per side
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

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

    # --- Read file contents (streamed; aborts as soon as the limit is hit) ---
    max_size = settings().MAX_IMAGE_SIZE_MB * 1024 * 1024
    contents = await read_upload_limited(file, max_size)

    if not contents:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Empty image file",
        )

    # --- Decode image ---
    try:
        image = Image.open(io.BytesIO(contents))
    except (UnidentifiedImageError, Image.DecompressionBombError) as e:
        logger.warning("predict.decode_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Could not decode image",
        ) from e

    # --- Reject decompression bombs before anything allocates the pixels ---
    width, height = image.size
    if (
        width > MAX_IMAGE_DIMENSION
        or height > MAX_IMAGE_DIMENSION
        or width * height > MAX_IMAGE_PIXELS
    ):
        logger.warning("predict.image_too_large", width=width, height=height)
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"Image dimensions too large: {width}x{height}. "
                f"Max {MAX_IMAGE_DIMENSION}px per side, {MAX_IMAGE_PIXELS} pixels total."
            ),
        )

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
        # Never echo the exception text: it leaks model paths, tensor shapes
        # and execution-provider names. The logger above keeps the details.
        logger.exception("predict.inference_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Inference failed",
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
