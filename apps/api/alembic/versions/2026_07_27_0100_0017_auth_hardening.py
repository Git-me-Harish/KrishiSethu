"""Auth hardening: google_sub identity binding + wider aadhaar_hash

Two schema changes on identity.users:

- google_sub (VARCHAR(64), NULL, UNIQUE): Google's immutable subject id.
  Google OAuth login previously matched accounts by email alone, so an
  attacker could pre-register an account on a victim's email address and be
  handed that account the moment the victim signed in with Google. Matching
  on google_sub first closes that; email is only an acceptable fallback when
  the existing record's email is verified.

- aadhaar_hash widened 64 -> 128 chars: the hash is now version-prefixed
  ("v2$<64 hex>") so the peppered-PBKDF2 scheme can be told apart from the
  legacy bare SHA-256 digests. Existing values are left untouched — they
  cannot be recomputed without the raw Aadhaar numbers, which are never
  stored. See core/security.py:hash_aadhaar for the backfill TODO.

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-27
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- Federated identity: Google subject id ---
    op.add_column(
        "users",
        sa.Column(
            "google_sub",
            sa.String(64),
            nullable=True,
            comment=(
                "Google's immutable subject identifier. Matched BEFORE email "
                "on OAuth login — email alone is user-settable and was "
                "hijackable."
            ),
        ),
        schema="identity",
    )
    op.create_unique_constraint(
        "users_google_sub_key", "users", ["google_sub"], schema="identity"
    )
    op.create_index(
        "idx_users_google_sub",
        "users",
        ["google_sub"],
        schema="identity",
        postgresql_where=sa.text("google_sub IS NOT NULL"),
    )

    # --- Versioned Aadhaar hash ---
    op.alter_column(
        "users",
        "aadhaar_hash",
        type_=sa.String(128),
        existing_type=sa.String(64),
        existing_nullable=True,
        schema="identity",
        comment=(
            "Peppered PBKDF2 hash of the Aadhaar number, prefixed with its "
            "scheme version ('v2$...'). Legacy rows hold a bare SHA-256 digest."
        ),
        existing_comment="SHA-256 hash of Aadhaar number, salted with app secret",
    )


def downgrade() -> None:
    # Narrowing back to 64 chars would truncate any v2$-prefixed hash, so
    # clear those rows first rather than corrupt them into false duplicates.
    op.execute(
        "UPDATE identity.users SET aadhaar_hash = NULL, aadhaar_verified = false "
        "WHERE aadhaar_hash LIKE 'v2$%';"
    )
    op.alter_column(
        "users",
        "aadhaar_hash",
        type_=sa.String(64),
        existing_type=sa.String(128),
        existing_nullable=True,
        schema="identity",
        comment="SHA-256 hash of Aadhaar number, salted with app secret",
    )

    op.drop_index("idx_users_google_sub", table_name="users", schema="identity")
    op.drop_constraint("users_google_sub_key", "users", schema="identity", type_="unique")
    op.drop_column("users", "google_sub", schema="identity")
