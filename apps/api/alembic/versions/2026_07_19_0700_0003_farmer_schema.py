"""Create farmer schema: crops, plots, plot_boundaries, crop_cycles

Creates the `farmer` schema (already exists from migration 0001) and the
following tables:
- farmer.crops            (master data, seeded by 0004_seed_crops)
- farmer.plots            (farmer's registered plots with PostGIS boundary)
- farmer.plot_boundaries  (historical boundary snapshots)
- farmer.crop_cycles      (crop rotations per plot per season)

The plots.boundary column uses PostGIS GEOGRAPHY(POLYGON, 4326) — geographic
coordinates in WGS84 (lat/lon). PostGIS provides spatial functions:
- ST_Area()      — area in square meters
- ST_Centroid()  — geometric center
- ST_Contains()  — point-in-polygon
- ST_Intersects()— overlap detection

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-19

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geography
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Schema already created in migration 0001, but ensure it exists
    op.execute("CREATE SCHEMA IF NOT EXISTS farmer;")

    # --- crops (master data) ---
    op.create_table(
        "crops",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True, nullable=False),
        sa.Column("slug", sa.String(50), nullable=False),
        sa.Column("name_en", sa.String(100), nullable=False),
        sa.Column("name_hi", sa.String(100), nullable=True),
        sa.Column("scientific_name", sa.String(200), nullable=True),
        sa.Column("crop_category", sa.String(30), nullable=False),
        sa.Column("primary_season", sa.String(20), nullable=False),
        sa.Column("duration_days_min", sa.Integer(), nullable=False),
        sa.Column("duration_days_max", sa.Integer(), nullable=False),
        sa.Column("water_requirement_mm", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.CheckConstraint(
            "primary_season IN ('kharif', 'rabi', 'zaid')",
            name="crops_season_check",
        ),
        sa.CheckConstraint(
            "crop_category IN ('cereals', 'pulses', 'oilseeds', 'fibre', 'sugar', 'plantation', 'horticulture', 'spices', 'fodder')",
            name="crops_category_check",
        ),
        sa.UniqueConstraint("slug", name="crops_slug_unique"),
        schema="farmer",
    )
    op.create_index("idx_crops_slug", "crops", ["slug"], schema="farmer")
    op.create_index(
        "idx_crops_active",
        "crops",
        ["slug"],
        postgresql_where=sa.text("is_active = true"),
        schema="farmer",
    )

    # --- plots ---
    op.create_table(
        "plots",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True, nullable=False),
        sa.Column("farmer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("survey_number", sa.String(100), nullable=False),
        sa.Column("village", sa.String(255), nullable=False),
        sa.Column("district", sa.String(100), nullable=False),
        sa.Column("state", sa.String(100), nullable=False),
        sa.Column("pincode", sa.String(10), nullable=True),
        sa.Column("area_ha", sa.Numeric(10, 4), nullable=False),
        sa.Column("boundary", Geography(geometry_type="POLYGON", srid=4326), nullable=False),
        sa.Column("centroid", Geography(geometry_type="POINT", srid=4326), nullable=True),
        sa.Column("soil_type", sa.String(50), nullable=True),
        sa.Column("soil_ph", sa.Numeric(4, 2), nullable=True),
        sa.Column("irrigation_source", sa.String(20), nullable=True),
        sa.Column("ownership_type", sa.String(20), server_default=sa.text("'owned'"), nullable=False),
        sa.Column("lessor_name", sa.String(255), nullable=True),
        sa.Column("lease_start_date", sa.Date(), nullable=True),
        sa.Column("lease_end_date", sa.Date(), nullable=True),
        sa.Column("verification_status", sa.String(30), server_default=sa.text("'pending'"), nullable=False),
        sa.Column("verified_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_notes", sa.Text(), nullable=True),
        sa.Column("nickname", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.CheckConstraint(
            "irrigation_source IS NULL OR irrigation_source IN ('canal', 'borewell', 'river', 'rainfed', 'drip', 'sprinkler', 'tank', 'other')",
            name="plots_irrigation_check",
        ),
        sa.CheckConstraint(
            "ownership_type IN ('owned', 'leased', 'shared')",
            name="plots_ownership_type_check",
        ),
        sa.CheckConstraint(
            "verification_status IN ('pending', 'verified', 'rejected', 'resubmission_requested')",
            name="plots_verification_status_check",
        ),
        sa.CheckConstraint("area_ha > 0", name="plots_area_positive_check"),
        sa.ForeignKeyConstraint(["farmer_id"], ["identity.users.id"], ondelete="CASCADE", name="plots_farmer_fk"),
        sa.ForeignKeyConstraint(["verified_by"], ["identity.users.id"], ondelete="SET NULL", name="plots_verified_by_fk"),
        sa.UniqueConstraint(
            "farmer_id",
            "survey_number",
            "village",
            "district",
            "state",
            name="plots_farmer_survey_unique",
        ),
        schema="farmer",
    )

    # Indexes
    op.create_index("idx_plots_farmer", "plots", ["farmer_id"], schema="farmer")
    op.create_index("idx_plots_district", "plots", ["district"], schema="farmer")
    op.create_index("idx_plots_verification", "plots", ["verification_status"], schema="farmer")
    op.create_index("idx_plots_state_district", "plots", ["state", "district"], schema="farmer")
    # GiST indexes for spatial queries (ST_Contains, ST_Intersects, ST_Distance)
    op.execute(
        "CREATE INDEX idx_plots_boundary_gist ON farmer.plots USING GIST (boundary);"
    )
    op.execute(
        "CREATE INDEX idx_plots_centroid_gist ON farmer.plots USING GIST (centroid);"
    )

    # Trigger: auto-update centroid and updated_at
    op.execute("""
        CREATE OR REPLACE FUNCTION farmer.set_plot_centroid_and_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            -- Auto-compute centroid from boundary if not set
            IF NEW.boundary IS NOT NULL THEN
                NEW.centroid := ST_Centroid(NEW.boundary::geometry)::geography;
            END IF;
            NEW.updated_at := NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER plots_set_centroid_updated_at
            BEFORE INSERT OR UPDATE ON farmer.plots
            FOR EACH ROW
            EXECUTE FUNCTION farmer.set_plot_centroid_and_updated_at();
    """)

    # --- plot_boundaries (historical) ---
    op.create_table(
        "plot_boundaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True, nullable=False),
        sa.Column("plot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("boundary", Geography(geometry_type="POLYGON", srid=4326), nullable=False),
        sa.Column("area_ha", sa.Numeric(10, 4), nullable=False),
        sa.Column("source", sa.String(30), server_default=sa.text("'user_drawn'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint(
            "source IN ('user_drawn', 'satellite_detected', 'officer_corrected', 'imported')",
            name="plot_boundaries_source_check",
        ),
        sa.ForeignKeyConstraint(["plot_id"], ["farmer.plots.id"], ondelete="CASCADE", name="plot_boundaries_plot_fk"),
        sa.ForeignKeyConstraint(["created_by"], ["identity.users.id"], name="plot_boundaries_created_by_fk"),
        schema="farmer",
    )
    op.create_index("idx_plot_boundaries_plot", "plot_boundaries", ["plot_id"], schema="farmer")
    op.create_index(
        "idx_plot_boundaries_created_at",
        "plot_boundaries",
        ["created_at"],
        schema="farmer",
    )

    # --- crop_cycles ---
    op.create_table(
        "crop_cycles",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True, nullable=False),
        sa.Column("plot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("crop_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("season", sa.String(20), nullable=False),
        sa.Column("season_year", sa.Integer(), nullable=False),
        sa.Column("sowing_date", sa.Date(), nullable=True),
        sa.Column("expected_harvest_date", sa.Date(), nullable=True),
        sa.Column("actual_harvest_date", sa.Date(), nullable=True),
        sa.Column("area_ha", sa.Numeric(10, 4), nullable=False),
        sa.Column("status", sa.String(20), server_default=sa.text("'planned'"), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.CheckConstraint(
            "season IN ('kharif', 'rabi', 'zaid')",
            name="crop_cycles_season_check",
        ),
        sa.CheckConstraint(
            "status IN ('planned', 'sown', 'growing', 'harvested', 'failed')",
            name="crop_cycles_status_check",
        ),
        sa.CheckConstraint("area_ha > 0", name="crop_cycles_area_positive_check"),
        sa.CheckConstraint("season_year >= 2000 AND season_year <= 2100", name="crop_cycles_year_check"),
        sa.ForeignKeyConstraint(["plot_id"], ["farmer.plots.id"], ondelete="CASCADE", name="crop_cycles_plot_fk"),
        sa.ForeignKeyConstraint(["crop_id"], ["farmer.crops.id"], ondelete="RESTRICT", name="crop_cycles_crop_fk"),
        schema="farmer",
    )
    op.create_index("idx_crop_cycles_plot", "crop_cycles", ["plot_id"], schema="farmer")
    op.create_index("idx_crop_cycles_crop", "crop_cycles", ["crop_id"], schema="farmer")
    op.create_index("idx_crop_cycles_status", "crop_cycles", ["status"], schema="farmer")
    op.create_index(
        "idx_crop_cycles_active",
        "crop_cycles",
        ["plot_id"],
        postgresql_where=sa.text("status IN ('sown', 'growing')"),
        schema="farmer",
    )

    # Trigger for updated_at
    op.execute("""
        CREATE TRIGGER crop_cycles_set_updated_at
            BEFORE UPDATE ON farmer.crop_cycles
            FOR EACH ROW
            EXECUTE FUNCTION identity.set_updated_at();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS crop_cycles_set_updated_at ON farmer.crop_cycles;")
    op.drop_index("idx_crop_cycles_active", schema="farmer")
    op.drop_index("idx_crop_cycles_status", schema="farmer")
    op.drop_index("idx_crop_cycles_crop", schema="farmer")
    op.drop_index("idx_crop_cycles_plot", schema="farmer")
    op.drop_table("crop_cycles", schema="farmer")

    op.drop_index("idx_plot_boundaries_created_at", schema="farmer")
    op.drop_index("idx_plot_boundaries_plot", schema="farmer")
    op.drop_table("plot_boundaries", schema="farmer")

    op.execute("DROP TRIGGER IF EXISTS plots_set_centroid_updated_at ON farmer.plots;")
    op.execute("DROP FUNCTION IF EXISTS farmer.set_plot_centroid_and_updated_at();")
    op.execute("DROP INDEX IF EXISTS farmer.idx_plots_centroid_gist;")
    op.execute("DROP INDEX IF EXISTS farmer.idx_plots_boundary_gist;")
    op.drop_index("idx_plots_state_district", schema="farmer")
    op.drop_index("idx_plots_verification", schema="farmer")
    op.drop_index("idx_plots_district", schema="farmer")
    op.drop_index("idx_plots_farmer", schema="farmer")
    op.drop_table("plots", schema="farmer")

    op.drop_index("idx_crops_active", schema="farmer")
    op.drop_index("idx_crops_slug", schema="farmer")
    op.drop_table("crops", schema="farmer")
