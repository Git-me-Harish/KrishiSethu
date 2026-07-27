"""KrishiSetu FastAPI application factory.

The application is constructed via a factory pattern, enabling multiple app
variants (main API, admin API) from the same codebase with different middleware
and router configurations.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from krishisetu.api.v1.router import api_router
from krishisetu.core.config import settings
from krishisetu.core.exceptions import KrishiSetuError, RateLimitExceededError
from krishisetu.core.logging import configure_logging, get_logger
from krishisetu.core.middleware import (
    ExceptionHandlerMiddleware,
    LoggingMiddleware,
    RequestIDMiddleware,
)
from krishisetu.core.csrf import CSRFMiddleware
from krishisetu.core.rate_limiter import AuthRateLimitMiddleware
from krishisetu.core.redis import close_redis
from krishisetu.core.security_headers import SecurityHeadersMiddleware, csp_report_handler
from krishisetu.core.security_middleware import (
    RequestSizeLimitMiddleware,
    SQLInjectionGuardMiddleware,
)

# Configure logging on import
configure_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown hooks."""
    logger.info("application.starting", env=settings().ENV, version="0.1.0")

    # --- Startup ---
    # Verify critical config is present
    if settings().is_production and len(settings().JWT_SECRET.get_secret_value()) < 32:
        raise RuntimeError("JWT_SECRET must be at least 32 characters in production")

    # Phase F: Warn (not fail) if security config is missing in production
    if settings().is_production:
        if not settings().ENCRYPTION_KEY:
            logger.warning("security.encryption_key_missing_in_prod")
        if not settings().CSRF_SECRET:
            logger.warning("security.csrf_secret_missing_in_prod")

    logger.info("application.started")
    yield

    # --- Shutdown ---
    logger.info("application.stopping")
    await close_redis()
    from krishisetu.core.database import engine

    await engine.dispose()
    logger.info("application.stopped")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app_settings = settings()

    app = FastAPI(
        title="KrishiSetu API",
        description=(
            "One-Stop AI-Powered Agricultural Platform for India. "
            "Production-grade, government-grade digital platform serving Indian farmers."
        ),
        version="0.1.0",
        docs_url="/docs" if not app_settings.is_production else None,
        redoc_url="/redoc" if not app_settings.is_production else None,
        openapi_url="/openapi.json" if not app_settings.is_production else None,
        lifespan=lifespan,
    )

    # --- Middleware (order matters: outermost first) ---
    # Outermost (first added = runs last on response, first on request):
    #   RequestIDMiddleware      — generate request_id for tracing
    #   SecurityHeadersMiddleware — add CSP/HSTS/etc to every response
    #   RequestSizeLimitMiddleware — reject oversized bodies early
    #   SQLInjectionGuardMiddleware — log suspicious inputs
    #   ExceptionHandlerMiddleware — convert unhandled exceptions to clean 500s
    #   LoggingMiddleware         — log every request with duration
    #   CSRFMiddleware            — enforce double-submit cookie on writes
    #   AuthRateLimitMiddleware   — per-IP throttle on auth endpoints
    #   CORSMiddleware            — handle CORS preflight
    #
    # AuthRateLimitMiddleware sits inside CORS (so 429s carry CORS headers and
    # are readable by the browser) but outside routing, so throttled requests
    # never reach a DB session or a bcrypt verify.
    #
    # Note: In Starlette, middleware added LAST runs FIRST on the request
    # path. So the order below is REVERSED from the request-flow order above.
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestSizeLimitMiddleware)
    app.add_middleware(SQLInjectionGuardMiddleware)
    app.add_middleware(ExceptionHandlerMiddleware)
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(CSRFMiddleware)
    app.add_middleware(AuthRateLimitMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    # --- Exception handlers ---
    @app.exception_handler(KrishiSetuError)
    async def krishisetu_error_handler(request: Request, exc: KrishiSetuError) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "unknown")
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                    "request_id": request_id,
                }
            },
            headers={"X-Request-ID": request_id},
        )

    @app.exception_handler(RateLimitExceededError)
    async def rate_limit_handler(
        request: Request, exc: RateLimitExceededError
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", "unknown")
        return JSONResponse(
            status_code=429,
            content={
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                    "request_id": request_id,
                }
            },
            headers={
                "X-Request-ID": request_id,
                "Retry-After": str(exc.retry_after_seconds),
            },
        )

    # --- Routers ---
    app.include_router(api_router, prefix="/api/v1")

    # --- CSP violation report endpoint ---
    app.add_api_route(
        "/api/v1/security/csp-report",
        csp_report_handler,
        methods=["POST"],
        include_in_schema=False,
    )

    # --- Root endpoint ---
    @app.get("/", include_in_schema=False)
    async def root() -> dict:
        return {
            "name": "KrishiSetu API",
            "version": "0.1.0",
            "docs": "/docs" if not app_settings.is_production else None,
            "health": "/api/v1/health",
        }

    return app


# Module-level app instance (used by uvicorn: krishisetu.main:app)
app = create_app()
