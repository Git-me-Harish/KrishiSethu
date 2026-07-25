"""Health and metadata endpoints for the ML inference service.

Endpoints:
- GET /health       — Liveness probe (always 200 if process running)
- GET /ready        — Readiness probe (checks model is loaded)
- GET /models       — List loaded models with versions
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from krishisetu_ml.core.config import settings

router = APIRouter(prefix="/health", tags=["health"])


class LivenessResponse(BaseModel):
    status: str
    version: str
    env: str


class ReadinessResponse(BaseModel):
    status: str
    version: str
    env: str
    models: dict[str, dict[str, str]]


@router.get("", response_model=LivenessResponse)
@router.get("/", response_model=LivenessResponse, include_in_schema=False)
async def liveness() -> LivenessResponse:
    """Liveness probe — process is running."""
    return LivenessResponse(status="alive", version="0.1.0", env=settings().ENV)


@router.get("/ready", response_model=ReadinessResponse)
async def readiness() -> ReadinessResponse:
    """Readiness probe — model is loaded and ready for inference."""
    from krishisetu_ml.core.onnx_runtime import get_model_loader

    loader = get_model_loader()
    models_status: dict[str, dict[str, str]] = {}

    # Check if disease_classifier is loaded
    if "disease_classifier" in loader._sessions:
        models_status["disease_classifier"] = {
            "version": settings().DISEASE_CLASSIFIER_MODEL_VERSION,
            "status": "loaded",
            "labels_count": str(len(settings().DISEASE_CLASSIFIER_LABELS)),
        }
    else:
        models_status["disease_classifier"] = {
            "status": "not_loaded",
            "version": settings().DISEASE_CLASSIFIER_MODEL_VERSION,
        }

    all_loaded = all(m.get("status") == "loaded" for m in models_status.values())

    return ReadinessResponse(
        status="ready" if all_loaded else "not_ready",
        version="0.1.0",
        env=settings().ENV,
        models=models_status,
    )
