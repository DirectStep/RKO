"""Add client payout text to bank activation conditions."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260821_09"
down_revision: str | None = "20260821_08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bank_activation_conditions",
        sa.Column(
            "payout_text",
            sa.Text(),
            server_default="Уточняется",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("bank_activation_conditions", "payout_text")
