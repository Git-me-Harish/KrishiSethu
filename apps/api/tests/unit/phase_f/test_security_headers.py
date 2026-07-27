"""Unit tests for security headers middleware.

Verifies that the middleware attaches all expected security headers to
responses, and that CSP report-only mode works.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from krishisetu.core.security_headers import SecurityHeadersMiddleware


def _build_test_app() -> FastAPI:
    """Build a minimal FastAPI app with just the SecurityHeadersMiddleware."""
    app = FastAPI()

    @app.get("/")
    async def root() -> dict:
        return {"ok": True}

    @app.get("/error")
    async def error() -> dict:
        raise RuntimeError("test error")

    app.add_middleware(SecurityHeadersMiddleware)
    # Add exception handler so /error returns a clean 500 instead of crashing
    from fastapi.responses import JSONResponse

    @app.exception_handler(Exception)
    async def handler(request, exc):
        return JSONResponse(status_code=500, content={"error": "test"})

    return app


class TestSecurityHeaders:
    @pytest.fixture
    def app(self) -> FastAPI:
        return _build_test_app()

    async def test_csp_header_present(self, app: FastAPI) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/")
            assert "content-security-policy" in {k.lower() for k in r.headers.keys()}

    async def test_x_content_type_options(self, app: FastAPI) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/")
            assert r.headers.get("x-content-type-options") == "nosniff"

    async def test_x_frame_options(self, app: FastAPI) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/")
            assert r.headers.get("x-frame-options") == "DENY"

    async def test_referrer_policy(self, app: FastAPI) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/")
            assert r.headers.get("referrer-policy") == "strict-origin-when-cross-origin"

    async def test_permissions_policy(self, app: FastAPI) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/")
            pp = r.headers.get("permissions-policy", "")
            assert "camera=()" in pp
            assert "microphone=()" in pp
            assert "geolocation=()" in pp

    async def test_cross_origin_isolation(self, app: FastAPI) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/")
            assert r.headers.get("cross-origin-opener-policy") == "same-origin"
            assert r.headers.get("cross-origin-resource-policy") == "same-origin"

    async def test_dns_prefetch_control(self, app: FastAPI) -> None:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/")
            assert r.headers.get("x-dns-prefetch-control") == "off"

    async def test_hsts_only_over_https(self, app: FastAPI) -> None:
        """HSTS should NOT be set for HTTP requests (would lock out dev)."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/")
            assert r.headers.get("strict-transport-security") is None

    async def test_hsts_set_when_https(self, app: FastAPI) -> None:
        """HSTS should be set when the request comes over HTTPS."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
            r = await client.get("/")
            hsts = r.headers.get("strict-transport-security", "")
            assert "max-age=63072000" in hsts
            assert "includeSubDomains" in hsts

    async def test_hsts_set_via_forwarded_proto(self, app: FastAPI) -> None:
        """HSTS should be set when X-Forwarded-Proto: https (TLS-terminating proxy)."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/", headers={"x-forwarded-proto": "https"})
            hsts = r.headers.get("strict-transport-security", "")
            assert "max-age=63072000" in hsts

    async def test_headers_applied_to_error_responses(self, app: FastAPI) -> None:
        """Security headers should be applied even to error responses."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/error")
            assert r.status_code == 500
            assert r.headers.get("x-content-type-options") == "nosniff"
            assert r.headers.get("x-frame-options") == "DENY"

    async def test_cache_control_not_set_for_generic_path(self, app: FastAPI) -> None:
        """Generic paths should not get no-store (only sensitive paths do)."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/")
            assert r.headers.get("cache-control") is None


class TestCspReportOnlyMode:
    """When CSP_REPORT_ONLY=true, emit Content-Security-Policy-Report-Only
    instead of Content-Security-Policy. This allows staged rollout."""

    async def test_report_only_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from krishisetu.core import security_headers as mod
        from krishisetu.core.config import Settings

        # Build a settings instance with report-only enabled
        class TestSettings(Settings):
            CSP_REPORT_ONLY: bool = True
            CSP_DIRECTIVES: str | None = None

        # Monkeypatch the cached settings()
        monkeypatch.setattr(mod, "settings", lambda: TestSettings(
            JWT_SECRET="x" * 32,
            DATABASE_URL="postgresql+asyncpg://u:p@h/db",
            REDIS_URL="redis://localhost",
            S3_ENDPOINT="http://localhost",
            S3_ACCESS_KEY="x",
            S3_SECRET_KEY="x",
            ENCRYPTION_KEY="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
            CSRF_SECRET="x" * 32,
        ))

        app = _build_test_app()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.get("/")
            # Report-Only header present
            assert "content-security-policy-report-only" in {k.lower() for k in r.headers.keys()}
            # Regular CSP not set
            assert "content-security-policy" not in {k.lower() for k in r.headers.keys()}
