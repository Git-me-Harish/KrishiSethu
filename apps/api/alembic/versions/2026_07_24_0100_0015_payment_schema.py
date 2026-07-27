"""Create payment tables: payments, payment_webhooks

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-24

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- payments ---
    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True, nullable=False),
        sa.Column("payment_number", sa.String(50), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payment_type", sa.String(30), nullable=False),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reference_type", sa.String(30), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), server_default=sa.text("'INR'"), nullable=False),
        sa.Column("amount_refunded", sa.Numeric(12, 2), server_default=sa.text("0"), nullable=False),
        sa.Column("status", sa.String(30), server_default=sa.text("'created'"), nullable=False),
        sa.Column("provider", sa.String(20), server_default=sa.text("'razorpay'"), nullable=False),
        sa.Column("payment_method", sa.String(20), nullable=True),
        sa.Column("provider_order_id", sa.String(100), nullable=True),
        sa.Column("provider_payment_id", sa.String(100), nullable=True),
        sa.Column("provider_signature", sa.String(256), nullable=True),
        sa.Column("upi_id", sa.String(100), nullable=True),
        sa.Column("upi_intent_url", sa.String(512), nullable=True),
        sa.Column("is_escrow", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("escrow_released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_to_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("bank_account_number", sa.String(30), nullable=True),
        sa.Column("bank_ifsc", sa.String(15), nullable=True),
        sa.Column("bank_payout_reference", sa.String(100), nullable=True),
        sa.Column("refund_reason", sa.Text(), nullable=True),
        sa.Column("refunded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("notes", postgresql.JSONB, nullable=True),
        sa.Column("raw_provider_response", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "payment_type IN ('marketplace_order', 'insurance_premium', 'insurance_payout', 'scheme_fee', 'refund')",
            name="payments_type_check",
        ),
        sa.CheckConstraint(
            "status IN ('created', 'pending', 'authorized', 'captured', 'failed', 'refunded', 'partially_refunded', 'released', 'cancelled')",
            name="payments_status_check",
        ),
        sa.CheckConstraint(
            "provider IN ('razorpay', 'upi_direct', 'cod', 'dbt')",
            name="payments_provider_check",
        ),
        sa.CheckConstraint("amount > 0", name="payments_amount_positive"),
        sa.CheckConstraint("amount_refunded >= 0", name="payments_refunded_non_negative"),
        sa.ForeignKeyConstraint(["user_id"], ["identity.users.id"], ondelete="CASCADE", name="payments_user_fk"),
        sa.ForeignKeyConstraint(["released_to_user_id"], ["identity.users.id"], ondelete="SET NULL", name="payments_released_to_fk"),
        sa.UniqueConstraint("payment_number", name="payments_number_unique"),
        schema="commerce",
    )
    op.create_index("idx_payments_number", "payments", ["payment_number"], schema="commerce")
    op.create_index("idx_payments_user", "payments", ["user_id"], schema="commerce")
    op.create_index("idx_payments_type", "payments", ["payment_type"], schema="commerce")
    op.create_index("idx_payments_reference", "payments", ["reference_id", "reference_type"], schema="commerce")
    op.create_index("idx_payments_status", "payments", ["status"], schema="commerce")
    op.create_index("idx_payments_provider_order", "payments", ["provider_order_id"], schema="commerce", postgresql_where=sa.text("provider_order_id IS NOT NULL"))
    op.create_index("idx_payments_escrow", "payments", ["is_escrow", "status"], schema="commerce", postgresql_where=sa.text("is_escrow = true"))

    op.execute("""
        CREATE TRIGGER payments_set_updated_at
            BEFORE UPDATE ON commerce.payments
            FOR EACH ROW
            EXECUTE FUNCTION identity.set_updated_at();
    """)

    # --- payment_webhooks ---
    op.create_table(
        "payment_webhooks",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True, nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("event_id", sa.String(100), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("payment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("signature_verified", sa.Boolean(), nullable=False, default=False),
        sa.Column("processed", sa.Boolean(), server_default=sa.text("false"), nullable=False, default=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB, nullable=False),
        sa.Column("headers", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.ForeignKeyConstraint(["payment_id"], ["commerce.payments.id"], ondelete="SET NULL", name="payment_webhooks_payment_fk"),
        sa.UniqueConstraint("provider", "event_id", name="payment_webhooks_event_unique"),
        schema="commerce",
    )
    op.create_index("idx_payment_webhooks_event", "payment_webhooks", ["event_type"], schema="commerce")
    op.create_index("idx_payment_webhooks_unprocessed", "payment_webhooks", ["created_at"], schema="commerce", postgresql_where=sa.text("processed = false"))


def downgrade() -> None:
    op.drop_index("idx_payment_webhooks_unprocessed", schema="commerce")
    op.drop_index("idx_payment_webhooks_event", schema="commerce")
    op.drop_table("payment_webhooks", schema="commerce")

    op.execute("DROP TRIGGER IF EXISTS payments_set_updated_at ON commerce.payments;")
    op.drop_index("idx_payments_escrow", schema="commerce")
    op.drop_index("idx_payments_provider_order", schema="commerce")
    op.drop_index("idx_payments_status", schema="commerce")
    op.drop_index("idx_payments_reference", schema="commerce")
    op.drop_index("idx_payments_type", schema="commerce")
    op.drop_index("idx_payments_user", schema="commerce")
    op.drop_index("idx_payments_number", schema="commerce")
    op.drop_table("payments", schema="commerce")
