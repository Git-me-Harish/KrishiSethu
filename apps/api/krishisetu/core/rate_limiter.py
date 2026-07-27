"""Rate limiting — external API quotas, and per-IP throttling of auth routes.

Two independent concerns live here:

1. ExternalAPIRateLimiter — protects *us* from exhausting third-party quotas
   (IMD, OWM, Sentinel Hub, UIDAI, MSG91), with a circuit breaker.
2. AuthRateLimitMiddleware — protects the *auth endpoints* from credential
   stuffing and OTP brute force, keyed on client IP. Registered in main.py.

--- External API rate limiter ---

Each external API has different rate limits. This module provides a
unified rate limiter that:
1. Tracks calls per API per time window (using Redis)
2. Enforces per-API limits
3. Provides circuit breaker pattern (stops calling if API is consistently failing)
4. Logs rate limit warnings before exhaustion

Rate limits (per service):
- IMD: 60 requests/minute
- OWM: 60 requests/minute (free tier)
- Sentinel Hub: 30 requests/minute (free tier)
- ISRIC: 50 requests/minute (free)
- UIDAI: 5 requests/minute (OTP)
- MSG91: 10 requests/second (transactional)

Circuit breaker:
- After 5 consecutive failures, circuit opens (stops calling for 5 minutes)
- After 5 minutes, circuit half-opens (allows 1 test call)
- If test call succeeds, circuit closes (resumes normal operation)
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any, ClassVar

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from krishisetu.core.config import settings
from krishisetu.core.logging import get_logger
from krishisetu.core.redis import get_redis

logger = get_logger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing — stop calling
    HALF_OPEN = "half_open" # Testing if API recovered


@dataclass
class RateLimitConfig:
    """Rate limit configuration for an external API."""

    service: str
    max_requests: int
    window_seconds: int
    circuit_failure_threshold: int = 5
    circuit_recovery_seconds: int = 300  # 5 minutes


# Pre-configured limits per service
RATE_LIMITS: dict[str, RateLimitConfig] = {
    "imd": RateLimitConfig("imd", max_requests=60, window_seconds=60),
    "owm": RateLimitConfig("owm", max_requests=60, window_seconds=60),
    "sentinel_hub": RateLimitConfig("sentinel_hub", max_requests=30, window_seconds=60),
    "isric": RateLimitConfig("isric", max_requests=50, window_seconds=60),
    "uidai": RateLimitConfig("uidai", max_requests=5, window_seconds=60),
    "msg91": RateLimitConfig("msg91", max_requests=600, window_seconds=60),  # 10/sec
}


class ExternalAPIRateLimiter:
    """Rate limiter with circuit breaker for external APIs.

    Usage:
        limiter = get_rate_limiter()
        allowed, reason = await limiter.check("imd")
        if not allowed:
            # Skip API call, use fallback
            return None
        # Make API call
        try:
            result = await api_call()
            await limiter.record_success("imd")
        except Exception:
            await limiter.record_failure("imd")
            raise
    """

    def __init__(self) -> None:
        self._configs = RATE_LIMITS

    async def check(self, service: str) -> tuple[bool, str]:
        """Check if an API call is allowed (rate limit + circuit breaker).

        Returns:
            (allowed, reason) — True if call is permitted, False with reason if not.
        """
        config = self._configs.get(service)
        if not config:
            # No rate limit configured — allow
            return True, "no_config"

        redis = await get_redis()
        now = int(time.time())

        # --- Circuit breaker check ---
        circuit_key = f"ext:circuit:{service}"
        circuit_data = await redis.get(circuit_key)

        if circuit_data == CircuitState.OPEN.value:
            # Check if recovery period has passed
            opened_at_key = f"ext:circuit:{service}:opened_at"
            opened_at = await redis.get(opened_at_key)
            if opened_at:
                elapsed = now - int(opened_at)
                if elapsed >= config.circuit_recovery_seconds:
                    # Half-open: allow one test call
                    await redis.set(circuit_key, CircuitState.HALF_OPEN.value, ex=config.circuit_recovery_seconds)
                    logger.info("ext_api.circuit_half_open", service=service)
                    # Continue to rate limit check
                else:
                    return False, f"circuit_open ({elapsed}s/{config.circuit_recovery_seconds}s)"

        # --- Rate limit check ---
        window_key = f"ext:rl:{service}:{now // config.window_seconds}"

        current = int(await redis.get(window_key) or 0)
        if current >= config.max_requests:
            logger.warning(
                "ext_api.rate_limited",
                service=service,
                current=current,
                max=config.max_requests,
                window=config.window_seconds,
            )
            return False, f"rate_limited ({current}/{config.max_requests} per {config.window_seconds}s)"

        # Increment counter
        pipe = redis.pipeline()
        pipe.incr(window_key)
        pipe.expire(window_key, config.window_seconds)
        await pipe.execute()

        return True, "allowed"

    async def record_success(self, service: str) -> None:
        """Record a successful API call — resets circuit breaker."""
        config = self._configs.get(service)
        if not config:
            return

        redis = await get_redis()
        circuit_key = f"ext:circuit:{service}"
        failure_key = f"ext:failures:{service}"

        # Reset failure count
        await redis.delete(failure_key)

        # Close circuit if it was open/half-open
        current = await redis.get(circuit_key)
        if current in (CircuitState.OPEN.value, CircuitState.HALF_OPEN.value):
            await redis.delete(circuit_key)
            await redis.delete(f"ext:circuit:{service}:opened_at")
            logger.info("ext_api.circuit_closed", service=service)

    async def record_failure(self, service: str) -> None:
        """Record a failed API call — increments failure count, may open circuit."""
        config = self._configs.get(service)
        if not config:
            return

        redis = await get_redis()
        failure_key = f"ext:failures:{service}"
        circuit_key = f"ext:circuit:{service}"

        failure_count = int(await redis.incr(failure_key))
        await redis.expire(failure_key, 300)  # Reset failures after 5 minutes

        if failure_count >= config.circuit_failure_threshold:
            # Open circuit
            now = int(time.time())
            await redis.set(circuit_key, CircuitState.OPEN.value, ex=config.circuit_recovery_seconds)
            await redis.set(f"ext:circuit:{service}:opened_at", str(now), ex=config.circuit_recovery_seconds)
            logger.warning(
                "ext_api.circuit_opened",
                service=service,
                failures=failure_count,
                threshold=config.circuit_failure_threshold,
                recovery_seconds=config.circuit_recovery_seconds,
            )

    async def get_status(self, service: str) -> dict[str, Any]:
        """Get current rate limiter status for a service."""
        config = self._configs.get(service)
        if not config:
            return {"service": service, "configured": False}

        redis = await get_redis()
        now = int(time.time())
        window_key = f"ext:rl:{service}:{now // config.window_seconds}"
        failure_key = f"ext:failures:{service}"
        circuit_key = f"ext:circuit:{service}"

        current_calls = int(await redis.get(window_key) or 0)
        failures = int(await redis.get(failure_key) or 0)
        circuit_state = await redis.get(circuit_key) or CircuitState.CLOSED.value

        return {
            "service": service,
            "configured": True,
            "max_requests": config.max_requests,
            "window_seconds": config.window_seconds,
            "current_calls": current_calls,
            "consecutive_failures": failures,
            "circuit_state": circuit_state,
            "circuit_threshold": config.circuit_failure_threshold,
        }

    async def get_all_status(self) -> dict[str, Any]:
        """Get status for all configured services."""
        statuses = {}
        for service in self._configs:
            statuses[service] = await self.get_status(service)
        return statuses


# Singleton
_rate_limiter: ExternalAPIRateLimiter | None = None


def get_rate_limiter() -> ExternalAPIRateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = ExternalAPIRateLimiter()
    return _rate_limiter


# ---------------------------------------------------------------------------
# Per-IP throttling of authentication endpoints
# ---------------------------------------------------------------------------

_WINDOW_SECONDS: dict[str, int] = {
    "second": 1,
    "minute": 60,
    "hour": 3600,
    "day": 86400,
}


def parse_rate(rate: str) -> tuple[int, int]:
    """Parse a "<count>/<period>" rate string into (max_requests, seconds).

    Accepts the same syntax as the RATE_LIMIT_* settings, e.g. "5/minute".
    """
    count_str, _, period = rate.partition("/")
    period = period.strip().lower().rstrip("s") or "minute"
    window = _WINDOW_SECONDS.get(period)
    if window is None:
        raise ValueError(f"Unsupported rate period: {rate!r}")
    return int(count_str.strip()), window


def client_ip(request: Request) -> str:
    """Best-effort client IP, honouring the first X-Forwarded-For hop."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


async def check_ip_rate_limit(
    bucket: str,
    identifier: str,
    rate: str,
) -> tuple[bool, int]:
    """Fixed-window counter for (bucket, identifier).

    Returns (allowed, retry_after_seconds). Fails OPEN if Redis is down —
    an unreachable cache must not take authentication offline.
    """
    max_requests, window = parse_rate(rate)
    now = int(time.time())
    key = f"authrl:{bucket}:{identifier}:{now // window}"

    try:
        redis = await get_redis()
        pipe = redis.pipeline()
        pipe.incr(key)
        pipe.expire(key, window)
        results = await pipe.execute()
        current = int(results[0])
    except Exception as exc:  # pragma: no cover — Redis outage path
        logger.error("auth_rate_limit.backend_error", bucket=bucket, error=str(exc))
        return True, 0

    if current > max_requests:
        retry_after = window - (now % window)
        return False, max(retry_after, 1)
    return True, 0


class AuthRateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP rate limiting on credential-bearing auth endpoints.

    Without this, /auth/login-password and /auth/verify-otp accept unlimited
    guesses from a single host: the OTP counter is per-phone and the lockout
    counter is per-account, so neither costs an attacker anything when they
    spread guesses across many accounts.

    Limits come from settings (RATE_LIMIT_AUTH, RATE_LIMIT_AUTH_REFRESH) and
    are enforced on the exact paths below — deliberately not a prefix match,
    so adding an auth route does not silently inherit or escape a limit.
    """

    #: request path -> settings attribute holding its rate string
    LIMITED_PATHS: ClassVar[dict[str, str]] = {
        "/api/v1/auth/login-password": "RATE_LIMIT_AUTH",
        "/api/v1/auth/verify-otp": "RATE_LIMIT_AUTH",
        "/api/v1/auth/send-otp": "RATE_LIMIT_AUTH",
        "/api/v1/auth/google/callback": "RATE_LIMIT_AUTH",
        "/api/v1/auth/google/exchange": "RATE_LIMIT_AUTH",
        "/api/v1/auth/refresh": "RATE_LIMIT_AUTH_REFRESH",
    }

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        setting_name = self.LIMITED_PATHS.get(request.url.path.rstrip("/") or "/")
        if setting_name is None:
            return await call_next(request)

        rate = getattr(settings(), setting_name)
        ip = client_ip(request)
        allowed, retry_after = await check_ip_rate_limit(
            bucket=request.url.path, identifier=ip, rate=rate
        )

        if not allowed:
            logger.warning(
                "auth_rate_limit.exceeded",
                path=request.url.path,
                ip=ip,
                rate=rate,
            )
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": "Too many attempts. Please try again later.",
                        "details": {"retry_after_seconds": retry_after},
                    }
                },
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)
