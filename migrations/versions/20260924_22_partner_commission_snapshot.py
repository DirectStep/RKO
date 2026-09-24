"""Preserve the partner commission agreed when a lead is created."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260924_22"
down_revision: str | None = "20260923_21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("leads", sa.Column("partner_percent_snapshot", sa.Numeric(5, 2)))
    op.add_column("leads", sa.Column("original_partner_id", sa.UUID()))
    op.add_column("leads", sa.Column("original_partner_percent_snapshot", sa.Numeric(5, 2)))
    op.create_foreign_key(
        "fk_lead_original_partner", "leads", "partners", ["original_partner_id"], ["id"]
    )
    op.create_check_constraint(
        "ck_lead_partner_percent_snapshot",
        "leads",
        "partner_percent_snapshot IS NULL OR "
        "(partner_percent_snapshot >= 0 AND partner_percent_snapshot <= 100)",
    )
    op.create_check_constraint(
        "ck_lead_original_partner_percent_snapshot",
        "leads",
        "original_partner_percent_snapshot IS NULL OR "
        "(original_partner_percent_snapshot >= 0 "
        "AND original_partner_percent_snapshot <= 100)",
    )
    op.execute(
        "UPDATE leads SET partner_percent_snapshot = 20 "
        "WHERE partner_id IS NOT NULL OR proposed_partner_id IS NOT NULL"
    )
    op.execute(
        "UPDATE leads SET original_partner_id = COALESCE(partner_id, proposed_partner_id), "
        "original_partner_percent_snapshot = partner_percent_snapshot "
        "WHERE partner_percent_snapshot IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_constraint("ck_lead_original_partner_percent_snapshot", "leads", type_="check")
    op.drop_constraint("ck_lead_partner_percent_snapshot", "leads", type_="check")
    op.drop_constraint("fk_lead_original_partner", "leads", type_="foreignkey")
    op.drop_column("leads", "original_partner_percent_snapshot")
    op.drop_column("leads", "original_partner_id")
    op.drop_column("leads", "partner_percent_snapshot")
