"""Custom FastAPI middleware.

Middleware order (outermost first):
1. RequestIDMiddleware — generate/propagate request ID
2. ExceptionHandlerMiddleware — convert unhandled exceptions to 500s
3. LoggingMiddleware — log every request with duration
4. CORSMiddleware — added in main.py
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from krishisetu.core.logging import get_logger

logger = get_logger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Inject a unique request ID into every request.

    - Reads X-Request-ID header if present (from upstream gateway)
    - Otherwise generates a UUID v4
    - Stores in request.state.request_id
    - Adds to response headers as X-Request-ID
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        # Bind to structlog context for the duration of this request
        import structlog

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class LoggingMiddleware(BaseHTTPMiddleware):
    """Log every request with method, path, status, duration."""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        start_time = time.perf_counter()
        request_id = getattr(request.state, "request_id", "unknown")

        # Skip health checks to avoid log noise
        path = request.url.path
        if path in ("/health", "/ready", "/metrics"):
            return await call_next(request)

        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start_time) * 1000

            logger.info(
                "request.completed",
                method=request.method,
                path=path,
                status_code=response.status_code,
                duration_ms=round(duration_ms, 2),
                request_id=request_id,
                client_ip=request.client.host if request.client else None,
            )
            return response

        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                "request.failed",
                method=request.method,
                path=path,
                error=str(exc),
                error_type=type(exc).__name__,
                duration_ms=round(duration_ms, 2),
                request_id=request_id,
            )
            raise


class ExceptionHandlerMiddleware(BaseHTTPMiddleware):
    """Catch unhandled exceptions and return a clean 500 response.

    Prevents stack traces from leaking to the client in production.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        try:
            return await call_next(request)
        except Exception as exc:
            request_id = getattr(request.state, "request_id", "unknown")
            logger.exception(
                "unhandled.exception",
                error=str(exc),
                error_type=type(exc).__name__,
                path=request.url.path,
                request_id=request_id,
            )
            return JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": "An internal server error occurred",
                        "request_id": request_id,
                    }
                },
                headers={"X-Request-ID": request_id},
            )
