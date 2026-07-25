# KrishiSetu API

FastAPI backend for the KrishiSetu agricultural platform.

## Local Development

### With Docker Compose (recommended)

From the repository root:

```bash
docker compose -f infra/docker-compose.yml up -d api
```

The API will be available at http://localhost:8000.

### Without Docker

```bash
# Create virtual env
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e ".[dev]"

# Copy env
cp .env.example .env
# Edit .env to point DATABASE_URL and REDIS_URL to your local services

# Run migrations
alembic upgrade head

# Start dev server
uvicorn krishisetu.main:app --reload --port 8000
```

## Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Root info |
| `/docs` | GET | Swagger UI (dev only) |
| `/redoc` | GET | ReDoc (dev only) |
| `/openapi.json` | GET | OpenAPI spec (dev only) |
| `/api/v1/health` | GET | Liveness probe |
| `/api/v1/health/ready` | GET | Readiness probe (checks DB + Redis) |

## Code Quality

```bash
# Lint
ruff check .
ruff format .

# Type check
mypy krishisetu/

# Tests
pytest
```
