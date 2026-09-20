"""Track actual payouts made to leads."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260919_14"
down_revision: str | None = "20260919_13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "lead_banks",
        sa.Column("lead_reward_paid_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("lead_banks", "lead_reward_paid_at")
