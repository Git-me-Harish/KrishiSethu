"""

Revision ID: 0008
Revises: 0007
Create Date: 2026-07-19

"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- ndvi_observations (partitioned by month) ---
    op.create_table(
        "ndvi_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("plot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("ndvi_mean", sa.Numeric(5, 4), nullable=False),
        sa.Column("ndvi_min", sa.Numeric(5, 4), nullable=False),
        sa.Column("ndvi_max", sa.Numeric(5, 4), nullable=False),
        sa.Column("ndvi_stddev", sa.Numeric(5, 4), nullable=False),
        sa.Column("cloud_cover_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("valid_pixel_count", sa.Integer(), nullable=False),
        sa.Column("total_pixel_count", sa.Integer(), nullable=False),
        sa.Column("raster_url", sa.String(512), nullable=True),
        sa.Column("thumbnail_url", sa.String(512), nullable=True),
        sa.Column("raw_metadata", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.CheckConstraint(
            "source IN ('sentinel2', 'landsat8', 'synthetic')",
            name="ndvi_obs_source_check",
        ),
        sa.CheckConstraint(
            "ndvi_mean >= -1 AND ndvi_mean <= 1",
            name="ndvi_obs_mean_range_check",
        ),
        sa.CheckConstraint(
            "cloud_cover_pct >= 0 AND cloud_cover_pct <= 100",
            name="ndvi_obs_cloud_cover_range_check",
        ),
        sa.ForeignKeyConstraint(["plot_id"], ["farmer.plots.id"], ondelete="CASCADE", name="ndvi_obs_plot_fk"),
        sa.UniqueConstraint("plot_id", "observed_at", "source", name="ndvi_obs_plot_time_source_unique"),
        sa.PrimaryKeyConstraint("id", "observed_at"),
        schema="intelligence",
    )

    # Convert to partitioned table
    op.execute("""
        ALTER TABLE intelligence.ndvi_observations
        PARTITION BY RANGE (observed_at);
    """)

    # Create monthly partitions for Jul 2026 - Jun 2027 (12 months)
    op.execute("""
        CREATE TABLE intelligence.ndvi_observations_2026_07
        PARTITION OF intelligence.ndvi_observations
        FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');

        CREATE TABLE intelligence.ndvi_observations_2026_08
        PARTITION OF intelligence.ndvi_observations
        FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');

        CREATE TABLE intelligence.ndvi_observations_2026_09
        PARTITION OF intelligence.ndvi_observations
        FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');

        CREATE TABLE intelligence.ndvi_observations_2026_10
        PARTITION OF intelligence.ndvi_observations
        FOR VALUES FROM ('2026-10-01') TO ('2026-11-01');

        CREATE TABLE intelligence.ndvi_observations_2026_11
        PARTITION OF intelligence.ndvi_observations
        FOR VALUES FROM ('2026-11-01') TO ('2026-12-01');

        CREATE TABLE intelligence.ndvi_observations_2026_12
        PARTITION OF intelligence.ndvi_observations
        FOR VALUES FROM ('2026-12-01') TO ('2027-01-01');

        CREATE TABLE intelligence.ndvi_observations_2027_01
        PARTITION OF intelligence.ndvi_observations
        FOR VALUES FROM ('2027-01-01') TO ('2027-02-01');

        CREATE TABLE intelligence.ndvi_observations_2027_02
        PARTITION OF intelligence.ndvi_observations
        FOR VALUES FROM ('2027-02-01') TO ('2027-03-01');

        CREATE TABLE intelligence.ndvi_observations_2027_03
        PARTITION OF intelligence.ndvi_observations
        FOR VALUES FROM ('2027-03-01') TO ('2027-04-01');

        CREATE TABLE intelligence.ndvi_observations_2027_04
        PARTITION OF intelligence.ndvi_observations
        FOR VALUES FROM ('2027-04-01') TO ('2027-05-01');

        CREATE TABLE intelligence.ndvi_observations_2027_05
        PARTITION OF intelligence.ndvi_observations
        FOR VALUES FROM ('2027-05-01') TO ('2027-06-01');

        CREATE TABLE intelligence.ndvi_observations_2027_06
        PARTITION OF intelligence.ndvi_observations
        FOR VALUES FROM ('2027-06-01') TO ('2027-07-01');

        CREATE TABLE intelligence.ndvi_observations_default
        PARTITION OF intelligence.ndvi_observations
        DEFAULT;
    """)

    # Indexes (propagated to all partitions)
    op.execute("""
        CREATE INDEX idx_ndvi_obs_plot_time
        ON intelligence.ndvi_observations (plot_id, observed_at DESC);
    """)
    op.execute("""
        CREATE INDEX idx_ndvi_obs_time
        ON intelligence.ndvi_observations (observed_at DESC);
    """)
    op.execute("""
        CREATE INDEX idx_ndvi_obs_source
        ON intelligence.ndvi_observations (source);
    """)

    # --- ndvi_anomaly_alerts ---
    op.create_table(
        "ndvi_anomaly_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True, nullable=False),
        sa.Column("plot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("farmer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("anomaly_type", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), server_default=sa.text("'active'"), nullable=False),
        sa.Column("previous_ndvi", sa.Numeric(5, 4), nullable=False),
        sa.Column("current_ndvi", sa.Numeric(5, 4), nullable=False),
        sa.Column("drop_magnitude", sa.Numeric(5, 4), nullable=False),
        sa.Column("previous_observation_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("current_observation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("notification_sent", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("notification_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.CheckConstraint(
            "anomaly_type IN ('significant_drop', 'severe_drop', 'low_vegetation', 'prolonged_decline')",
            name="ndvi_anomaly_type_check",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'acknowledged', 'investigating', 'resolved')",
            name="ndvi_anomaly_status_check",
        ),
        sa.ForeignKeyConstraint(["plot_id"], ["farmer.plots.id"], ondelete="CASCADE", name="ndvi_anomaly_plot_fk"),
        sa.ForeignKeyConstraint(["farmer_id"], ["identity.users.id"], ondelete="CASCADE", name="ndvi_anomaly_farmer_fk"),
        schema="intelligence",
    )
    op.create_index("idx_ndvi_anomaly_plot", "ndvi_anomaly_alerts", ["plot_id"], schema="intelligence")
    op.create_index("idx_ndvi_anomaly_farmer", "ndvi_anomaly_alerts", ["farmer_id"], schema="intelligence")
    op.create_index("idx_ndvi_anomaly_type", "ndvi_anomaly_alerts", ["anomaly_type"], schema="intelligence")
    op.create_index("idx_ndvi_anomaly_status", "ndvi_anomaly_alerts", ["status"], schema="intelligence")
    op.create_index(
        "idx_ndvi_anomaly_active",
        "ndvi_anomaly_alerts",
        ["farmer_id", "plot_id"],
        postgresql_where=sa.text("status IN ('active', 'acknowledged', 'investigating')"),
        schema="intelligence",
    )

    # Trigger for updated_at
    op.execute("""
        CREATE TRIGGER ndvi_anomaly_alerts_set_updated_at
            BEFORE UPDATE ON intelligence.ndvi_anomaly_alerts
            FOR EACH ROW
            EXECUTE FUNCTION identity.set_updated_at();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS ndvi_anomaly_alerts_set_updated_at ON intelligence.ndvi_anomaly_alerts;")
    op.drop_index("idx_ndvi_anomaly_active", schema="intelligence")
    op.drop_index("idx_ndvi_anomaly_status", schema="intelligence")
    op.drop_index("idx_ndvi_anomaly_type", schema="intelligence")
    op.drop_index("idx_ndvi_anomaly_farmer", schema="intelligence")
    op.drop_index("idx_ndvi_anomaly_plot", schema="intelligence")
    op.drop_table("ndvi_anomaly_alerts", schema="intelligence")

    op.execute("DROP INDEX IF EXISTS intelligence.idx_ndvi_obs_source;")
    op.execute("DROP INDEX IF EXISTS intelligence.idx_ndvi_obs_time;")
    op.execute("DROP INDEX IF EXISTS intelligence.idx_ndvi_obs_plot_time;")
    op.execute("DROP TABLE IF EXISTS intelligence.ndvi_observations_default;")
    for month in range(6, 13):  # 2026-07 to 2026-12
        op.execute(f"DROP TABLE IF EXISTS intelligence.ndvi_observations_2026_{month:02d};")
    for month in range(1, 7):  # 2027-01 to 2027-06
        op.execute(f"DROP TABLE IF EXISTS intelligence.ndvi_observations_2027_{month:02d};")
    op.execute("DROP TABLE IF EXISTS intelligence.ndvi_observations;")
