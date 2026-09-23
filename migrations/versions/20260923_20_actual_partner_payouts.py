"""Wait for actual lead payment and keep negative team profit."""

from collections.abc import Sequence

from alembic import op

revision: str = "20260923_20"
down_revision: str | None = "20260923_19"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "ck_lead_bank_financial_snapshots_nonnegative", "lead_banks", type_="check"
    )
    op.create_check_constraint(
        "ck_lead_bank_financial_snapshots_nonnegative",
        "lead_banks",
        "(lead_reward_estimate IS NULL OR lead_reward_estimate >= 0) AND "
        "(lead_reward_fact IS NULL OR lead_reward_fact >= 0)",
    )
    op.execute(
        """
        UPDATE lead_banks lb
        SET partner_percent_snapshot = 20,
            partner_reward_estimate = CASE WHEN lb.bank_income_estimate IS NULL THEN NULL
                ELSE ROUND(
                    GREATEST(lb.bank_income_estimate - COALESCE(lb.lead_reward_estimate, 0), 0)
                    * 0.20, 2
                ) END,
            team_profit_estimate = CASE WHEN lb.bank_income_estimate IS NULL THEN NULL
                ELSE ROUND(
                    lb.bank_income_estimate - COALESCE(lb.lead_reward_estimate, 0)
                    - GREATEST(
                        lb.bank_income_estimate - COALESCE(lb.lead_reward_estimate, 0), 0
                    ) * 0.20, 2
                ) END,
            partner_reward_fact = CASE
                WHEN lb.bank_income_fact IS NULL OR lb.lead_reward_paid_at IS NULL THEN NULL
                ELSE ROUND(GREATEST(lb.bank_income_fact - lb.lead_reward_fact, 0) * 0.20, 2)
                END,
            team_profit_fact = CASE
                WHEN lb.bank_income_fact IS NULL OR lb.lead_reward_paid_at IS NULL THEN NULL
                ELSE ROUND(
                    lb.bank_income_fact - lb.lead_reward_fact
                    - GREATEST(lb.bank_income_fact - lb.lead_reward_fact, 0) * 0.20, 2
                ) END
        FROM leads l
        WHERE l.id = lb.lead_id
          AND l.partner_id IS NOT NULL
          AND NOT EXISTS (
              SELECT 1 FROM payments p
              WHERE p.lead_bank_id = lb.id AND p.status IN ('confirmed', 'in_registry', 'paid')
          )
        """
    )
    op.execute(
        """
        UPDATE payments p
        SET partner_reward_fact = lb.partner_reward_fact
        FROM lead_banks lb
        JOIN leads l ON l.id = lb.lead_id
        WHERE p.lead_bank_id = lb.id
          AND l.partner_id IS NOT NULL
          AND p.status NOT IN ('confirmed', 'in_registry', 'paid')
        """
    )


def downgrade() -> None:
    raise RuntimeError("Исторические финансовые значения невозможно восстановить автоматически")
