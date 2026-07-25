"""HTTP security headers middleware.

Implements defense-in-depth browser-side protections aligned with OWASP
Secure Headers Project and the Mozilla Observatory grading criteria.

Headers applied (with rationale):
- Content-Security-Policy: mitigates XSS, data injection, clickjacking
- Strict-Transport-Security: forces HTTPS for 2 years incl. subdomains
- X-Content-Type-Options: nosniff — prevents MIME-type confusion
- X-Frame-Options: DENY — legacy clickjacking defense (CSP frame-ancestors
  is the modern equivalent, but we keep both for older browsers)
- Referrer-Policy: strict-origin-when-cross-origin — limits referrer leakage
- Permissions-Policy: disables camera, microphone, geolocation, USB by default
  (the platform only requests these on specific pages, e.g. voice assistant
  requests microphone; CSP and JS APIs are still available where explicitly
  enabled on the client)
- Cross-Origin-Opener-Policy: same-origin — isolates browsing context
- Cross-Origin-Resource-Policy: same-origin — restricts who can embed resources
- X-DNS-Prefetch-Control: off — disables prefetch to prevent DNS rebinding
- Cache-Control (for API responses): no-store — prevents caching of PII in
  shared browser caches and proxies

Design choices:
- CSP is configurable via env (CSP_DIRECTIVES) so production can be locked
  down without redeploying code.
- Report-only mode is supported via CSP_REPORT_ONLY env flag for staged rollout.
- The API serves JSON, so CSP is intentionally strict (default-src 'none').
- The web frontend serves its own CSP via Next.js middleware (see
  apps/web/middleware.ts); this header set is for the API surface.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from krishisetu.core.config import settings
from krishisetu.core.logging import get_logger

logger = get_logger(__name__)


# Default CSP for API responses (JSON-only surface, very strict).
# 'none' for everything except connect-src (which must allow the web origin
# for fetch) and report-uri (for CSP violation reporting endpoint).
DEFAULT_API_CSP = (
    "default-src 'none'; "
    "frame-ancestors 'none'; "
    "base-uri 'none'; "
    "form-action 'none'; "
    "connect-src 'self'; "
    "report-uri /api/v1/security/csp-report"
)

# Paths that should never be cached (anything that may carry user data or
# session-identifying tokens).
_NO_CACHE_PATHS = (
    "/api/v1/auth",
    "/api/v1/me",
    "/api/v1/plots",
    "/api/v1/disease-reports",
    "/api/v1/insurance",
    "/api/v1/orders",
    "/api/v1/payments",
    "/api/v1/consent",
    "/api/v1/privacy",
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach strict security headers to every response.

    Order in the middleware chain: this is added as the OUTER middleware
    (after RequestIDMiddleware, before LoggingMiddleware) so headers are
    applied to error responses too.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)

        s = settings()

        # --- Content-Security-Policy ---
        csp = s.CSP_DIRECTIVES or DEFAULT_API_CSP
        if s.CSP_REPORT_ONLY:
            response.headers["Content-Security-Policy-Report-Only"] = csp
        else:
            response.headers["Content-Security-Policy"] = csp

        # --- Strict-Transport-Security ---
        # Only emit when serving over HTTPS (or behind a TLS-terminating proxy
        # that forwards X-Forwarded-Proto). The 2-year duration matches
        # recommendations from hstspreload.org. includeSubDomains is intentional
        # because the entire krishisetu.in domain is HTTPS-only.
        if (
            request.url.scheme == "https"
            or request.headers.get("x-forwarded-proto") == "https"
        ):
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains; preload"
            )

        # --- X-Content-Type-Options ---
        response.headers["X-Content-Type-Options"] = "nosniff"

        # --- X-Frame-Options (legacy clickjacking defense) ---
        response.headers["X-Frame-Options"] = "DENY"

        # --- Referrer-Policy ---
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # --- Permissions-Policy ---
        # Disable all sensitive client APIs by default; the web client
        # explicitly requests microphone on the voice assistant page only.
        response.headers["Permissions-Policy"] = (
            "camera=(), "
            "microphone=(), "
            "geolocation=(), "
            "usb=(), "
            "magnetometer=(), "
            "gyroscope=(), "
            "accelerometer=(), "
            "payment=()"
        )

        # --- Cross-Origin isolation ---
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"

        # --- DNS prefetch ---
        response.headers["X-DNS-Prefetch-Control"] = "off"

        # --- Cache-Control for sensitive paths ---
        path = request.url.path
        if path.startswith(_NO_CACHE_PATHS):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"

        # --- Server header scrubbing ---
        # Never reveal the underlying server tech stack to make fingerprinting
        # harder. The default uvicorn Server header is replaced with a
        # meaningless value.
        if "server" in {k.lower() for k in response.headers.keys()}:
            response.headers["server"] = "krishisetu"

        return response


async def csp_report_handler(request: Request) -> Response:
    """Endpoint to receive Content-Security-Policy violation reports.

    Browsers POST JSON to this endpoint when a CSP violation occurs (if
    report-uri / report-to is configured). We log the report for inspection
    and return 204 No Content.

    Registered at: POST /api/v1/security/csp-report
    """
    try:
        body: Any = await request.json()
    except Exception:
        body = None

    logger.warning(
        "csp.violation_reported",
        report=body,
        client_ip=request.client.host if request.client else None,
        request_id=getattr(request.state, "request_id", None),
    )
    return Response(status_code=204)
