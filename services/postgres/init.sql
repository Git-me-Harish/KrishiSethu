-- KrishiSetu PostgreSQL initialization script
-- Runs once when the Postgres container is first created (before Alembic migrations).
--
-- Responsibilities:
--   1. Create the application database and user (if not already created)
--   2. Enable required extensions
--
-- Note: Schema creation (identity, farmer, etc.) is handled by Alembic migrations,
-- not this script. This script only sets up extensions and roles.

-- Required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";       -- UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";        -- gen_random_uuid(), cryptographic functions
CREATE EXTENSION IF NOT EXISTS "postgis";         -- Geographic data types and functions
CREATE EXTENSION IF NOT EXISTS "postgis_topology"; -- PostGIS topology support
CREATE EXTENSION IF NOT EXISTS "pg_trgm";         -- Trigram matching for fuzzy search
CREATE EXTENSION IF NOT EXISTS "btree_gist";      -- GiST indexing for composite types
CREATE EXTENSION IF NOT EXISTS "pg_stat_statements"; -- Query statistics (requires restart to enable in postgresql.conf)

-- Set default search_path to include our schemas
ALTER DATABASE krishisetu SET search_path TO identity, farmer, intelligence, commerce, insurance, schemes, audit, notifications, public;

-- Grant permissions (the krishisetu user is the app's database user)
GRANT ALL PRIVILEGES ON DATABASE krishisetu TO krishisetu;

-- PostGIS requires schema-level grants
GRANT USAGE, CREATE ON SCHEMA public TO krishisetu;

-- Statement timeout (prevent runaway queries)
ALTER DATABASE krishisetu SET statement_timeout = '30s';
ALTER DATABASE krishisetu SET lock_timeout = '5s';
ALTER DATABASE krishisetu SET idle_in_transaction_session_timeout = '60s';
