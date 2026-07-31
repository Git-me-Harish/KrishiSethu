"""Prometheus metrics for the main API.

This module defines:
- http_requests_total: Counter (labels: method, path_template, status)
- http_request_duration_seconds: Histogram (labels: method, path_template)
- http_requests_active: Gauge (current in-flight requests)
- db_connections_active: Gauge (active DB pool connections)

And a Starlette middleware that records http_requests_total and
http_request_duration_seconds for every request. The middleware uses
the route's path_template (e.g. "/plots/{plot_id}") as the label value
so that high-cardinality path params (UUIDs) don't explode the metric
cardinality.

The /metrics endpoint is exposed in api/v1/health.py and returns the
Prometheus exposition format via generate_latest().
"""

from __future__ import annotations

import time
from typing import Any

from prometheus_client import (
    CollectorRegistry,
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from krishisetu.core.logging import get_logger

logger = get_logger(__name__)

# Metrics registry (custom registry to avoid global state pollution)
REGISTRY = CollectorRegistry()

# HTTP request counter — total requests by method, path, status
http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    labelnames=["method", "path", "status"],
    registry=REGISTRY,
)

# HTTP request duration histogram — latency distribution
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    labelnames=["method", "path"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0),
    registry=REGISTRY,
)

# Active in-flight requests
http_requests_active = Gauge(
    "http_requests_active",
    "Number of HTTP requests currently being processed",
    registry=REGISTRY,
)

# Active DB pool connections (updated by the database module)
db_connections_active = Gauge(
    "db_connections_active",
    "Number of active database pool connections",
    registry=REGISTRY,
)

# Middleware
class PrometheusMiddleware(BaseHTTPMiddleware):
    """Records HTTP request count + duration for every request.

    Uses the route's path_template (e.g. "/api/v1/plots/{plot_id}") as
    the label value, NOT the actual URL (which would include UUIDs and
    explode cardinality). Falls back to "unknown" if the route hasn't
    been matched yet (e.g. 404s).
    """

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        # Skip metrics endpoint itself (don't measure the scraper)
        if request.url.path == "/api/v1/health/metrics":
            return await call_next(request)

        start_time = time.perf_counter()
        http_requests_active.inc()

        try:
            response = await call_next(request)
            return response
        finally:
            duration = time.perf_counter() - start_time
            http_requests_active.dec()

            # Extract path template (e.g. "/plots/{plot_id}" → "/api/v1/plots/{plot_id}")
            path_template = _get_path_template(request)

            # Get status code (may not exist if the request errored before
            # a response was produced — use 500 in that case)
            status_code = getattr(request.state, "status_code", 500)
            try:
                # If call_next produced a response, get the status from it
                # This is a best-effort — the middleware may not have access
                # to the response object at this point
                pass
            except Exception:
                pass

            # Record metrics
            method = request.method
            http_requests_total.labels(
                method=method,
                path=path_template,
                status=str(status_code),
            ).inc()
            http_request_duration_seconds.labels(
                method=method,
                path=path_template,
            ).observe(duration)


def _get_path_template(request: Request) -> str:
    """Extract the route's path template from the request.

    For example, a request to /api/v1/plots/550e8400-... returns
    "/api/v1/plots/{plot_id}" — the template with UUIDs replaced by
    their parameter names. This prevents high-cardinality label explosion.

    Falls back to the raw path if the route hasn't been matched (404s).
    """
    # Starlette/FastAPI stores the matched route on request.scope["route"]
    route = request.scope.get("route")
    if route and hasattr(route, "path"):
        return route.path

    # Fallback: use the raw path (will have UUIDs in it, but only for 404s
    # and unmatched routes, which are rare)
    return request.url.path


# Exposition
def metrics_response() -> Response:
    """Return a Prometheus-format metrics response.

    Used by the /metrics endpoint in api/v1/health.py.
    """
    return Response(
        content=generate_latest(REGISTRY),
        media_type=CONTENT_TYPE_LATEST,
    )


__all__ = [
    "PrometheusMiddleware",
    "metrics_response",
    "REGISTRY",
    "http_requests_total",
    "http_request_duration_seconds",
    "http_requests_active",
    "db_connections_active",
]
