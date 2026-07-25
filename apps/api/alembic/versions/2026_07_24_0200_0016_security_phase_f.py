"""Phase F: Security hardening schema — audit logs, consent, DSRs, grievances

Creates four new tables across two new schemas:
- audit.audit_logs        — append-only audit trail (PII access, auth events, etc.)
- privacy.consent_records — DPDP consent grants/withdrawals
- privacy.consent_notices — versioned consent notice text (provenance)
- privacy.data_subject_requests — DPDP data subject rights requests
- privacy.grievances      — DPDP Section 13 grievance redressal

Revision ID: 0016
Revises: 0015
Create Date: 2026-07-24

Indexes:
- audit_logs: actor_id, action, resource_type, occurred_at, request_id
- consent_records: user_id, purpose, status (partial unique on active grants)
- data_subject_requests: user_id, status, due_at (for SLA monitoring)
- grievances: user_id, status, due_at
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Create schemas ---
    op.execute("CREATE SCHEMA IF NOT EXISTS audit;")
    op.execute("CREATE SCHEMA IF NOT EXISTS privacy;")

    # --- audit.audit_logs ---
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True, nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column("outcome", sa.String(20), server_default=sa.text("'success'"), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_role", sa.String(20), nullable=True),
        sa.Column("resource_type", sa.String(50), nullable=True),
        sa.Column("resource_id", sa.String(64), nullable=True),
        sa.Column("details", postgresql.JSONB, server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True, index=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.CheckConstraint(
            "outcome IN ('success', 'failure', 'denied', 'error')",
            name="audit_logs_outcome_check",
        ),
        schema="audit",
    )
    op.create_index("idx_audit_logs_actor", "audit_logs", ["actor_id"], schema="audit", postgresql_where=sa.text("actor_id IS NOT NULL"))
    op.create_index("idx_audit_logs_action", "audit_logs", ["action"], schema="audit")
    op.create_index("idx_audit_logs_resource", "audit_logs", ["resource_type", "resource_id"], schema="audit")
    op.create_index("idx_audit_logs_occurred", "audit_logs", ["occurred_at"], schema="audit")
    op.create_index("idx_audit_logs_outcome", "audit_logs", ["outcome"], schema="audit")
    op.create_index("idx_audit_logs_action_time", "audit_logs", ["action", "occurred_at"], schema="audit")

    # Append-only enforcement: deny UPDATE and DELETE to all roles except
    # a dedicated audit_admin role (which we don't grant to any app role).
    # Application code writes via INSERT only — see core/audit_logger.py.
    op.execute("""
        REVOKE UPDATE, DELETE ON audit.audit_logs FROM PUBLIC;
    """)
    # Note: app DB user retains INSERT, SELECT only via existing grants on schema.

    # --- privacy.consent_notices ---
    op.create_table(
        "consent_notices",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True, nullable=False),
        sa.Column("version", sa.String(20), nullable=False, unique=True),
        sa.Column("purpose", sa.String(50), nullable=False, index=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("full_text", sa.Text(), nullable=False),
        sa.Column("text_hash", sa.String(64), nullable=False, index=True),
        sa.Column("language", sa.String(5), server_default=sa.text("'en'"), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        schema="privacy",
    )

    # --- privacy.consent_records ---
    op.create_table(
        "consent_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purpose", sa.String(50), nullable=False, index=True),
        sa.Column("status", sa.String(20), server_default=sa.text("'granted'"), nullable=False, index=True),
        sa.Column("notice_version", sa.String(20), nullable=False),
        sa.Column("notice_text_hash", sa.String(64), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("granted_from_ip", sa.String(45), nullable=True),
        sa.Column("withdrawn_from_ip", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.Column("withdrawn_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("withdrawal_reason", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('granted', 'withdrawn', 'expired')",
            name="consent_records_status_check",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["identity.users.id"], ondelete="CASCADE", name="consent_records_user_fk"),
        sa.ForeignKeyConstraint(["withdrawn_by"], ["identity.users.id"], ondelete="SET NULL", name="consent_records_withdrawn_by_fk"),
        schema="privacy",
    )
    op.create_index("idx_consent_user", "consent_records", ["user_id"], schema="privacy")
    op.create_index("idx_consent_user_purpose", "consent_records", ["user_id", "purpose"], schema="privacy")
    op.create_index("idx_consent_status", "consent_records", ["status"], schema="privacy")
    # Partial unique: at most one ACTIVE grant per (user, purpose)
    op.execute("""
        CREATE UNIQUE INDEX consent_one_active_per_purpose
            ON privacy.consent_records (user_id, purpose)
            WHERE status = 'granted';
    """)

    # --- privacy.data_subject_requests ---
    op.create_table(
        "data_subject_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_type", sa.String(20), nullable=False, index=True),
        sa.Column("status", sa.String(30), server_default=sa.text("'submitted'"), nullable=False, index=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("requested_changes", postgresql.JSONB, nullable=True),
        sa.Column("export_url", sa.String(1024), nullable=True),
        sa.Column("export_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("assigned_to", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.CheckConstraint(
            "request_type IN ('access', 'correction', 'erasure', 'portability', 'restriction')",
            name="dsr_type_check",
        ),
        sa.CheckConstraint(
            "status IN ('submitted', 'acknowledged', 'in_review', 'processing', 'awaiting_verification', 'completed', 'rejected', 'withdrawn')",
            name="dsr_status_check",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["identity.users.id"], ondelete="CASCADE", name="dsr_user_fk"),
        sa.ForeignKeyConstraint(["assigned_to"], ["identity.users.id"], ondelete="SET NULL", name="dsr_assigned_to_fk"),
        schema="privacy",
    )
    op.create_index("idx_dsr_user", "data_subject_requests", ["user_id"], schema="privacy")
    op.create_index("idx_dsr_status", "data_subject_requests", ["status"], schema="privacy")
    op.create_index("idx_dsr_due", "data_subject_requests", ["due_at"], schema="privacy")
    op.create_index("idx_dsr_type_status", "data_subject_requests", ["request_type", "status"], schema="privacy")

    # --- privacy.grievances ---
    op.create_table(
        "grievances",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True, nullable=False),
        sa.Column("grievance_number", sa.String(30), nullable=False, unique=True, index=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), server_default=sa.text("'filed'"), nullable=False, index=True),
        sa.Column("filed_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("assigned_to", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("escalation_reference", sa.String(100), nullable=True),
        sa.Column("attachments", postgresql.JSONB, nullable=True),
        sa.Column("metadata", postgresql.JSONB, nullable=True),
        sa.CheckConstraint(
            "status IN ('filed', 'acknowledged', 'in_review', 'resolved', 'escalated', 'rejected')",
            name="grievances_status_check",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["identity.users.id"], ondelete="CASCADE", name="grievances_user_fk"),
        sa.ForeignKeyConstraint(["assigned_to"], ["identity.users.id"], ondelete="SET NULL", name="grievances_assigned_to_fk"),
        schema="privacy",
    )
    op.create_index("idx_grievances_user", "grievances", ["user_id"], schema="privacy")
    op.create_index("idx_grievances_status", "grievances", ["status"], schema="privacy")
    op.create_index("idx_grievances_due", "grievances", ["due_at"], schema="privacy")
    op.create_index("idx_grievances_category", "grievances", ["category"], schema="privacy")


def downgrade() -> None:
    # grievances
    op.drop_index("idx_grievances_category", schema="privacy")
    op.drop_index("idx_grievances_due", schema="privacy")
    op.drop_index("idx_grievances_status", schema="privacy")
    op.drop_index("idx_grievances_user", schema="privacy")
    op.drop_table("grievances", schema="privacy")

    # DSRs
    op.drop_index("idx_dsr_type_status", schema="privacy")
    op.drop_index("idx_dsr_due", schema="privacy")
    op.drop_index("idx_dsr_status", schema="privacy")
    op.drop_index("idx_dsr_user", schema="privacy")
    op.drop_table("data_subject_requests", schema="privacy")

    # consent_records
    op.execute("DROP INDEX IF EXISTS privacy.consent_one_active_per_purpose;")
    op.drop_index("idx_consent_status", schema="privacy")
    op.drop_index("idx_consent_user_purpose", schema="privacy")
    op.drop_index("idx_consent_user", schema="privacy")
    op.drop_table("consent_records", schema="privacy")

    # consent_notices
    op.drop_table("consent_notices", schema="privacy")

    # audit_logs
    op.drop_index("idx_audit_logs_action_time", schema="audit")
    op.drop_index("idx_audit_logs_outcome", schema="audit")
    op.drop_index("idx_audit_logs_occurred", schema="audit")
    op.drop_index("idx_audit_logs_resource", schema="audit")
    op.drop_index("idx_audit_logs_action", schema="audit")
    op.drop_index("idx_audit_logs_actor", schema="audit")
    op.drop_table("audit_logs", schema="audit")
