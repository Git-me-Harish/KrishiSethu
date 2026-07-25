"""Create schemes schema: scheme_catalog, scheme_applications

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-19

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS schemes;")

    # --- scheme_catalog ---
    op.create_table(
        "scheme_catalog",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True, nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("name_hi", sa.String(255), nullable=True),
        sa.Column("short_description", sa.String(500), nullable=False),
        sa.Column("full_description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("level", sa.String(20), server_default=sa.text("'central'"), nullable=False),
        sa.Column("ministry", sa.String(255), nullable=True),
        sa.Column("states", postgresql.JSONB, nullable=True),
        sa.Column("benefit_type", sa.String(50), nullable=True),
        sa.Column("benefit_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("benefit_frequency", sa.String(30), nullable=True),
        sa.Column("benefit_description", sa.Text(), nullable=True),
        sa.Column("eligibility_rules", postgresql.JSONB, nullable=False),
        sa.Column("application_mode", sa.String(20), server_default=sa.text("'online'"), nullable=False),
        sa.Column("documents_required", postgresql.JSONB, nullable=True),
        sa.Column("application_url", sa.String(512), nullable=True),
        sa.Column("application_start_date", sa.Date(), nullable=True),
        sa.Column("application_end_date", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("is_featured", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("source_url", sa.String(512), nullable=True),
        sa.Column("helpline_number", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.CheckConstraint(
            "category IN ('income_support', 'crop_insurance', 'credit', 'input_subsidy', 'equipment_subsidy', 'irrigation', 'soil_health', 'market_support', 'pension', 'other')",
            name="scheme_catalog_category_check",
        ),
        sa.CheckConstraint(
            "level IN ('central', 'state', 'central_state')",
            name="scheme_catalog_level_check",
        ),
        sa.CheckConstraint(
            "application_mode IN ('online', 'offline', 'mixed')",
            name="scheme_catalog_mode_check",
        ),
        sa.UniqueConstraint("code", name="scheme_catalog_code_unique"),
        schema="schemes",
    )
    op.create_index("idx_schemes_code", "scheme_catalog", ["code"], schema="schemes")
    op.create_index("idx_schemes_category", "scheme_catalog", ["category"], schema="schemes")
    op.create_index("idx_schemes_active", "scheme_catalog", ["is_active", "is_featured"], schema="schemes")

    op.execute("""
        CREATE TRIGGER scheme_catalog_set_updated_at
            BEFORE UPDATE ON schemes.scheme_catalog
            FOR EACH ROW
            EXECUTE FUNCTION identity.set_updated_at();
    """)

    # --- scheme_applications ---
    op.create_table(
        "scheme_applications",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True, nullable=False),
        sa.Column("application_number", sa.String(50), nullable=False),
        sa.Column("scheme_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("farmer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(30), server_default=sa.text("'draft'"), nullable=False),
        sa.Column("submitted_data", postgresql.JSONB, nullable=False),
        sa.Column("eligibility_result", postgresql.JSONB, nullable=True),
        sa.Column("submitted_documents", postgresql.JSONB, nullable=True),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("benefit_disbursed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("benefit_reference", sa.String(100), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'submitted', 'under_review', 'approved', 'rejected', 'resubmission_requested', 'withdrawn', 'benefit_disbursed')",
            name="scheme_applications_status_check",
        ),
        sa.ForeignKeyConstraint(["scheme_id"], ["schemes.scheme_catalog.id"], ondelete="RESTRICT", name="scheme_applications_scheme_fk"),
        sa.ForeignKeyConstraint(["farmer_id"], ["identity.users.id"], ondelete="CASCADE", name="scheme_applications_farmer_fk"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["identity.users.id"], ondelete="SET NULL", name="scheme_applications_reviewed_by_fk"),
        sa.UniqueConstraint("application_number", name="scheme_applications_number_unique"),
        schema="schemes",
    )
    op.create_index("idx_scheme_apps_number", "scheme_applications", ["application_number"], schema="schemes")
    op.create_index("idx_scheme_apps_scheme", "scheme_applications", ["scheme_id"], schema="schemes")
    op.create_index("idx_scheme_apps_farmer", "scheme_applications", ["farmer_id"], schema="schemes")
    op.create_index("idx_scheme_apps_status", "scheme_applications", ["status"], schema="schemes")
    op.create_index("idx_scheme_apps_farmer_status", "scheme_applications", ["farmer_id", "status"], schema="schemes")

    op.execute("""
        CREATE TRIGGER scheme_applications_set_updated_at
            BEFORE UPDATE ON schemes.scheme_applications
            FOR EACH ROW
            EXECUTE FUNCTION identity.set_updated_at();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS scheme_applications_set_updated_at ON schemes.scheme_applications;")
    op.drop_index("idx_scheme_apps_farmer_status", schema="schemes")
    op.drop_index("idx_scheme_apps_status", schema="schemes")
    op.drop_index("idx_scheme_apps_farmer", schema="schemes")
    op.drop_index("idx_scheme_apps_scheme", schema="schemes")
    op.drop_index("idx_scheme_apps_number", schema="schemes")
    op.drop_table("scheme_applications", schema="schemes")

    op.execute("DROP TRIGGER IF EXISTS scheme_catalog_set_updated_at ON schemes.scheme_catalog;")
    op.drop_index("idx_schemes_active", schema="schemes")
    op.drop_index("idx_schemes_category", schema="schemes")
    op.drop_index("idx_schemes_code", schema="schemes")
    op.drop_table("scheme_catalog", schema="schemes")

    op.execute("DROP SCHEMA IF EXISTS schemes CASCADE;")
