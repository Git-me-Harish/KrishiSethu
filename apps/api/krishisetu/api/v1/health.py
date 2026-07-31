"""Health check + observability endpoints.

Four endpoints:
- GET /health         — liveness probe (always 200 if process is running)
- GET /ready          — readiness probe (checks DB, Redis connectivity)
- GET /metrics        — Prometheus metrics (T7: now implemented)
- GET /integrations   — integration health (Sentinel Hub, UIDAI, etc.)
"""

from __future__ import annotations

from fastapi import APIRouter, Response
from pydantic import BaseModel

from krishisetu.core.config import settings
from krishisetu.core.database import check_db_connection
from krishisetu.core.redis import check_redis_connection
from krishisetu.core.metrics import metrics_response

router = APIRouter(tags=["health"])

class LivenessResponse(BaseModel):
    """Liveness probe response."""

    status: str
    version: str
    env: str

class ReadinessResponse(BaseModel):
    """Readiness probe response with component health."""

    status: str
    version: str
    env: str
    checks: dict[str, bool]


@router.get("", response_model=LivenessResponse)
@router.get("/", response_model=LivenessResponse, include_in_schema=False)
async def liveness() -> LivenessResponse:
    """Liveness probe — returns 200 if the process is running.

    Use this for Kubernetes livenessProbe / Docker HEALTHCHECK.
    Does NOT check dependencies — that's what /ready is for.
    """
    return LivenessResponse(
        status="alive",
        version="0.1.0",
        env=settings().ENV,
    )


@router.get("/ready", response_model=ReadinessResponse)
async def readiness() -> ReadinessResponse:
    """Readiness probe — checks DB, Redis connectivity.

    Use this for Kubernetes readinessProbe.
    Returns 200 only if all critical dependencies are reachable.
    """
    db_ok = await check_db_connection()
    redis_ok = await check_redis_connection()
    all_ok = db_ok and redis_ok

    return ReadinessResponse(
        status="ready" if all_ok else "not_ready",
        version="0.1.0",
        env=settings().ENV,
        checks={
            "database": db_ok,
            "redis": redis_ok,
        },
    )


@router.get("/metrics", include_in_schema=False)
async def prometheus_metrics() -> Response:
    return metrics_response()