# KrishiSetu — One-Stop AI-Powered Agricultural Platform for India

> **कृषि-सेतु** — "Bridge to Agriculture"
> Production-grade, government-grade digital platform serving Indian farmers.

[![Status](https://img.shields.io/badge/status-active%20development-green)]()
[![License](https://img.shields.io/badge/license-MIT-blue)]()

## What is KrishiSetu?

KrishiSetu is a unified, AI-powered platform addressing the fragmentation in Indian agriculture. It consolidates eight critical capabilities — identity, diagnostics, agronomy, monitoring, insurance, commerce, schemes, and accessibility — under one verified identity graph.

| Module | Status |
|--------|--------|
| Identity & Auth (Aadhaar e-KYC) | Phase 1 — In Progress |
| Farmer Profile & Land Records | Phase 1 — Planned |
| Crop Disease Identification (YOLOv8) | Phase 1 — Planned |
| Soil Health & Weather (IMD) | Phase 2 |
| Satellite NDVI (Sentinel-2) | Phase 2 |
| Insurance & PMFBY | Phase 3 |
| Agricultural Marketplace | Phase 3 |
| Govt Schemes Discovery | Phase 4 |
| Multilingual & Voice (10 languages) | Phase 2+ |

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.12, FastAPI, SQLAlchemy 2.0 (async), Celery, Redis |
| **Frontend** | Next.js 14 (App Router, RSC), TypeScript, Tailwind CSS, shadcn/ui |
| **Database** | PostgreSQL 16 + PostGIS |
| **ML** | PyTorch, Ultralytics YOLOv8, HuggingFace Transformers, ONNX Runtime |
| **Observability** | Loki, Prometheus, Jaeger, Grafana |
| **DevOps** | Docker Compose (local), GitHub Actions (CI) |

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
│   ├── ml-inference/         # ML inference microservice (Phase 1+)
│   └── worker/               # Celery workers (Phase 1+)
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

See **`KrishiSetu_Architecture_Plan.md`** in `/home/z/my-project/download/` for the comprehensive architecture document (24 sections, 18 diagrams).

## Development Principles

1. **No mock data, ever.** Every value comes from a real source.
2. **Identity as foundation.** Aadhaar e-KYC anchors every capability.
3. **Engineer like a systems architect.** Production-grade from line one.
4. **Best model per task.** YOLOv8 for diseases, Whisper for ASR, MuRIL for NLU.
5. **Security by construction.** RBAC, RLS, audit log — built-in, not bolted on.
6. **No emojis in production UI.** Professional, accessible, component-based.
7. **Strict tech stack adherence.** No substitutions without formal review.

## License

MIT — see `LICENSE`.
