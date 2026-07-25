# Engineering Onboarding

Welcome to KrishiSetu. This guide gets you from zero to your first PR in
under 30 minutes.

## 1. Prerequisites

Install these on your machine:

- **Git** (latest)
- **Docker Desktop** (or Docker Engine + Docker Compose on Linux)
- **VS Code** (recommended) with extensions:
  - Python (Microsoft)
  - Pylance
  - Ruff
  - ESLint
  - Tailwind CSS IntelliSense
  - PostgreSQL (by Chris Kolkman)
- **Python 3.12** (for running tests without Docker)
- **Node.js 20+ and pnpm 9+** (for running frontend without Docker)

## 2. Clone and Run

```bash
git clone <repo-url> krishisetu
cd krishisetu

# Copy env templates
cp .env.example .env
cp apps/api/.env.example apps/api/.env
cp apps/web/.env.example apps/web/.env

# Start the entire stack
docker compose -f infra/docker-compose.yml up -d

# Check status
docker compose -f infra/docker-compose.yml ps

# View logs
docker compose -f infra/docker-compose.yml logs -f api
docker compose -f infra/docker-compose.yml logs -f web
```

Verify everything is running:
- Frontend: http://localhost:3000 — should show the landing page
- API docs: http://localhost:8000/docs — should show Swagger UI
- Health: http://localhost:8000/api/v1/health — should return `{"status": "alive"}`
- Readiness: http://localhost:8000/api/v1/health/ready — should return DB + Redis as `true`
- MinIO console: http://localhost:9001 — login with `krishisetu` / `krishisetu_dev_password`

## 3. Project Structure

```
krishisetu/
├── apps/
│   ├── api/                  # FastAPI backend
│   │   ├── krishisetu/
│   │   │   ├── core/         # Config, DB, logging, middleware
│   │   │   ├── api/v1/       # API routes
│   │   │   └── domains/      # Domain modules (identity, plots, etc.)
│   │   ├── alembic/          # Database migrations
│   │   ├── tests/
│   │   └── pyproject.toml
│   └── web/                  # Next.js 14 frontend
│       ├── src/
│       │   ├── app/          # App Router pages
│       │   ├── components/   # UI components
│       │   └── lib/          # Utilities
│       └── package.json
├── infra/
│   └── docker-compose.yml    # Local dev environment
├── services/
│   └── postgres/init.sql     # DB init script
└── docs/
    └── architecture/         # ADRs
```

## 4. Your First Change

Let's add a new API endpoint together — `/api/v1/ping` that returns the
current server time.

### Step 1: Create the route

Edit `apps/api/krishisetu/api/v1/router.py`:

```python
from datetime import datetime, timezone
from fastapi import APIRouter

api_router = APIRouter()

@api_router.get("/ping", tags=["misc"])
async def ping():
    """Simple ping endpoint returning server time."""
    return {
        "message": "pong",
        "server_time": datetime.now(timezone.utc).isoformat(),
    }

# ... existing router includes ...
```

### Step 2: Verify it works

The API hot-reloads automatically. Open http://localhost:8000/api/v1/ping —
you should see the JSON response.

### Step 3: Commit and push

```bash
git add .
git commit -m "feat(api): add /ping endpoint"
git push
```

GitHub Actions will run the full CI pipeline on your PR.

## 5. Common Commands

### Backend (run inside the api container)

```bash
# Enter the API container
docker compose -f infra/docker-compose.yml exec api bash

# Run tests
pytest

# Run linting
ruff check .
ruff format .

# Type checking
mypy krishisetu/

# Create a new migration
alembic revision --autogenerate -m "description of change"

# Apply migrations
alembic upgrade head
```

### Frontend (run inside the web container)

```bash
# Enter the web container
docker compose -f infra/docker-compose.yml exec web sh

# Run tests
pnpm test

# Lint
pnpm lint

# Type check
pnpm typecheck
```

### Database

```bash
# Connect to Postgres
docker compose -f infra/docker-compose.yml exec postgres psql -U krishisetu -d krishisetu

# Common psql commands:
# \dt          — list tables
# \d users     — describe users table
# \dn          — list schemas
# \q           — quit
```

## 6. Debugging

### API not starting?

```bash
docker compose -f infra/docker-compose.yml logs api
```

Common issues:
- **Port 8000 in use**: Stop other services using that port
- **Database connection refused**: Wait for Postgres to be healthy
- **Migration failed**: Check `alembic` logs

### Reset everything

```bash
docker compose -f infra/docker-compose.yml down -v
docker compose -f infra/docker-compose.yml up -d
```

The `-v` flag removes volumes, wiping the database. Use with caution.

## 7. Next Steps

After you're comfortable with the basics:

1. Read `KrishiSetu_Architecture_Plan.md` for the full architecture
2. Read ADRs in `docs/architecture/`
3. Pick a Phase 1 task from the roadmap
4. Create a feature branch: `git checkout -b feature/auth-otp`
5. Build, test, PR

Welcome aboard.
