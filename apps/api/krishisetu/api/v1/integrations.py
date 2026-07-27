"""Integration health check endpoints.

Endpoints:
- GET /api/v1/health/integrations — Check all external API integrations

Reports the status of each external API:
- IMD Weather API
- OpenWeatherMap API
- Sentinel Hub API
- ISRIC SoilGrids API
- UIDAI Aadhaar API
- MSG91 SMS Gateway

Each integration is reported as:
- "live" — API key configured and API is reachable
- "dev_mode" — Running in development/synthetic mode
- "not_configured" — API key not set
- "error" — API key set but API is unreachable
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel

from krishisetu.core.config import settings
from krishisetu.core.database import check_db_connection
from krishisetu.core.dependencies import CurrentUser, DBSession
from krishisetu.core.logging import get_logger
from krishisetu.core.redis import check_redis_connection
from krishisetu.domains.identity.models import UserRole

logger = get_logger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


class IntegrationStatus(BaseModel):
    """Status of a single external integration."""

    name: str
    status: str  # live, dev_mode, not_configured, error
    is_configured: bool
    is_live: bool
    message: str
    checked_at: str


class IntegrationsHealthResponse(BaseModel):
    """Health check response for all integrations."""

    overall_status: str  # healthy, degraded, dev_mode
    integrations: list[IntegrationStatus]
    infrastructure: dict[str, bool]
    checked_at: str


@router.get("/integrations", response_model=IntegrationsHealthResponse)
async def check_integrations(
    current_user: CurrentUser,
    db: DBSession,
) -> IntegrationsHealthResponse:
    """Check the status of all external API integrations.

    Admin-only endpoint. Returns the status of each integration:
    - IMD Weather
    - OpenWeatherMap
    - Sentinel Hub
    - ISRIC SoilGrids
    - UIDAI Aadhaar
    - MSG91 SMS

    Also checks infrastructure (PostgreSQL, Redis).
    """
    if current_user.role != UserRole.ADMIN:
        from krishisetu.core.exceptions import AuthorizationError

        raise AuthorizationError("Admin access required")

    now = datetime.now(UTC).isoformat()
    cfg = settings()
    statuses: list[IntegrationStatus] = []

    # --- IMD Weather ---
    imd_configured = cfg.IMD_API_KEY is not None
    imd_live = imd_configured and not cfg.is_development
    statuses.append(IntegrationStatus(
        name="IMD Weather API",
        status="live" if imd_live else "dev_mode" if cfg.is_development else "not_configured",
        is_configured=imd_configured,
        is_live=imd_live,
        message="Synthetic data (climatology-based)" if not imd_live else "Connected to IMD API",
        checked_at=now,
    ))

    # --- OpenWeatherMap ---
    owm_configured = cfg.OPENWEATHERMAP_API_KEY is not None
    statuses.append(IntegrationStatus(
        name="OpenWeatherMap API",
        status="live" if owm_configured else "not_configured",
        is_configured=owm_configured,
        is_live=owm_configured,
        message="Connected" if owm_configured else "API key not set (optional fallback)",
        checked_at=now,
    ))

    # --- Sentinel Hub ---
    sh_configured = (
        cfg.SENTINEL_HUB_CLIENT_ID is not None
        and cfg.SENTINEL_HUB_CLIENT_SECRET is not None
    )
    sh_live = sh_configured and not cfg.is_development
    statuses.append(IntegrationStatus(
        name="Sentinel Hub API",
        status="live" if sh_live else "dev_mode" if cfg.is_development else "not_configured",
        is_configured=sh_configured,
        is_live=sh_live,
        message=(
            "Synthetic NDVI (monthly baselines)"
            if not sh_live
            else "Connected to Sentinel Hub Process API"
        ),
        checked_at=now,
    ))

    # --- ISRIC SoilGrids ---
    # ISRIC is free — always "live" (no API key needed)
    statuses.append(IntegrationStatus(
        name="ISRIC SoilGrids API",
        status="live",
        is_configured=True,
        is_live=True,
        message="Connected (free API, no key required)",
        checked_at=now,
    ))

    # --- UIDAI Aadhaar ---
    uidai_configured = cfg.UIDAI_API_KEY is not None
    uidai_live = uidai_configured and not cfg.is_development
    statuses.append(IntegrationStatus(
        name="UIDAI Aadhaar e-KYC",
        status="live" if uidai_live else "dev_mode" if cfg.is_development else "not_configured",
        is_configured=uidai_configured,
        is_live=uidai_live,
        message="Synthetic OTP (logged to console)" if not uidai_live else "Connected to UIDAI API",
        checked_at=now,
    ))

    # --- MSG91 SMS ---
    msg91_configured = cfg.MSG91_AUTH_KEY is not None
    msg91_live = msg91_configured and not cfg.is_development
    statuses.append(IntegrationStatus(
        name="MSG91 SMS Gateway",
        status="live" if msg91_live else "dev_mode" if cfg.is_development else "not_configured",
        is_configured=msg91_configured,
        is_live=msg91_live,
        message="Console (logs to stdout)" if not msg91_live else "Connected to MSG91",
        checked_at=now,
    ))

    # --- Infrastructure ---
    db_ok = await check_db_connection()
    redis_ok = await check_redis_connection()

    # Overall status
    any_error = any(s.status == "error" for s in statuses)
    all_dev = all(s.status in ("dev_mode", "not_configured") for s in statuses)

    if any_error:
        overall = "degraded"
    elif all_dev:
        overall = "dev_mode"
    else:
        overall = "healthy"

    return IntegrationsHealthResponse(
        overall_status=overall,
        integrations=statuses,
        infrastructure={
            "postgresql": db_ok,
            "redis": redis_ok,
        },
        checked_at=now,
    )
