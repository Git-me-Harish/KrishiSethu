"""Create insurance schema: products, policies, claims, claim_evidence

Creates 4 tables in the `insurance` schema:
- insurance.insurance_products  (PMFBY and state scheme catalog)
- insurance.insurance_policies  (farmer's purchased policies)
- insurance.insurance_claims    (filed claims with status workflow)
- insurance.claim_evidence      (auto-attached + manual evidence)

Revision ID: 0009
Revises: 0008
Create Date: 2026-07-19

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS insurance;")

    # --- insurance_products ---
    op.create_table(
        "insurance_products",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True, nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("product_type", sa.String(30), nullable=False),
        sa.Column("insurer_name", sa.String(255), nullable=False),
        sa.Column("crop_slug", sa.String(50), nullable=False),
        sa.Column("crop_name", sa.String(100), nullable=False),
        sa.Column("season", sa.String(20), nullable=False),
        sa.Column("season_year", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(100), nullable=False),
        sa.Column("district", sa.String(100), nullable=True),
        sa.Column("sum_insured_per_ha", sa.Numeric(12, 2), nullable=False),
        sa.Column("farmer_premium_rate", sa.Numeric(5, 4), nullable=False),
        sa.Column("farmer_premium_min", sa.Numeric(12, 2), nullable=True),
        sa.Column("farmer_premium_max", sa.Numeric(12, 2), nullable=True),
        sa.Column("coverage_start_date", sa.Date(), nullable=False),
        sa.Column("coverage_end_date", sa.Date(), nullable=False),
        sa.Column("claim_cutoff_yield", sa.Numeric(8, 2), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.CheckConstraint(
            "product_type IN ('pmfby', 'rwbcis', 'state_scheme', 'commercial')",
            name="insurance_products_type_check",
        ),
        sa.CheckConstraint(
            "season IN ('kharif', 'rabi', 'zaid')",
            name="insurance_products_season_check",
        ),
        sa.CheckConstraint("sum_insured_per_ha > 0", name="insurance_products_sum_insured_positive"),
        sa.CheckConstraint("farmer_premium_rate >= 0 AND farmer_premium_rate <= 1", name="insurance_products_premium_rate_range"),
        sa.CheckConstraint("coverage_end_date > coverage_start_date", name="insurance_products_coverage_dates"),
        sa.UniqueConstraint("slug", "season", "season_year", "state", name="insurance_products_unique"),
        schema="insurance",
    )
    op.create_index("idx_ins_products_slug", "insurance_products", ["slug"], schema="insurance")
    op.create_index("idx_ins_products_type", "insurance_products", ["product_type"], schema="insurance")
    op.create_index("idx_ins_products_crop", "insurance_products", ["crop_slug"], schema="insurance")
    op.create_index("idx_ins_products_state", "insurance_products", ["state", "season", "season_year"], schema="insurance")
    op.create_index("idx_ins_products_active", "insurance_products", ["state", "season", "season_year"], postgresql_where=sa.text("is_active = true"), schema="insurance")

    op.execute("""
        CREATE TRIGGER insurance_products_set_updated_at
            BEFORE UPDATE ON insurance.insurance_products
            FOR EACH ROW
            EXECUTE FUNCTION identity.set_updated_at();
    """)

    # --- insurance_policies ---
    op.create_table(
        "insurance_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True, nullable=False),
        sa.Column("policy_number", sa.String(50), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("farmer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("crop_cycle_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("sum_insured", sa.Numeric(12, 2), nullable=False),
        sa.Column("area_insured_ha", sa.Numeric(10, 4), nullable=False),
        sa.Column("premium_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("premium_rate", sa.Numeric(5, 4), nullable=False),
        sa.Column("premium_paid", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("premium_paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payment_reference", sa.String(100), nullable=True),
        sa.Column("coverage_start_date", sa.Date(), nullable=False),
        sa.Column("coverage_end_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("bank_account_number", sa.String(30), nullable=True),
        sa.Column("bank_ifsc", sa.String(15), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'active', 'expired', 'cancelled')",
            name="insurance_policies_status_check",
        ),
        sa.CheckConstraint("sum_insured > 0", name="insurance_policies_sum_insured_positive"),
        sa.CheckConstraint("area_insured_ha > 0", name="insurance_policies_area_positive"),
        sa.CheckConstraint("premium_amount >= 0", name="insurance_policies_premium_non_negative"),
        sa.CheckConstraint("coverage_end_date > coverage_start_date", name="insurance_policies_coverage_dates"),
        sa.ForeignKeyConstraint(["product_id"], ["insurance.insurance_products.id"], ondelete="RESTRICT", name="insurance_policies_product_fk"),
        sa.ForeignKeyConstraint(["farmer_id"], ["identity.users.id"], ondelete="CASCADE", name="insurance_policies_farmer_fk"),
        sa.ForeignKeyConstraint(["plot_id"], ["farmer.plots.id"], ondelete="CASCADE", name="insurance_policies_plot_fk"),
        sa.ForeignKeyConstraint(["crop_cycle_id"], ["farmer.crop_cycles.id"], ondelete="SET NULL", name="insurance_policies_crop_cycle_fk"),
        sa.UniqueConstraint("policy_number", name="insurance_policies_policy_number_unique"),
        schema="insurance",
    )
    op.create_index("idx_ins_policies_number", "insurance_policies", ["policy_number"], schema="insurance")
    op.create_index("idx_ins_policies_product", "insurance_policies", ["product_id"], schema="insurance")
    op.create_index("idx_ins_policies_farmer", "insurance_policies", ["farmer_id"], schema="insurance")
    op.create_index("idx_ins_policies_plot", "insurance_policies", ["plot_id"], schema="insurance")
    op.create_index("idx_ins_policies_status", "insurance_policies", ["status"], schema="insurance")
    op.create_index("idx_ins_policies_farmer_status", "insurance_policies", ["farmer_id", "status"], schema="insurance")

    op.execute("""
        CREATE TRIGGER insurance_policies_set_updated_at
            BEFORE UPDATE ON insurance.insurance_policies
            FOR EACH ROW
            EXECUTE FUNCTION identity.set_updated_at();
    """)

    # --- insurance_claims ---
    op.create_table(
        "insurance_claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True, nullable=False),
        sa.Column("claim_number", sa.String(50), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("farmer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(30), server_default=sa.text("'draft'"), nullable=False),
        sa.Column("loss_date", sa.Date(), nullable=False),
        sa.Column("loss_description", sa.Text(), nullable=False),
        sa.Column("estimated_loss_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("claimed_amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("approved_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("payout_transaction_id", sa.String(100), nullable=True),
        sa.Column("payout_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("auto_evidence_summary", postgresql.JSONB, nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.CheckConstraint(
            "claim_type IN ('localized_risk', 'widespread_risk', 'preventive_sowing', 'post_harvest', 'mid_season_adversity')",
            name="insurance_claims_type_check",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'submitted', 'under_review', 'evidence_requested', 'approved', 'rejected', 'payout_disbursed', 'withdrawn')",
            name="insurance_claims_status_check",
        ),
        sa.CheckConstraint("estimated_loss_pct >= 0 AND estimated_loss_pct <= 100", name="insurance_claims_loss_pct_range"),
        sa.CheckConstraint("claimed_amount > 0", name="insurance_claims_claimed_positive"),
        sa.ForeignKeyConstraint(["policy_id"], ["insurance.insurance_policies.id"], ondelete="CASCADE", name="insurance_claims_policy_fk"),
        sa.ForeignKeyConstraint(["farmer_id"], ["identity.users.id"], ondelete="CASCADE", name="insurance_claims_farmer_fk"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["identity.users.id"], ondelete="SET NULL", name="insurance_claims_reviewed_by_fk"),
        sa.UniqueConstraint("claim_number", name="insurance_claims_claim_number_unique"),
        schema="insurance",
    )
    op.create_index("idx_ins_claims_number", "insurance_claims", ["claim_number"], schema="insurance")
    op.create_index("idx_ins_claims_policy", "insurance_claims", ["policy_id"], schema="insurance")
    op.create_index("idx_ins_claims_farmer", "insurance_claims", ["farmer_id"], schema="insurance")
    op.create_index("idx_ins_claims_status", "insurance_claims", ["status"], schema="insurance")
    op.create_index("idx_ins_claims_type", "insurance_claims", ["claim_type"], schema="insurance")
    op.create_index("idx_ins_claims_farmer_status", "insurance_claims", ["farmer_id", "status"], schema="insurance")

    op.execute("""
        CREATE TRIGGER insurance_claims_set_updated_at
            BEFORE UPDATE ON insurance.insurance_claims
            FOR EACH ROW
            EXECUTE FUNCTION identity.set_updated_at();
    """)

    # --- claim_evidence ---
    op.create_table(
        "claim_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True, nullable=False),
        sa.Column("claim_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_type", sa.String(30), nullable=False),
        sa.Column("source_module", sa.String(30), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("snapshot_data", postgresql.JSONB, nullable=True),
        sa.Column("file_url", sa.String(512), nullable=True),
        sa.Column("is_auto_attached", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.CheckConstraint(
            "evidence_type IN ('ndvi_drop', 'disease_report', 'weather_alert', 'officer_inspection', 'photo_evidence', 'yield_data', 'bank_document')",
            name="claim_evidence_type_check",
        ),
        sa.CheckConstraint(
            "source_module IN ('ndvi', 'disease', 'soil_weather', 'officer', 'farmer')",
            name="claim_evidence_source_module_check",
        ),
        sa.ForeignKeyConstraint(["claim_id"], ["insurance.insurance_claims.id"], ondelete="CASCADE", name="claim_evidence_claim_fk"),
        schema="insurance",
    )
    op.create_index("idx_claim_evidence_claim", "claim_evidence", ["claim_id"], schema="insurance")
    op.create_index("idx_claim_evidence_type", "claim_evidence", ["evidence_type"], schema="insurance")
    op.create_index("idx_claim_evidence_auto", "claim_evidence", ["claim_id"], postgresql_where=sa.text("is_auto_attached = true"), schema="insurance")


def downgrade() -> None:
    op.drop_index("idx_claim_evidence_auto", schema="insurance")
    op.drop_index("idx_claim_evidence_type", schema="insurance")
    op.drop_index("idx_claim_evidence_claim", schema="insurance")
    op.drop_table("claim_evidence", schema="insurance")

    op.execute("DROP TRIGGER IF EXISTS insurance_claims_set_updated_at ON insurance.insurance_claims;")
    op.drop_index("idx_ins_claims_farmer_status", schema="insurance")
    op.drop_index("idx_ins_claims_type", schema="insurance")
    op.drop_index("idx_ins_claims_status", schema="insurance")
    op.drop_index("idx_ins_claims_farmer", schema="insurance")
    op.drop_index("idx_ins_claims_policy", schema="insurance")
    op.drop_index("idx_ins_claims_number", schema="insurance")
    op.drop_table("insurance_claims", schema="insurance")

    op.execute("DROP TRIGGER IF EXISTS insurance_policies_set_updated_at ON insurance.insurance_policies;")
    op.drop_index("idx_ins_policies_farmer_status", schema="insurance")
    op.drop_index("idx_ins_policies_status", schema="insurance")
    op.drop_index("idx_ins_policies_plot", schema="insurance")
    op.drop_index("idx_ins_policies_farmer", schema="insurance")
    op.drop_index("idx_ins_policies_product", schema="insurance")
    op.drop_index("idx_ins_policies_number", schema="insurance")
    op.drop_table("insurance_policies", schema="insurance")

    op.execute("DROP TRIGGER IF EXISTS insurance_products_set_updated_at ON insurance.insurance_products;")
    op.drop_index("idx_ins_products_active", schema="insurance")
    op.drop_index("idx_ins_products_state", schema="insurance")
    op.drop_index("idx_ins_products_crop", schema="insurance")
    op.drop_index("idx_ins_products_type", schema="insurance")
    op.drop_index("idx_ins_products_slug", schema="insurance")
    op.drop_table("insurance_products", schema="insurance")

    op.execute("DROP SCHEMA IF EXISTS insurance CASCADE;")
