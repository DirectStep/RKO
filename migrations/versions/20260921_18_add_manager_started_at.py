"""Track whether the current manager has opened the lead."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260921_18"
down_revision: str | None = "20260921_17"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column("manager_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        """
        UPDATE leads
        SET manager_started_at = COALESCE(last_updated_at, bank_selection_submitted_at)
        WHERE manager_id IS NOT NULL
          AND workflow_stage = 'manager_processing'
        """
    )


def downgrade() -> None:
    op.drop_column("leads", "manager_started_at")
