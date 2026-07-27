"""Create NDVI tables: ndvi_observations (partitioned), ndvi_anomaly_alerts

Creates:
- intelligence.ndvi_observations (RANGE-partitioned by observed_at, monthly)
- intelligence.ndvi_anomaly_alerts (per-plot anomaly alerts)

ndvi_observations stores summary statistics per (plot, observation_time).
The full NDVI raster is stored in S3 (raster_url) and served via pre-signed URLs.
With 1M plots × weekly observations × 2 years = ~100M rows, partitioning is essential.

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
    # PostgreSQL cannot convert an existing table to a partitioned table via
    # ALTER TABLE ... PARTITION BY — partitioning must be declared at CREATE
    # TABLE time. So this is a raw CREATE TABLE instead of op.create_table().
    # Note: FOREIGN KEY constraints referencing a partitioned table's rows
    # are fine here since plot_id -> farmer.plots.id is a FK *from* this
    # table, not to it.
    op.execute("""
        CREATE TABLE intelligence.ndvi_observations (
            id UUID NOT NULL,
            plot_id UUID NOT NULL,
            observed_at TIMESTAMPTZ NOT NULL,
            source VARCHAR(20) NOT NULL,
            ndvi_mean NUMERIC(5, 4) NOT NULL,
            ndvi_min NUMERIC(5, 4) NOT NULL,
            ndvi_max NUMERIC(5, 4) NOT NULL,
            ndvi_stddev NUMERIC(5, 4) NOT NULL,
            cloud_cover_pct NUMERIC(5, 2) NOT NULL,
            valid_pixel_count INTEGER NOT NULL,
            total_pixel_count INTEGER NOT NULL,
            raster_url VARCHAR(512),
            thumbnail_url VARCHAR(512),
            raw_metadata JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT ndvi_obs_source_check CHECK (source IN ('sentinel2', 'landsat8', 'synthetic')),
            CONSTRAINT ndvi_obs_mean_range_check CHECK (ndvi_mean >= -1 AND ndvi_mean <= 1),
            CONSTRAINT ndvi_obs_cloud_cover_range_check CHECK (cloud_cover_pct >= 0 AND cloud_cover_pct <= 100),
            CONSTRAINT ndvi_obs_plot_fk FOREIGN KEY (plot_id) REFERENCES farmer.plots (id) ON DELETE CASCADE,
            CONSTRAINT ndvi_obs_plot_time_source_unique UNIQUE (plot_id, observed_at, source),
            CONSTRAINT ndvi_observations_pkey PRIMARY KEY (id, observed_at)
        ) PARTITION BY RANGE (observed_at);
    """)

    # Create monthly partitions for Jul 2026 - Jun 2027 (12 months)
    # asyncpg cannot run multiple SQL commands in one prepared statement, so
    # each partition is its own op.execute() call.
    for month in range(6, 13):  # 2026-07 to 2026-12
        start = f"2026-{month:02d}-01"
        end_year, end_month = (2026, month + 1) if month < 12 else (2027, 1)
        end = f"{end_year}-{end_month:02d}-01"
        op.execute(f"""
            CREATE TABLE intelligence.ndvi_observations_2026_{month:02d}
            PARTITION OF intelligence.ndvi_observations
            FOR VALUES FROM ('{start}') TO ('{end}');
        """)
    for month in range(1, 7):  # 2027-01 to 2027-06
        start = f"2027-{month:02d}-01"
        end = f"2027-{month + 1:02d}-01"
        op.execute(f"""
            CREATE TABLE intelligence.ndvi_observations_2027_{month:02d}
            PARTITION OF intelligence.ndvi_observations
            FOR VALUES FROM ('{start}') TO ('{end}');
        """)

    op.execute("""
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
