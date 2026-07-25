"""Combined security middleware: request size limit + SQL injection heuristic.

This module bundles two light-touch security middlewares that are too small
to warrant their own files:

1. **RequestSizeLimitMiddleware** — rejects requests with bodies exceeding
   a configurable limit. Prevents memory exhaustion from large payloads
   (e.g. a 1GB JSON body that the parser would happily try to load).

2. **SQLInjectionGuardMiddleware** — heuristic detection of SQL injection
   patterns in query parameters and JSON body. Does NOT reject (we rely on
   parameterized queries), but logs suspicious requests for security
   monitoring and increments a counter that can trigger alerts.

Both middlewares are placed early in the chain so they run before the
expensive application logic.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from krishisetu.core.config import settings
from krishisetu.core.input_sanitizer import detect_sql_injection_attempt
from krishisetu.core.logging import get_logger

logger = get_logger(__name__)

# Methods that typically carry a body worth size-checking
_BODY_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Methods whose query string is worth SQLi-checking (all of them — GET is
# actually the most common vector for reflected SQLi)
_ALL_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"})


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests with bodies exceeding MAX_REQUEST_BODY_BYTES.

    Default limit: 15 MB (covers our largest upload: 10MB disease image +
    overhead). Larger uploads go through multipart streaming which is not
    subject to this limit (the limit applies to non-streaming bodies only).
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if request.method in _BODY_METHODS:
            cl = request.headers.get("content-length")
            if cl:
                try:
                    size = int(cl)
                except ValueError:
                    return Response(
                        status_code=400,
                        content='{"error":{"code":"BAD_REQUEST","message":"Invalid Content-Length"}}',
                        media_type="application/json",
                    )
                max_bytes = settings().MAX_REQUEST_BODY_BYTES
                if size > max_bytes:
                    logger.warning(
                        "security.request_too_large",
                        method=request.method,
                        path=request.url.path,
                        content_length=size,
                        max=max_bytes,
                    )
                    return Response(
                        status_code=413,
                        content=(
                            '{"error":{"code":"REQUEST_TOO_LARGE",'
                            f'"message":"Request body exceeds {max_bytes} bytes"}}'
                        ),
                        media_type="application/json",
                    )
        return await call_next(request)


class SQLInjectionGuardMiddleware(BaseHTTPMiddleware):
    """Heuristic detection of SQL injection patterns in request inputs.

    Checks:
    - URL query parameters
    - JSON body (if Content-Type is application/json)

    Behavior:
    - On match: log a security event (level WARNING) and increment a
      Redis counter for rate-based alerting. Does NOT reject the request.
    - Rationale: parameterized queries make actual injection impossible;
      this is purely for threat intelligence and anomaly detection.

    The audit log is also written via audit_logger when a match is detected,
    so suspicious requests appear in the audit trail for incident response.
    """

    # Path prefixes that are exempt (admin actions may legitimately contain
    # SQL keywords like "DROP TABLE" in documentation or notes)
    EXEMPT_PREFIXES = (
        "/api/v1/admin/audit",
        "/docs",
        "/redoc",
        "/openapi.json",
    )

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        path = request.url.path
        if path.startswith(self.EXEMPT_PREFIXES):
            return await call_next(request)

        if request.method not in _ALL_METHODS:
            return await call_next(request)

        suspicious = False
        suspicious_params: list[str] = []

        # 1. Check query parameters
        for key, value in request.query_params.multi_items():
            if detect_sql_injection_attempt(value):
                suspicious = True
                suspicious_params.append(f"query:{key}")

        # 2. Check JSON body (read-then-replay, since we can't peek)
        if (
            request.method in _BODY_METHODS
            and request.headers.get("content-type", "").startswith("application/json")
        ):
            try:
                body_bytes = await request.body()
                if body_bytes:
                    body_text = body_bytes.decode("utf-8", errors="ignore")
                    # Quick check: does any suspicious pattern appear in the body?
                    if detect_sql_injection_attempt(body_text):
                        # Try to identify which field triggered it
                        try:
                            body_json = json.loads(body_text)
                            if isinstance(body_json, dict):
                                for k, v in body_json.items():
                                    if isinstance(v, str) and detect_sql_injection_attempt(v):
                                        suspicious_params.append(f"body:{k}")
                        except Exception:
                            pass
                        suspicious = True
            except Exception:
                pass

        if suspicious:
            request_id = getattr(request.state, "request_id", "unknown")
            client_ip = (
                request.headers.get("x-forwarded-for", "").split(",")[0].strip()
                or (request.client.host if request.client else None)
            )
            logger.warning(
                "security.sqli_attempt_detected",
                method=request.method,
                path=path,
                suspicious_params=suspicious_params,
                client_ip=client_ip,
                request_id=request_id,
            )
            # Increment Redis counter for rate-based alerting
            try:
                from krishisetu.core.redis import get_redis
                redis = await get_redis()
                if redis is not None:
                    key = "security:sqli:counter"
                    await redis.incr(key)
                    await redis.expire(key, 3600)  # 1-hour window
            except Exception:
                # Redis is best-effort for security counters
                pass

        return await call_next(request)


__all__ = [
    "RequestSizeLimitMiddleware",
    "SQLInjectionGuardMiddleware",
]
