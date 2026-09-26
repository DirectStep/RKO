"""Add manager-collected lead contact fields."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260926_26"
down_revision: str | None = "20260926_25"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("street_address", sa.String(length=300)))
    op.add_column("leads", sa.Column("inn_draft", sa.String(length=120)))
    op.add_column(
        "lead_banks",
        sa.Column("decision_history", JSONB(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "payments", sa.Column("partner_notification_sent_at", sa.DateTime(timezone=True))
    )
    op.execute(
        "UPDATE payments SET partner_notification_sent_at = confirmed_at "
        "WHERE status = 'paid' AND confirmed_at IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("payments", "partner_notification_sent_at")
    op.drop_column("lead_banks", "decision_history")
    op.drop_column("leads", "inn_draft")
    op.drop_column("leads", "street_address")
