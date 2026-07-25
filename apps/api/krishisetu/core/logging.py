"""Structured logging configuration using structlog.

All logs are emitted as structured JSON with:
- timestamp (ISO 8601 UTC)
- level
- request_id (propagated from middleware)
- user_id (when available)
- service name
- message
- extra fields

Logs are shipped to Loki via Promtail in production.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from krishisetu.core.config import settings


def configure_logging() -> None:
    """Configure structlog and stdlib logging for the application."""
    log_level = getattr(logging, settings().LOG_LEVEL.upper(), logging.INFO)

    # Configure stdlib logging (used by libraries like SQLAlchemy, uvicorn)
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )

    # Tame noisy libraries
    for noisy_logger in (
        "uvicorn.access",
        "uvicorn.error",
        "sqlalchemy.engine",
        "asyncpg",
        "httpx",
        "botocore",
    ):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)

    # Configure structlog
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings().is_development:
        # Pretty console output for dev
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    else:
        # JSON output for production (parsed by Loki/Promtail)
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a structlog logger instance."""
    return structlog.get_logger(name).bind(service="krishisetu-api")
