from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM identity.refresh_tokens rt
        WHERE NOT EXISTS (
            SELECT 1 FROM identity.users u WHERE u.id = rt.user_id
        )
        """
    )

    op.create_foreign_key(
        constraint_name="fk_refresh_tokens_user_id_users_id",
        source_table="refresh_tokens",
        source_schema="identity",
        referent_table="users",
        referent_schema="identity",
        local_cols=["user_id"],
        remote_cols=["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    """Drop the FK, returning to the bare-PGUUID state."""
    op.drop_constraint(
        constraint_name="fk_refresh_tokens_user_id_users_id",
        table_name="refresh_tokens",
        schema="identity",
        type_="foreignkey",
    )
