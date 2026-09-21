"""Return untouched auto-started manager leads to the new queue."""

from collections.abc import Sequence

from alembic import op

revision: str = "20260921_17"
down_revision: str | None = "20260921_16"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE leads
        SET workflow_stage = 'awaiting_manager',
            internal_status = 'data_received',
            external_status = 'in_progress'
        WHERE workflow_stage = 'manager_processing'
          AND bank_selection_submitted_at IS NOT NULL
          AND last_updated_at = bank_selection_submitted_at
        """
    )


def downgrade() -> None:
    # Opening history did not exist before this migration, so reversal is unsafe.
    pass
