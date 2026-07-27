"""Service-to-service authentication for the ML inference service.

This service is internal: only the main API (apps/api) is allowed to call it.
Callers must present the shared secret from ``ML_SERVICE_TOKEN`` in the
``X-ML-Service-Token`` header. Health probes are intentionally exempt so the
container healthcheck keeps working.
"""

from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, status

from krishisetu_ml.core.config import settings
from krishisetu_ml.core.logging import get_logger

logger = get_logger(__name__)

SERVICE_TOKEN_HEADER = "X-ML-Service-Token"


async def require_service_token(
    x_ml_service_token: str | None = Header(
        default=None,
        alias=SERVICE_TOKEN_HEADER,
        description="Shared secret issued to the KrishiSetu API service",
    ),
) -> None:
    """Reject any request that does not carry the shared service token.

    Uses a constant-time comparison so the token cannot be recovered by
    timing the response.
    """
    expected = settings().ML_SERVICE_TOKEN.get_secret_value()

    if x_ml_service_token is None or not secrets.compare_digest(
        x_ml_service_token, expected
    ):
        logger.warning(
            "ml_service.auth_failed",
            reason="missing_token" if x_ml_service_token is None else "bad_token",
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing service token",
            headers={"WWW-Authenticate": SERVICE_TOKEN_HEADER},
        )
