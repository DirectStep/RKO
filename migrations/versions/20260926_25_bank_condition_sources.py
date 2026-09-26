"""Preserve source worksheet categories for lead bank ordering."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260926_25"
down_revision: str | None = "20260925_24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bank_activation_conditions",
        sa.Column("source_sheets", JSONB(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("bank_activation_conditions", "source_sheets")
