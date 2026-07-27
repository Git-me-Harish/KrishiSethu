"""Add refresh_tokens table for JWT rotation and revocation

Creates the `identity.refresh_tokens` table that stores hashed refresh tokens
with their jti (JWT ID) for rotation and revocation tracking. Also adds the
foreign key constraint from refresh_tokens.user_id to identity.users.id
(which was intentionally omitted in migration 0001 to keep that migration
focused on the users table).

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-19

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("jti", sa.String(length=64), nullable=False),
        sa.Column("device_info", sa.String(length=512), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_reason", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.CheckConstraint(
            "revoked_reason IS NULL OR revoked_reason IN ('logout', 'rotation', 'session_invalidation', 'suspected_theft', 'logout_all')",
            name="refresh_tokens_revoked_reason_check",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["identity.users.id"], ondelete="CASCADE", name="refresh_tokens_user_fk"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="refresh_tokens_token_hash_unique"),
        sa.UniqueConstraint("jti", name="refresh_tokens_jti_unique"),
        schema="identity",
    )

    # Indexes for common query patterns
    op.create_index(
        "idx_refresh_tokens_user_id",
        "refresh_tokens",
        ["user_id"],
        schema="identity",
    )
    op.create_index(
        "idx_refresh_tokens_jti",
        "refresh_tokens",
        ["jti"],
        schema="identity",
    )
    op.create_index(
        "idx_refresh_tokens_expires_at",
        "refresh_tokens",
        ["expires_at"],
        schema="identity",
    )
    # Partial index for active (non-revoked) tokens — speeds up validation
    op.create_index(
        "idx_refresh_tokens_active",
        "refresh_tokens",
        ["user_id"],
        postgresql_where=sa.text("revoked_at IS NULL"),
        schema="identity",
    )


def downgrade() -> None:
    op.drop_index("idx_refresh_tokens_active", schema="identity")
    op.drop_index("idx_refresh_tokens_expires_at", schema="identity")
    op.drop_index("idx_refresh_tokens_jti", schema="identity")
    op.drop_index("idx_refresh_tokens_user_id", schema="identity")
    op.drop_table("refresh_tokens", schema="identity")
