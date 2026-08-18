"""Add one-time partner activation tokens."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260818_06"
down_revision: str | None = "20260818_05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("partners", sa.Column("activation_token_hash", sa.String(length=64)))
    op.add_column("partners", sa.Column("activation_created_at", sa.DateTime(timezone=True)))
    op.create_unique_constraint(
        "uq_partners_activation_token_hash", "partners", ["activation_token_hash"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_partners_activation_token_hash", "partners", type_="unique")
    op.drop_column("partners", "activation_created_at")
    op.drop_column("partners", "activation_token_hash")
