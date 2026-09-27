"""Freeze activation conditions for bank accounts opened before this revision."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260927_28"
down_revision: str | None = "20260927_27"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("lead_banks", sa.Column("activation_condition_snapshot", sa.Text()))
    op.execute(
        """
        UPDATE lead_banks AS lb
        SET activation_condition_snapshot = COALESCE(
            (
                SELECT c.action_text
                FROM banks AS b
                JOIN bank_activation_conditions AS c
                    ON c.normalized_bank_name = regexp_replace(
                        replace(lower(trim(b.name)), 'ё', 'е'), '\\s+', ' ', 'g'
                    )
                WHERE b.id = lb.bank_id AND c.active = true
                LIMIT 1
            ),
            ''
        )
        WHERE lb.account_opened_at IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_column("lead_banks", "activation_condition_snapshot")
