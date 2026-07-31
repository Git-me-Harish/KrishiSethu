"""
Revision ID: 0018
Revises: 0017
Create Date: 2026-07-31
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create system schema + outbox_events table."""
    # Create the system schema (if it doesn't exist)
    op.execute("CREATE SCHEMA IF NOT EXISTS system")

    op.create_table(
        "outbox_events",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                   server_default=sa.text("gen_random_uuid()"),
                   primary_key=True, nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False, index=True),
        sa.Column("payload", sa.dialects.postgresql.JSONB, nullable=False),
        sa.Column("status", sa.String(20), nullable=False,
                   server_default="pending", index=True),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer, nullable=False, server_default="3"),
        sa.Column("last_error", sa.String(2000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                   server_default=sa.text("NOW()"), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        schema="system",
    )

    # Index for the relay query: SELECT ... WHERE status='pending' AND attempts < max_attempts
    op.create_index(
        "ix_outbox_events_pending",
        "outbox_events",
        ["status", "attempts"],
        schema="system",
        postgresql_where=sa.text("status = 'pending'"),
    )

    # Index for cleanup of old dispatched events
    op.create_index(
        "ix_outbox_events_dispatched_at",
        "outbox_events",
        ["dispatched_at"],
        schema="system",
    )


def downgrade() -> None:
    """Drop the outbox_events table."""
    op.drop_index("ix_outbox_events_dispatched_at", schema="system")
    op.drop_index("ix_outbox_events_pending", schema="system")
    op.drop_table("outbox_events", schema="system")