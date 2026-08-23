"""Add synchronized bank rates and financial snapshots."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260823_12"
down_revision: str | None = "20260822_11"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "bank_rates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("offer_code", sa.String(length=64), nullable=False),
        sa.Column("bank_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "online_text", sa.String(length=120), server_default="Уточняется", nullable=False
        ),
        sa.Column("base_payout", sa.Numeric(14, 2), nullable=False),
        sa.Column("lead_payout", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "lead_payout_paid_separately", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("source_row", sa.Integer(), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "base_payout >= 0 AND lead_payout >= 0", name="ck_bank_rate_nonnegative_money"
        ),
        sa.ForeignKeyConstraint(["bank_id"], ["banks.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bank_id"),
        sa.UniqueConstraint("offer_code"),
    )
    op.add_column(
        "lead_banks", sa.Column("bank_rate_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column("lead_banks", sa.Column("lead_reward_estimate", sa.Numeric(14, 2)))
    op.add_column("lead_banks", sa.Column("lead_reward_fact", sa.Numeric(14, 2)))
    op.add_column("lead_banks", sa.Column("team_profit_estimate", sa.Numeric(14, 2)))
    op.add_column("lead_banks", sa.Column("team_profit_fact", sa.Numeric(14, 2)))
    op.add_column(
        "lead_banks",
        sa.Column(
            "lead_reward_paid_separately", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
    )
    op.create_foreign_key(
        "lead_banks_bank_rate_id_fkey",
        "lead_banks",
        "bank_rates",
        ["bank_rate_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_lead_bank_financial_snapshots_nonnegative",
        "lead_banks",
        "(lead_reward_estimate IS NULL OR lead_reward_estimate >= 0) AND "
        "(lead_reward_fact IS NULL OR lead_reward_fact >= 0) AND "
        "(team_profit_estimate IS NULL OR team_profit_estimate >= 0) AND "
        "(team_profit_fact IS NULL OR team_profit_fact >= 0)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_lead_bank_financial_snapshots_nonnegative", "lead_banks", type_="check")
    op.drop_constraint("lead_banks_bank_rate_id_fkey", "lead_banks", type_="foreignkey")
    op.drop_column("lead_banks", "lead_reward_paid_separately")
    op.drop_column("lead_banks", "team_profit_fact")
    op.drop_column("lead_banks", "team_profit_estimate")
    op.drop_column("lead_banks", "lead_reward_fact")
    op.drop_column("lead_banks", "lead_reward_estimate")
    op.drop_column("lead_banks", "bank_rate_id")
    op.drop_table("bank_rates")
