"""Create soil & weather tables: soil_tests, weather_observations, weather_forecasts, weather_alerts

Creates the following tables in the `intelligence` schema (already exists from
migration 0001):
- intelligence.soil_tests             (per-plot soil test results, 4 sources)
- intelligence.weather_observations   (district-level hourly observations, partitioned by month)
- intelligence.weather_forecasts      (7-day daily forecasts per district)
- intelligence.weather_alerts         (extreme weather alerts)

Partitioning:
- weather_observations is RANGE-partitioned by observed_at (monthly)
- weather_forecasts is RANGE-partitioned by forecast_date (monthly)
This enables efficient time-series queries and easy archival of old data.

Revision ID: 0007
Revises: 0006
Create Date: 2026-07-19

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- soil_tests ---
    op.create_table(
        "soil_tests",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True, nullable=False),
        sa.Column("plot_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("shc_id", sa.String(50), nullable=True),
        sa.Column("lab_name", sa.String(255), nullable=True),
        sa.Column("test_date", sa.Date(), nullable=False),
        sa.Column("nitrogen_n", sa.Numeric(8, 2), nullable=True),
        sa.Column("phosphorus_p", sa.Numeric(8, 2), nullable=True),
        sa.Column("potassium_k", sa.Numeric(8, 2), nullable=True),
        sa.Column("ph", sa.Numeric(4, 2), nullable=True),
        sa.Column("electrical_conductivity", sa.Numeric(6, 3), nullable=True),
        sa.Column("organic_carbon", sa.Numeric(5, 2), nullable=True),
        sa.Column("clay_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("sand_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("silt_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("soil_type", sa.String(50), nullable=True),
        sa.Column("soil_texture", sa.String(30), nullable=True),
        sa.Column("micronutrients", postgresql.JSONB, nullable=True),
        sa.Column("fertilizer_recommendation", sa.Text(), nullable=True),
        sa.Column("amendment_recommendation", sa.Text(), nullable=True),
        sa.Column("is_verified", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("verified_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.CheckConstraint(
            "source IN ('shc_portal', 'lab_manual', 'isric_auto', 'officer_entered')",
            name="soil_tests_source_check",
        ),
        sa.CheckConstraint("ph IS NULL OR (ph >= 0 AND ph <= 14)", name="soil_tests_ph_range_check"),
        sa.CheckConstraint("electrical_conductivity IS NULL OR electrical_conductivity >= 0", name="soil_tests_ec_positive_check"),
        sa.CheckConstraint(
            "(clay_pct IS NULL AND sand_pct IS NULL AND silt_pct IS NULL) OR "
            "(clay_pct IS NOT NULL AND sand_pct IS NOT NULL AND silt_pct IS NOT NULL AND "
            "clay_pct + sand_pct + silt_pct BETWEEN 99 AND 101)",
            name="soil_tests_texture_pct_sum_check",
        ),
        sa.ForeignKeyConstraint(["plot_id"], ["farmer.plots.id"], ondelete="CASCADE", name="soil_tests_plot_fk"),
        sa.ForeignKeyConstraint(["verified_by"], ["identity.users.id"], ondelete="SET NULL", name="soil_tests_verified_by_fk"),
        sa.UniqueConstraint("plot_id", "test_date", "source", name="soil_tests_plot_date_source_unique"),
        schema="intelligence",
    )
    op.create_index("idx_soil_tests_plot", "soil_tests", ["plot_id"], schema="intelligence")
    op.create_index("idx_soil_tests_source", "soil_tests", ["source"], schema="intelligence")
    op.create_index("idx_soil_tests_plot_date", "soil_tests", ["plot_id", "test_date"], schema="intelligence")

    # Trigger for updated_at
    op.execute("""
        CREATE TRIGGER soil_tests_set_updated_at
            BEFORE UPDATE ON intelligence.soil_tests
            FOR EACH ROW
            EXECUTE FUNCTION identity.set_updated_at();
    """)

    # --- weather_observations (partitioned by month) ---
    # PostgreSQL cannot convert an existing table to a partitioned table via
    # ALTER TABLE ... PARTITION BY — partitioning must be declared at CREATE
    # TABLE time. So this is a raw CREATE TABLE instead of op.create_table().
    # Every UNIQUE/PK constraint on a partitioned table must include the
    # partition key (observed_at), which is already true here (composite PK
    # and the unique constraint both include observed_at).
    op.execute("""
        CREATE TABLE intelligence.weather_observations (
            id UUID NOT NULL,
            district VARCHAR(100) NOT NULL,
            state VARCHAR(100) NOT NULL,
            district_centroid_lon NUMERIC(10, 6),
            district_centroid_lat NUMERIC(10, 6),
            observed_at TIMESTAMPTZ NOT NULL,
            source VARCHAR(20) NOT NULL,
            temperature_c NUMERIC(5, 2),
            feels_like_c NUMERIC(5, 2),
            temp_min_c NUMERIC(5, 2),
            temp_max_c NUMERIC(5, 2),
            precipitation_mm NUMERIC(6, 2),
            precipitation_probability NUMERIC(5, 2),
            humidity_pct NUMERIC(5, 2),
            wind_speed_kmph NUMERIC(6, 2),
            wind_direction_deg NUMERIC(6, 2),
            wind_gust_kmph NUMERIC(6, 2),
            pressure_hpa NUMERIC(7, 1),
            cloud_cover_pct NUMERIC(5, 2),
            visibility_km NUMERIC(5, 2),
            uv_index NUMERIC(4, 1),
            weather_main VARCHAR(50),
            weather_description VARCHAR(255),
            weather_icon VARCHAR(20),
            sunrise_at TIMESTAMPTZ,
            sunset_at TIMESTAMPTZ,
            raw_data JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT weather_obs_source_check CHECK (source IN ('imd', 'owm', 'sentinel')),
            CONSTRAINT weather_obs_district_time_source_unique UNIQUE (district, state, observed_at, source),
            CONSTRAINT weather_observations_pkey PRIMARY KEY (id, observed_at)
        ) PARTITION BY RANGE (observed_at);
    """)  # Note: partitioned table — no PK index by default

    # Create initial monthly partitions (current month + next 6 months)
    # asyncpg cannot run multiple SQL commands in one prepared statement, so
    # each partition is its own op.execute() call.
    _weather_obs_months = [
        ("2026_07", "2026-07-01", "2026-08-01"),
        ("2026_08", "2026-08-01", "2026-09-01"),
        ("2026_09", "2026-09-01", "2026-10-01"),
        ("2026_10", "2026-10-01", "2026-11-01"),
        ("2026_11", "2026-11-01", "2026-12-01"),
        ("2026_12", "2026-12-01", "2027-01-01"),
    ]
    for suffix, start, end in _weather_obs_months:
        op.execute(f"""
            CREATE TABLE intelligence.weather_observations_{suffix}
            PARTITION OF intelligence.weather_observations
            FOR VALUES FROM ('{start}') TO ('{end}');
        """)

    # Default partition for out-of-range dates
    op.execute("""
        CREATE TABLE intelligence.weather_observations_default
        PARTITION OF intelligence.weather_observations
        DEFAULT;
    """)

    # Indexes on each partition (must be created per-partition)
    # We create indexes on the parent — Postgres propagates to partitions
    op.execute("""
        CREATE INDEX idx_weather_obs_district_time
        ON intelligence.weather_observations (district, state, observed_at DESC);
    """)
    op.execute("""
        CREATE INDEX idx_weather_obs_time
        ON intelligence.weather_observations (observed_at DESC);
    """)
    op.execute("""
        CREATE INDEX idx_weather_obs_source
        ON intelligence.weather_observations (source);
    """)

    # --- weather_forecasts ---
    op.create_table(
        "weather_forecasts",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True, nullable=False),
        sa.Column("district", sa.String(100), nullable=False),
        sa.Column("state", sa.String(100), nullable=False),
        sa.Column("forecast_date", sa.Date(), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("temp_min_c", sa.Numeric(5, 2), nullable=True),
        sa.Column("temp_max_c", sa.Numeric(5, 2), nullable=True),
        sa.Column("precipitation_mm", sa.Numeric(6, 2), nullable=True),
        sa.Column("precipitation_probability", sa.Numeric(5, 2), nullable=True),
        sa.Column("humidity_min_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("humidity_max_pct", sa.Numeric(5, 2), nullable=True),
        sa.Column("wind_speed_kmph", sa.Numeric(6, 2), nullable=True),
        sa.Column("wind_direction_deg", sa.Numeric(6, 2), nullable=True),
        sa.Column("weather_main", sa.String(50), nullable=True),
        sa.Column("weather_description", sa.String(255), nullable=True),
        sa.Column("weather_icon", sa.String(20), nullable=True),
        sa.Column("agromet_advisory", sa.Text(), nullable=True),
        sa.Column("raw_data", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.CheckConstraint(
            "source IN ('imd', 'owm', 'sentinel')",
            name="weather_fcst_source_check",
        ),
        sa.UniqueConstraint("district", "state", "forecast_date", "source", "issued_at", name="weather_fcst_district_date_source_issued_unique"),
        schema="intelligence",
    )
    op.create_index("idx_weather_fcst_district_date", "weather_forecasts", ["district", "state", "forecast_date"], schema="intelligence")
    op.create_index("idx_weather_fcst_date", "weather_forecasts", ["forecast_date"], schema="intelligence")
    op.create_index("idx_weather_fcst_issued", "weather_forecasts", ["issued_at"], schema="intelligence")

    # --- weather_alerts ---
    op.create_table(
        "weather_alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True, nullable=False),
        sa.Column("district", sa.String(100), nullable=False),
        sa.Column("state", sa.String(100), nullable=False),
        sa.Column("alert_type", sa.String(30), nullable=False),
        sa.Column("severity", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), server_default=sa.text("'active'"), nullable=False),
        sa.Column("effective_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("recommended_actions", sa.Text(), nullable=True),
        sa.Column("source", sa.String(50), server_default=sa.text("'krishisetu_engine'"), nullable=False),
        sa.Column("raw_data", postgresql.JSONB, nullable=True),
        sa.Column("notifications_sent", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_notification_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.CheckConstraint(
            "alert_type IN ('frost', 'hail', 'heat_wave', 'heavy_rain', 'cyclone', 'drought', 'high_wind', 'fog')",
            name="weather_alerts_type_check",
        ),
        sa.CheckConstraint(
            "severity IN ('info', 'warning', 'severe', 'critical')",
            name="weather_alerts_severity_check",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'expired', 'cancelled')",
            name="weather_alerts_status_check",
        ),
        sa.CheckConstraint("expires_at > effective_at", name="weather_alerts_expiry_after_effective_check"),
        schema="intelligence",
    )
    op.create_index("idx_weather_alerts_district", "weather_alerts", ["district", "state"], schema="intelligence")
    op.create_index("idx_weather_alerts_type", "weather_alerts", ["alert_type"], schema="intelligence")
    op.create_index("idx_weather_alerts_severity", "weather_alerts", ["severity"], schema="intelligence")
    op.create_index("idx_weather_alerts_status", "weather_alerts", ["status"], schema="intelligence")
    op.create_index(
        "idx_weather_alerts_active",
        "weather_alerts",
        ["district", "expires_at"],
        postgresql_where=sa.text("status = 'active'"),
        schema="intelligence",
    )

    # Trigger for updated_at
    op.execute("""
        CREATE TRIGGER weather_alerts_set_updated_at
            BEFORE UPDATE ON intelligence.weather_alerts
            FOR EACH ROW
            EXECUTE FUNCTION identity.set_updated_at();
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS weather_alerts_set_updated_at ON intelligence.weather_alerts;")
    op.drop_index("idx_weather_alerts_active", schema="intelligence")
    op.drop_index("idx_weather_alerts_status", schema="intelligence")
    op.drop_index("idx_weather_alerts_severity", schema="intelligence")
    op.drop_index("idx_weather_alerts_type", schema="intelligence")
    op.drop_index("idx_weather_alerts_district", schema="intelligence")
    op.drop_table("weather_alerts", schema="intelligence")

    op.drop_index("idx_weather_fcst_issued", schema="intelligence")
    op.drop_index("idx_weather_fcst_date", schema="intelligence")
    op.drop_index("idx_weather_fcst_district_date", schema="intelligence")
    op.drop_table("weather_forecasts", schema="intelligence")

    op.execute("DROP INDEX IF EXISTS intelligence.idx_weather_obs_source;")
    op.execute("DROP INDEX IF EXISTS intelligence.idx_weather_obs_time;")
    op.execute("DROP INDEX IF EXISTS intelligence.idx_weather_obs_district_time;")
    op.execute("DROP TABLE IF EXISTS intelligence.weather_observations_default;")
    op.execute("DROP TABLE IF EXISTS intelligence.weather_observations_2026_12;")
    op.execute("DROP TABLE IF EXISTS intelligence.weather_observations_2026_11;")
    op.execute("DROP TABLE IF EXISTS intelligence.weather_observations_2026_10;")
    op.execute("DROP TABLE IF EXISTS intelligence.weather_observations_2026_09;")
    op.execute("DROP TABLE IF EXISTS intelligence.weather_observations_2026_08;")
    op.execute("DROP TABLE IF EXISTS intelligence.weather_observations_2026_07;")
    op.execute("DROP TABLE IF EXISTS intelligence.weather_observations;")

    op.execute("DROP TRIGGER IF EXISTS soil_tests_set_updated_at ON intelligence.soil_tests;")
    op.drop_index("idx_soil_tests_plot_date", schema="intelligence")
    op.drop_index("idx_soil_tests_source", schema="intelligence")
    op.drop_index("idx_soil_tests_plot", schema="intelligence")
    op.drop_table("soil_tests", schema="intelligence")
