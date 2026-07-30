"""
Revision ID: 0001
Revises:
Create Date: 20260719

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() > None:
    #  Enable required extensions 
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuidossp\";")
    op.execute("CREATE EXTENSION IF NOT EXISTS \"pgcrypto\";")
    op.execute("CREATE EXTENSION IF NOT EXISTS \"postgis\";")

    #  Create schemas 
    op.execute("CREATE SCHEMA IF NOT EXISTS identity;")
    op.execute("CREATE SCHEMA IF NOT EXISTS farmer;")
    op.execute("CREATE SCHEMA IF NOT EXISTS intelligence;")
    op.execute("CREATE SCHEMA IF NOT EXISTS commerce;")
    op.execute("CREATE SCHEMA IF NOT EXISTS insurance;")
    op.execute("CREATE SCHEMA IF NOT EXISTS schemes;")
    op.execute("CREATE SCHEMA IF NOT EXISTS audit;")
    op.execute("CREATE SCHEMA IF NOT EXISTS notifications;")

    #  users table 
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("phone", sa.String(length=15), nullable=False),
        sa.Column("phone_verified", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("email_verified", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("aadhaar_hash", sa.String(length=64), nullable=True),
        sa.Column("aadhaar_verified", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column(
            "role",
            sa.String(length=20),
            server_default=sa.text("'farmer'"),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("failed_login_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("preferred_language", sa.String(length=5), server_default=sa.text("'en'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.CheckConstraint(
            "role IN ('farmer', 'agri_officer', 'supplier', 'insurer', 'admin')",
            name="users_role_check",
        ),
        sa.CheckConstraint(
            "phone ~ '^[69][09]{9}$'",
            name="users_phone_format_check",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("phone", name="users_phone_unique"),
        sa.UniqueConstraint("aadhaar_hash", name="users_aadhaar_hash_unique"),
        schema="identity",
    )

    #  Indexes 
    op.create_index("idx_users_phone", "users", ["phone"], schema="identity")
    op.create_index(
        "idx_users_aadhaar_hash",
        "users",
        ["aadhaar_hash"],
        postgresql_where=sa.text("aadhaar_hash IS NOT NULL"),
        schema="identity",
    )
    op.create_index(
        "idx_users_role_active",
        "users",
        ["role"],
        postgresql_where=sa.text("is_active = true"),
        schema="identity",
    )

    #  updated_at trigger 
    op.execute("""
        CREATE OR REPLACE FUNCTION identity.set_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER users_set_updated_at
            BEFORE UPDATE ON identity.users
            FOR EACH ROW
            EXECUTE FUNCTION identity.set_updated_at();
    """)


def downgrade() > None:
    op.execute("DROP TRIGGER IF EXISTS users_set_updated_at ON identity.users;")
    op.execute("DROP FUNCTION IF EXISTS identity.set_updated_at();")
    op.drop_index("idx_users_role_active", schema="identity")
    op.drop_index("idx_users_aadhaar_hash", schema="identity")
    op.drop_index("idx_users_phone", schema="identity")
    op.drop_table("users", schema="identity")

    # Drop schemas (cascade to remove all objects within)
    # Note: only drop schemas we created in this migration
    for schema in (
        "notifications",
        "audit",
        "schemes",
        "insurance",
        "commerce",
        "intelligence",
        "farmer",
        "identity",
    ):
        op.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE;")
