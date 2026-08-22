"""Add repeat applications and archive previous lead cards."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260822_11"
down_revision: str | None = "20260822_10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("leads_telegram_id_key", "leads", type_="unique")
    op.create_index("ix_leads_telegram_id", "leads", ["telegram_id"])
    op.add_column(
        "leads",
        sa.Column("is_repeat", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "leads",
        sa.Column("previous_lead_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("leads", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "leads_previous_lead_id_fkey",
        "leads",
        "leads",
        ["previous_lead_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("leads_previous_lead_id_fkey", "leads", type_="foreignkey")
    op.drop_column("leads", "archived_at")
    op.drop_column("leads", "previous_lead_id")
    op.drop_column("leads", "is_repeat")
    op.drop_index("ix_leads_telegram_id", table_name="leads")
    op.create_unique_constraint("leads_telegram_id_key", "leads", ["telegram_id"])
