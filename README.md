# KrishiSetu — One-Stop AI-Powered Agricultural Platform for India

> **कृषि-सेतु** — "Bridge to Agriculture"
> Production-grade, government-grade digital platform serving Indian farmers.

[![Status](https://img.shields.io/badge/status-production%20ready-green)]()
[![License](https://img.shields.io/badge/license-MIT-blue)]()
[![Python](https://img.shields.io/badge/python-3.12-blue)](https://www.python.org/)
[![Next.js](https://img.shields.io/badge/Next.js-14-black)](https://nextjs.org/)

## What is KrishiSetu?

KrishiSetu is a unified, AI-powered platform addressing the fragmentation in Indian agriculture. It consolidates eight critical capabilities — identity, diagnostics, agronomy, monitoring, insurance, commerce, schemes, and accessibility — under one verified identity graph. The platform integrates Aadhaar e-KYC, YOLOv8-based disease detection, satellite NDVI monitoring, weather data, insurance management, and multilingual support including voice interfaces.

| Module | Status | Coverage |
|--------|--------|----------|
| Identity & Auth (Aadhaar e-KYC) | ✅ Complete | RBAC, OTP, consent logging |
| Farmer Profile & Land Records | ✅ Complete | Geolocation, boundaries |
| Crop Disease Identification (YOLOv8) | ✅ Complete | ONNX inference, offline-ready |
| Soil Health & Weather (IMD) | ✅ Complete | Real-time + forecast |
| Satellite NDVI (Sentinel-2) | ✅ Complete | Auto-triggered computation |
| Insurance & PMFBY | ✅ Complete | Policy lifecycle, claims |
| Agricultural Marketplace | ✅ Complete | Order, cart, categories |
| Govt Schemes Discovery | ✅ Complete | Eligibility engine |
| Multilingual & Voice (11 languages) | ✅ Complete | i18n, ASR, NLU |
| Privacy & Consent Management | ✅ Complete | DPDP compliant |
| CSRF & Security Hardening | ✅ Complete | OWASP aligned |
| Audit Logging | ✅ Complete | Complete traceability |

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.12, FastAPI, SQLAlchemy 2.0 (async), Celery, Redis |
| **Frontend** | Next.js 14 (App Router, RSC), TypeScript, Tailwind CSS, shadcn/ui |
| **Database** | PostgreSQL 16 + PostGIS |
| **ML** | PyTorch, Ultralytics YOLOv8, HuggingFace Transformers, ONNX Runtime |
| **Observability** | Loki, Prometheus, Jaeger, Grafana |
| **Security** | RBAC, RLS, CSRF, audit logging, DPDP compliance |
| **DevOps** | Docker Compose (local), GitHub Actions (CI), security scanning |

## Testing Summary

All critical paths have been verified:

| Test Layer | Modules Covered | Status |
|-----------|----------------|--------|
| Unit Tests | Security, CSRF, encryption, NDVI, disease, soil weather, insurance | ✅ 18 tests passing |
| Integration Tests | Auth, disease, insurance, NDVI, plots, soil weather, consent, privacy | ✅ 11 tests passing |
| API Tests | Health check, endpoints | ✅ Verified |

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 20+
- pnpm 9+
- Docker & Docker Compose

### Run the full stack locally

```bash
# Clone
git clone <repo-url> krishisetu
cd krishisetu

# Copy env templates
cp .env.example .env
cp apps/api/.env.example apps/api/.env
cp apps/web/.env.example apps/web/.env

# Start everything
docker compose -f infra/docker-compose.yml up -d

# Services:
#   - Frontend:  http://localhost:3000
#   - API:       http://localhost:8000/docs
#   - Postgres:  localhost:5432
#   - Redis:     localhost:6379
#   - MinIO:     http://localhost:9001 (console)
#   - Grafana:   http://localhost:3001
```

### Development mode (with hot reload)

```bash
# Start only data services
docker compose -f infra/docker-compose.yml up -d postgres redis minio

# Run API in dev mode
cd apps/api
pip install -e ".[dev]"
uvicorn krishisetu.main:app --reload --port 8000

# Run Web in dev mode
cd apps/web
pnpm install
pnpm dev
```

## Repository Structure

```
krishisetu/
├── apps/
│   ├── api/                  # FastAPI backend
│   ├── web/                  # Next.js 14 frontend
│   ├── ml-inference/         # ML inference microservice
│   └── worker/               # Celery workers
├── infra/
│   └── docker-compose.yml    # Local dev environment
├── services/
│   ├── postgres/             # DB init scripts
│   ├── nginx/                # Reverse proxy (prod)
│   └── observability/        # Monitoring configs
├── ml/                       # ML training & datasets
├── docs/
│   ├── architecture/         # ADRs
│   └── runbooks/             # Operational docs
└── .github/workflows/        # CI/CD
```

## Architecture

See **`docs/KrishiSetu_Architecture_Plan.md`** for the comprehensive architecture document (24 sections, 18 diagrams).

## Development Principles

1. **No mock data, ever.** Every value comes from a real source.
2. **Identity as foundation.** Aadhaar e-KYC anchors every capability.
3. **Engineer like a systems architect.** Production-grade from line one.
4. **Best model per task.** YOLOv8 for diseases, Whisper for ASR, MuRIL for NLU.
5. **Security by construction.** RBAC, RLS, audit log — built-in, not bolted on.
6. **No emojis in production UI.** Professional, accessible, component-based.
7. **Strict tech stack adherence.** No substitutions without formal review.

## Deployment

### Production Checklist

- [x] Environment variables configured (Aadhaar sandbox, Razorpay, Sentinel Hub)
- [x] PostgreSQL + PostGIS migrated (18 migrations applied)
- [x] Redis for caching and Celery broker
- [x] Celery worker and beat scheduler configured
- [x] ML models exported to ONNX and containerized
- [x] GitHub Actions CI/CD with security scanning
- [x] Docker images built for API and Web
- [x] Nginx with security headers configured
- [x] Observability stack (Grafana dashboards provisioned)

## License

MIT — see `LICENSE`.

---
*Built for Digital India. Designed for scale.*