# Alembic migrations directory.

Migrations are version-controlled database schema changes. Each file defines
an `upgrade()` and `downgrade()` function.

## Commands

```bash
# Apply all pending migrations
alembic upgrade head

# Roll back one migration
alembic downgrade -1

# Generate a new migration from model changes
alembic revision --autogenerate -m "description of change"

# Show current revision
alembic current

# Show migration history
alembic history --verbose
```

## Conventions

- Forward-only in production. Rollbacks are achieved by writing a new forward
  migration that reverses the change.
- File names follow `YYYY_MM_DD_HHMM_<revision>_<slug>.py`.
- Each migration is reviewed in PR before merge.
- Long-running migrations are broken into multiple steps:
  1. Add nullable column
  2. Backfill in batches
  3. Set default and NOT NULL
