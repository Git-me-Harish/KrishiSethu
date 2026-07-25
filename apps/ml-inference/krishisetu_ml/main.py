"""KrishiSetu ML Inference Service — FastAPI application.

Loads ML models on startup (with warmup) and serves inference requests.
Separate from the main API for independent scaling (GPU vs CPU pools).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from krishisetu_ml.api import disease, health, voice
from krishisetu_ml.core.config import settings
from krishisetu_ml.core.logging import configure_logging, get_logger
from krishisetu_ml.core.middleware import (
    ExceptionHandlerMiddleware,
    LoggingMiddleware,
    RequestIDMiddleware,
)

configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
    logger.info("ml_service.starting", env=settings().ENV, version="0.1.0")

    # --- Startup: warm up the disease classifier ---
    if settings().MODEL_WARMUP_ON_START:
        try:
            from krishisetu_ml.core.onnx_runtime import get_model_loader

            loader = get_model_loader()
            loader.warmup("disease_classifier")
            logger.info("ml_service.model_warmed_up", model="disease_classifier")
        except Exception as e:
            logger.warning(
                "ml_service.warmup_failed",
                model="disease_classifier",
                error=str(e),
                note="Service will start; first inference will be slower",
            )

    logger.info("ml_service.started")
    yield
    logger.info("ml_service.stopped")


def create_app() -> FastAPI:
    """Create and configure the ML inference FastAPI application."""
    cfg = settings()

    app = FastAPI(
        title="KrishiSetu ML Inference Service",
        description=(
            "ML inference microservice for crop disease classification, "
            "vernacular ASR/TTS, and natural language understanding."
        ),
        version="0.1.0",
        docs_url="/docs" if not cfg.is_production else None,
        redoc_url="/redoc" if not cfg.is_production else None,
        lifespan=lifespan,
    )

    # --- Middleware ---
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(ExceptionHandlerMiddleware)
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    # --- Routers ---
    app.include_router(health.router, prefix="/health")
    app.include_router(disease.router, prefix="/predict")
    app.include_router(voice.router, prefix="/voice")

    # --- Root endpoint ---
    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {
            "name": "KrishiSetu ML Inference Service",
            "version": "0.1.0",
            "docs": "/docs" if not cfg.is_production else "disabled",
            "health": "/health",
        }

    return app


app = create_app()
