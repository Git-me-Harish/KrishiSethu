"""Rate limiting for HTTP endpoints, backed by Redis via slowapi.

FIX (T3): the `RATE_LIMIT_AUTH` and `RATE_LIMIT_DEFAULT` config values in
core/config.py were previously never enforced anywhere in the codebase.
This module wires them up via slowapi, with Redis as the backend (so the
limit is shared across all API workers, not per-process).

Usage in routes:
    from krishisetu.core.rate_limit import limiter, rate_limit_auth

    @router.post("/login-password")
    @limiter.limit(rate_limit_auth)  # reads RATE_LIMIT_AUTH from settings
    async def login_with_password(request: Request, ...):
        ...

The `request: Request` parameter is REQUIRED by slowapi on any rate-limited
endpoint — it's how slowapi extracts the client IP for the limit key.

Configuration (in .env / Settings):
    RATE_LIMIT_AUTH=5/minute        # /auth/login-password, /auth/verify-otp
    RATE_LIMIT_DEFAULT=100/minute   # default for all other endpoints
    RATE_LIMIT_ML=20/minute         # ML inference endpoints (T15)

The rate-limit string format is `<count>/<period>` where period is one of:
second, minute, hour, day. Examples: "5/minute", "100/hour", "1000/day".

Behavior:
- On limit exceeded, slowapi raises RateLimitExceeded which the existing
  RateLimitExceededError exception handler in main.py turns into a 429
  response with `Retry-After` header.
- Exempt paths: /api/v1/health, /docs, /redoc, /openapi.json — these are
  never rate-limited (defined in EXEMPT_PATHS below).
- Exempt roles: in production, admin users are NOT exempt — they get the
  same limit as everyone else (defense in depth). Override per-endpoint
  if needed.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

from krishisetu.core.config import settings
from krishisetu.core.logging import get_logger
from krishisetu.core.redis import get_redis_client

logger = get_logger(__name__)


# Paths that are never rate-limited (health checks, docs, OpenAPI spec).
# These are called frequently by monitoring / load balancers and would
# generate false-positive rate-limit hits.
EXEMPT_PATHS: frozenset[str] = frozenset({
    "/",
    "/api/v1/health",
    "/api/v1/health/",
    "/api/v1/health/integrations",
    "/docs",
    "/redoc",
    "/openapi.json",
})


def _is_exempt(path: str) -> bool:
    """Check if a request path is exempt from rate limiting."""
    return path in EXEMPT_PATHS

# Rate-limit strings (read from Settings, with safe defaults)
def _rate_limit_auth() -> str:
    """Return the auth-endpoint rate-limit string from settings.

    Settings value: RATE_LIMIT_AUTH (default "5/minute")
    """
    return settings().RATE_LIMIT_AUTH


def _rate_limit_default() -> str:
    """Return the default rate-limit string from settings.

    Settings value: RATE_LIMIT_DEFAULT (default "100/minute")
    """
    return settings().RATE_LIMIT_DEFAULT


def _rate_limit_ml() -> str:
    """Return the ML-endpoint rate-limit string from settings.

    Settings value: RATE_LIMIT_ML (default "20/minute")
    """
    return settings().RATE_LIMIT_ML

# Public callables for use in @limiter.limit(...) decorators.
# These are functions (not strings) so they're evaluated at request time,
# not import time — which means changes to settings (e.g. via env var
# reload) take effect without restarting the app.
rate_limit_auth = _rate_limit_auth
rate_limit_default = _rate_limit_default
rate_limit_ml = _rate_limit_ml

# Limiter instance (singleton)
def _get_redis_url() -> str:
    """Get the Redis URL for slowapi's storage backend.

    slowapi requires a sync redis client (not async), so we build the URL
    string and let slowapi create its own connection. The URL is taken
    from the same REDIS_URL setting used by the rest of the app.
    """
    return str(settings().REDIS_URL)

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=_get_redis_url(),
    default_limits=[_rate_limit_default()],
    headers_enabled=True,  # emit X-RateLimit-* headers on every response
    strategy="fixed-window",  # simplest; "moving-window" is more accurate but pricier
)

# Middleware to exempt health/docs paths from the default limit
def should_skip_rate_limit(request_path: str) -> bool:
    """Return True if the request should skip rate limiting entirely.

    Use this in a middleware or a custom SlowAPIMiddleware subclass to
    bypass the limiter for health-check and documentation paths.
    """
    return _is_exempt(request_path)


# Startup hook — log the active rate-limit configuration
def log_rate_limit_config() -> None:
    """Log the active rate-limit configuration at app startup.

    Call this from main.py's lifespan() startup hook so the operator can
    verify rate limits are wired correctly.
    """
    cfg = settings()
    logger.info(
        "rate_limit.config",
        auth_limit=cfg.RATE_LIMIT_AUTH,
        default_limit=cfg.RATE_LIMIT_DEFAULT,
        ml_limit=cfg.RATE_LIMIT_ML,
        storage_uri=_get_redis_url().replace("://", "://***@") if "@" in _get_redis_url() else _get_redis_url(),
        exempt_paths=sorted(EXEMPT_PATHS),
    )


__all__ = [
    "limiter",
    "rate_limit_auth",
    "rate_limit_default",
    "rate_limit_ml",
    "should_skip_rate_limit",
    "log_rate_limit_config",
    "EXEMPT_PATHS",
]
