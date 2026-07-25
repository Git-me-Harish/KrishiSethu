"""Create disease schema: diseases, treatments, reports, predictions, feedback

Creates the `intelligence` schema tables (already exists from migration 0001)
and:
- intelligence.diseases             (master data — disease catalog)
- intelligence.disease_treatments   (treatment recommendations)
- intelligence.disease_reports      (farmer-submitted photos)
- intelligence.disease_predictions  (ML model predictions with provenance)
- intelligence.disease_feedback     (farmer feedback for model improvement)

Key design:
- disease_predictions.all_predictions is JSONB (full distribution, not just top-1)
- disease_reports.image_url stores S3 object key (pre-signed URL generated on demand)
- Unique constraint on disease_predictions.report_id (one prediction per report)
- Indexes on disease_slug, model_version, status for common query patterns

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-19

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Schema already created in migration 0001
    op.execute("CREATE SCHEMA IF NOT EXISTS intelligence;")

    # --- diseases (master data) ---
    op.create_table(
        "diseases",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True, nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("name_en", sa.String(200), nullable=False),
        sa.Column("name_hi", sa.String(200), nullable=True),
        sa.Column("scientific_name", sa.String(300), nullable=True),
        sa.Column("disease_type", sa.String(30), nullable=False),
        sa.Column("affected_crops", postgresql.JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("symptoms", sa.Text(), nullable=False),
        sa.Column("cause", sa.Text(), nullable=False),
        sa.Column("spread_mechanism", sa.Text(), nullable=True),
        sa.Column("favorable_conditions", sa.Text(), nullable=True),
        sa.Column("default_severity", sa.String(20), server_default=sa.text("'moderate'"), nullable=False),
        sa.Column("prevention_measures", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.CheckConstraint(
            "disease_type IN ('fungal', 'bacterial', 'viral', 'pest', 'nematode', 'nutrient', 'environmental')",
            name="diseases_type_check",
        ),
        sa.CheckConstraint(
            "default_severity IN ('low', 'moderate', 'high', 'critical')",
            name="diseases_severity_check",
        ),
        sa.UniqueConstraint("slug", name="diseases_slug_unique"),
        schema="intelligence",
    )
    op.create_index("idx_diseases_slug", "diseases", ["slug"], schema="intelligence")
    op.create_index(
        "idx_diseases_active",
        "diseases",
        ["slug"],
        postgresql_where=sa.text("is_active = true"),
        schema="intelligence",
    )

    # Trigger for updated_at (reuse the function from identity schema)
    op.execute("""
        CREATE TRIGGER diseases_set_updated_at
            BEFORE UPDATE ON intelligence.diseases
            FOR EACH ROW
            EXECUTE FUNCTION identity.set_updated_at();
    """)

    # --- disease_treatments ---
    op.create_table(
        "disease_treatments",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True, nullable=False),
        sa.Column("disease_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("treatment_type", sa.String(30), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("dosage", sa.String(255), nullable=True),
        sa.Column("application_method", sa.Text(), nullable=True),
        sa.Column("timing", sa.Text(), nullable=True),
        sa.Column("precautions", sa.Text(), nullable=True),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("priority", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("source", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.CheckConstraint(
            "treatment_type IN ('organic', 'chemical', 'biological', 'cultural', 'preventive')",
            name="disease_treatments_type_check",
        ),
        sa.ForeignKeyConstraint(["disease_id"], ["intelligence.diseases.id"], ondelete="CASCADE", name="disease_treatments_disease_fk"),
        schema="intelligence",
    )
    op.create_index("idx_disease_treatments_disease", "disease_treatments", ["disease_id"], schema="intelligence")

    # --- disease_reports ---
    op.create_table(
        "disease_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True, nullable=False),
        sa.Column("farmer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plot_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("crop_cycle_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("image_url", sa.String(512), nullable=False),
        sa.Column("image_thumbnail_url", sa.String(512), nullable=True),
        sa.Column("image_metadata", postgresql.JSONB, nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("farmer_notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(30), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("officer_diagnosis", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed', 'officer_review', 'reviewed')",
            name="disease_reports_status_check",
        ),
        sa.ForeignKeyConstraint(["farmer_id"], ["identity.users.id"], ondelete="CASCADE", name="disease_reports_farmer_fk"),
        sa.ForeignKeyConstraint(["plot_id"], ["farmer.plots.id"], ondelete="SET NULL", name="disease_reports_plot_fk"),
        sa.ForeignKeyConstraint(["crop_cycle_id"], ["farmer.crop_cycles.id"], ondelete="SET NULL", name="disease_reports_crop_cycle_fk"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["identity.users.id"], ondelete="SET NULL", name="disease_reports_reviewed_by_fk"),
        schema="intelligence",
    )
    op.create_index("idx_disease_reports_farmer", "disease_reports", ["farmer_id"], schema="intelligence")
    op.create_index("idx_disease_reports_plot", "disease_reports", ["plot_id"], schema="intelligence")
    op.create_index("idx_disease_reports_status", "disease_reports", ["status"], schema="intelligence")
    op.create_index(
        "idx_disease_reports_farmer_submitted",
        "disease_reports",
        ["farmer_id", "submitted_at"],
        schema="intelligence",
    )

    # Trigger for updated_at
    op.execute("""
        CREATE TRIGGER disease_reports_set_updated_at
            BEFORE UPDATE ON intelligence.disease_reports
            FOR EACH ROW
            EXECUTE FUNCTION identity.set_updated_at();
    """)

    # --- disease_predictions ---
    op.create_table(
        "disease_predictions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True, nullable=False),
        sa.Column("report_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("disease_slug", sa.String(100), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("all_predictions", postgresql.JSONB, nullable=False),
        sa.Column("model_name", sa.String(50), server_default=sa.text("'disease_classifier'"), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=False),
        sa.Column("inference_time_ms", sa.Integer(), nullable=False),
        sa.Column("is_reliable", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("heat_map_url", sa.String(512), nullable=True),
        sa.Column("inferred_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="disease_predictions_confidence_check"),
        sa.ForeignKeyConstraint(["report_id"], ["intelligence.disease_reports.id"], ondelete="CASCADE", name="disease_predictions_report_fk"),
        sa.UniqueConstraint("report_id", name="disease_predictions_report_unique"),
        schema="intelligence",
    )
    op.create_index("idx_disease_predictions_slug", "disease_predictions", ["disease_slug"], schema="intelligence")
    op.create_index("idx_disease_predictions_model", "disease_predictions", ["model_name", "model_version"], schema="intelligence")
    op.create_index(
        "idx_disease_predictions_unreliable",
        "disease_predictions",
        ["disease_slug"],
        postgresql_where=sa.text("is_reliable = false"),
        schema="intelligence",
    )

    # --- disease_feedback ---
    op.create_table(
        "disease_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True, nullable=False),
        sa.Column("report_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("farmer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("feedback_type", sa.String(30), nullable=False),
        sa.Column("suggested_disease_slug", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.CheckConstraint(
            "feedback_type IN ('correct', 'incorrect', 'partially_correct')",
            name="disease_feedback_type_check",
        ),
        sa.ForeignKeyConstraint(["report_id"], ["intelligence.disease_reports.id"], ondelete="CASCADE", name="disease_feedback_report_fk"),
        sa.ForeignKeyConstraint(["farmer_id"], ["identity.users.id"], ondelete="CASCADE", name="disease_feedback_farmer_fk"),
        schema="intelligence",
    )
    op.create_index("idx_disease_feedback_report", "disease_feedback", ["report_id"], schema="intelligence")
    op.create_index("idx_disease_feedback_farmer", "disease_feedback", ["farmer_id"], schema="intelligence")


def downgrade() -> None:
    op.drop_index("idx_disease_feedback_farmer", schema="intelligence")
    op.drop_index("idx_disease_feedback_report", schema="intelligence")
    op.drop_table("disease_feedback", schema="intelligence")

    op.drop_index("idx_disease_predictions_unreliable", schema="intelligence")
    op.drop_index("idx_disease_predictions_model", schema="intelligence")
    op.drop_index("idx_disease_predictions_slug", schema="intelligence")
    op.drop_table("disease_predictions", schema="intelligence")

    op.execute("DROP TRIGGER IF EXISTS disease_reports_set_updated_at ON intelligence.disease_reports;")
    op.drop_index("idx_disease_reports_farmer_submitted", schema="intelligence")
    op.drop_index("idx_disease_reports_status", schema="intelligence")
    op.drop_index("idx_disease_reports_plot", schema="intelligence")
    op.drop_index("idx_disease_reports_farmer", schema="intelligence")
    op.drop_table("disease_reports", schema="intelligence")

    op.drop_index("idx_disease_treatments_disease", schema="intelligence")
    op.drop_table("disease_treatments", schema="intelligence")

    op.execute("DROP TRIGGER IF EXISTS diseases_set_updated_at ON intelligence.diseases;")
    op.drop_index("idx_diseases_active", schema="intelligence")
    op.drop_index("idx_diseases_slug", schema="intelligence")
    op.drop_table("diseases", schema="intelligence")
