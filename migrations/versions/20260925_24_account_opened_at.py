"""Record account opening separately from activation."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260925_24"
down_revision: str | None = "20260923_23"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("lead_banks", sa.Column("account_opened_at", sa.DateTime(timezone=True)))
    op.execute("UPDATE lead_banks SET account_opened_at = opened_at WHERE opened_at IS NOT NULL")
    op.execute(
        "UPDATE lead_banks SET selected_by_lead = true "
        "WHERE internal_status = 'client_refused' AND selected_by_lead = false"
    )


def downgrade() -> None:
    op.drop_column("lead_banks", "account_opened_at")
