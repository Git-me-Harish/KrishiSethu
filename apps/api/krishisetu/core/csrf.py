"""CSRF protection via double-submit cookie pattern.

Why double-submit (not synchronizer token):
- KrishiSetu uses JWT Bearer tokens (not cookies) for API auth, which makes
  the API surface immune to classical CSRF.
- However, the refresh-token cookie (set by /auth/refresh) IS a cookie, and
  any cookie-based auth needs CSRF protection.
- Double-submit is simpler than synchronizer tokens for stateless APIs: the
  client sends the same random value in both a cookie and a header; the
  server checks they match.

Flow:
1. Client requests a CSRF token: GET /api/v1/auth/csrf-token
2. Server sets two cookies:
   - __Host-csrf: random token (32 bytes, base64url)
   - __Host-csrf_sign: HMAC-SHA256(csrf, server_secret) — prevents an
     attacker from forging just the csrf cookie
3. Client reads the csrf cookie (JavaScript) and sends it back as
   X-CSRF-Token header on every state-changing request.
4. Server middleware:
   - For safe methods (GET/HEAD/OPTIONS), skip.
   - For unsafe methods (POST/PUT/PATCH/DELETE):
     a. Read csrf cookie + X-CSRF-Token header.
     b. Verify both are present and equal.
     c. Verify csrf_sign cookie matches HMAC(csrf, secret).
     d. Reject with 403 if any check fails.

Cookie attributes:
- __Host- prefix: ensures cookie is only set over HTTPS, only from the
  apex domain (no subdomains), and requires Secure + Path=/. This is the
  strictest cookie prefix.
- SameSite=Strict: prevents the cookie from being sent on cross-site
  requests (defense in depth).
- Secure: only sent over HTTPS (in production).

Exemptions:
- Bearer-token-only requests are exempted (no cookie = no CSRF risk).
- Webhook endpoints (Razorpay) use HMAC signature verification instead.
"""

from __future__ import annotations

import hmac
import secrets
from collections.abc import Awaitable, Callable
from typing import ClassVar

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from krishisetu.core.config import settings
from krishisetu.core.exceptions import KrishiSetuError
from krishisetu.core.logging import get_logger

logger = get_logger(__name__)

# Cookie names — __Host- prefix requires Secure + Path=/ + no Domain attribute
CSRF_COOKIE = "__Host-csrf"
CSRF_SIGN_COOKIE = "__Host-csrf_sign"
CSRF_HEADER = "X-CSRF-Token"

# Methods that do not require CSRF protection (RFC 7231 "safe methods")
SAFE_METHODS: frozenset[str] = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

# Paths exempted from CSRF (use their own signature verification)
EXEMPT_PATHS: frozenset[str] = frozenset({
    "/api/v1/payments/webhook",  # Razorpay — HMAC signed
    "/api/v1/security/csp-report",  # browser CSP reports — no auth
    "/api/v1/health",  # public health check
})


class CSRFError(KrishiSetuError):
    """Raised when CSRF validation fails."""

    def __init__(self, message: str = "CSRF validation failed") -> None:
        super().__init__(
            code="CSRF_INVALID",
            message=message,
            status_code=403,
            details={"reason": message},
        )


def generate_csrf_token() -> tuple[str, str]:
    """Generate a new CSRF token and its HMAC signature.

    Returns (token, signed_token) where:
    - token is 32 bytes base64url-encoded (~43 chars)
    - signed_token is HMAC-SHA256(token, secret) hex-encoded
    """
    s = settings()
    if not s.CSRF_SECRET:
        raise RuntimeError("CSRF_SECRET not configured")
    secret = s.CSRF_SECRET.get_secret_value().encode("utf-8")

    token = secrets.token_urlsafe(32)
    signature = hmac.new(secret, token.encode("ascii"), "sha256").hexdigest()
    return token, signature


def verify_csrf_token(token: str, signature: str) -> bool:
    """Verify that a CSRF token matches its HMAC signature.

    Uses hmac.compare_digest for constant-time comparison (prevents timing
    attacks on the signature check).
    """
    s = settings()
    if not s.CSRF_SECRET:
        return False
    secret = s.CSRF_SECRET.get_secret_value().encode("utf-8")

    expected = hmac.new(secret, token.encode("ascii"), "sha256").hexdigest()
    return hmac.compare_digest(expected, signature)


def set_csrf_cookies(response: Response, token: str, signature: str) -> None:
    """Set the CSRF cookies on a response.

    Uses __Host- prefix which requires:
    - Secure=True (HTTPS only) — set based on environment
    - Path=/
    - No Domain attribute
    """
    s = settings()
    secure = s.is_production or s.CSRF_COOKIE_SECURE

    response.set_cookie(
        key=CSRF_COOKIE,
        value=token,
        secure=secure,
        httponly=False,  # MUST be readable by JS
        samesite="strict",
        path="/",
        max_age=60 * 60 * 24,  # 24 hours
    )
    response.set_cookie(
        key=CSRF_SIGN_COOKIE,
        value=signature,
        secure=secure,
        httponly=True,  # NOT readable by JS (server-only)
        samesite="strict",
        path="/",
        max_age=60 * 60 * 24,
    )


class CSRFMiddleware(BaseHTTPMiddleware):
    """Enforce CSRF protection on state-changing requests.

    Only enforces when:
    - The request uses an unsafe method (POST/PUT/PATCH/DELETE)
    - The path is not in EXEMPT_PATHS
    - The request has any cookie set (cookie-less requests with only
      Authorization: Bearer header are immune to CSRF)

    When enforcing: requires the X-CSRF-Token header to match the __Host-csrf
    cookie, and the __Host-csrf_sign cookie to be a valid HMAC signature.
    """

    # Exempt paths are matched by prefix
    EXEMPT_PREFIXES: ClassVar[tuple[str, ...]] = (
        "/api/v1/payments/webhook",
        "/api/v1/security/csp-report",
        "/api/v1/health",
        "/docs",
        "/redoc",
        "/openapi.json",
    )

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        method = request.method.upper()

        # Skip safe methods
        if method in SAFE_METHODS:
            return await call_next(request)

        path = request.url.path

        # Skip exempt paths
        if path in EXEMPT_PATHS or path.startswith(self.EXEMPT_PREFIXES):
            return await call_next(request)

        # Skip if no cookies present (Bearer-only auth — not vulnerable to CSRF)
        cookie_header = request.headers.get("cookie", "")
        if not cookie_header:
            return await call_next(request)

        # Enforce CSRF
        token = request.headers.get(CSRF_HEADER)
        cookie_token = request.cookies.get(CSRF_COOKIE)
        cookie_sign = request.cookies.get(CSRF_SIGN_COOKIE)

        if not token or not cookie_token or not cookie_sign:
            logger.warning(
                "csrf.missing_tokens",
                method=method,
                path=path,
                has_header=token is not None,
                has_cookie=cookie_token is not None,
                has_sign=cookie_sign is not None,
            )
            return Response(
                status_code=403,
                content='{"error":{"code":"CSRF_INVALID","message":"CSRF token missing"}}',
                media_type="application/json",
            )

        if not hmac.compare_digest(token, cookie_token):
            logger.warning("csrf.token_mismatch", method=method, path=path)
            return Response(
                status_code=403,
                content='{"error":{"code":"CSRF_INVALID","message":"CSRF token mismatch"}}',
                media_type="application/json",
            )

        if not verify_csrf_token(cookie_token, cookie_sign):
            logger.warning("csrf.signature_invalid", method=method, path=path)
            return Response(
                status_code=403,
                content='{"error":{"code":"CSRF_INVALID","message":"CSRF signature invalid"}}',
                media_type="application/json",
            )

        return await call_next(request)


__all__ = [
    "CSRF_COOKIE",
    "CSRF_HEADER",
    "CSRF_SIGN_COOKIE",
    "EXEMPT_PATHS",
    "SAFE_METHODS",
    "CSRFError",
    "CSRFMiddleware",
    "generate_csrf_token",
    "set_csrf_cookies",
    "verify_csrf_token",
]
