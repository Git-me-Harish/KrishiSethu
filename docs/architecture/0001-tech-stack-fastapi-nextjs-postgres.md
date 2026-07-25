# ADR-0001: Use FastAPI + Next.js + PostgreSQL as the core tech stack

## Status
Accepted

## Context
KrishiSetu is a government-grade, millions-of-users platform serving Indian
agriculture. The technology stack must be:

- **Python-first** for backend (per project spec — Python ecosystem for ML)
- **Reliable server-side rendering** for low-bandwidth rural users
- **PostgreSQL** for the database (per project spec)
- **Component-based** UI with no emojis (per reference UI)
- **Highly scalable** for millions of users
- **Secure** (RBAC, encryption, audit log)

Options considered:
- **Django + DRF** — batteries-included, but sync-first, less ML-friendly
- **Flask + extensions** — too minimal for this scope
- **FastAPI + Next.js + PostgreSQL** — async-first, type-safe, ML-native

## Decision
Use **FastAPI** for the backend, **Next.js 14 (App Router)** for the frontend,
and **PostgreSQL 16 + PostGIS** for the database.

Supporting technologies:
- **SQLAlchemy 2.0 (async)** as ORM
- **Alembic** for migrations
- **Redis 7** for cache and Celery broker
- **Celery 5** for background tasks
- **Tailwind CSS + shadcn/ui** for the design system
- **TypeScript** end-to-end (auto-generated from OpenAPI)

## Consequences

**Positive:**
- Async-first enables high concurrency on I/O-bound workloads
- Pydantic-native validation = type safety end-to-end
- Auto-generated OpenAPI spec → typed frontend API client
- Best-in-class ML ecosystem compatibility
- Strong government-grade security primitives in FastAPI dependency system

**Negative:**
- Two deployment artifacts (Python API + Node.js frontend) vs. one (Django)
- More operational complexity than a monolith
- FastAPI lacks built-in admin (must build custom)

**Mitigations:**
- Docker Compose + GitHub Actions make multi-artifact deployment manageable
- Custom admin console built on the same Next.js + FastAPI stack
