"""Reprice unpaid partner rewards using 20% of income after lead payout."""

from collections.abc import Sequence

from alembic import op

revision: str = "20260923_19"
down_revision: str | None = "20260921_18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE partners SET commission_percent = 20")
    op.execute(
        """
        WITH repricable AS (
            SELECT lb.id, lb.bank_income_estimate, lb.bank_income_fact,
                   lb.lead_reward_estimate,
                   CASE WHEN lb.lead_reward_paid_at IS NOT NULL
                        THEN lb.lead_reward_fact ELSE lb.lead_reward_estimate END AS lead_cost
            FROM lead_banks lb
            JOIN leads l ON l.id = lb.lead_id
            LEFT JOIN payments p ON p.lead_bank_id = lb.id
            WHERE l.partner_id IS NOT NULL
              AND (p.id IS NULL OR p.status NOT IN ('confirmed', 'in_registry', 'paid'))
              AND (lb.bank_income_estimate IS NULL
                   OR lb.bank_income_estimate >= COALESCE(lb.lead_reward_estimate, 0))
              AND (lb.bank_income_fact IS NULL
                   OR lb.bank_income_fact >= COALESCE(
                       CASE WHEN lb.lead_reward_paid_at IS NOT NULL
                            THEN lb.lead_reward_fact ELSE lb.lead_reward_estimate END, 0))
        )
        UPDATE lead_banks lb
        SET partner_percent_snapshot = 20,
            partner_reward_estimate = CASE WHEN r.bank_income_estimate IS NULL THEN NULL
                ELSE ROUND(
                    (r.bank_income_estimate - COALESCE(r.lead_reward_estimate, 0)) * 0.20, 2
                ) END,
            team_profit_estimate = CASE WHEN r.bank_income_estimate IS NULL THEN NULL
                ELSE ROUND(
                    (r.bank_income_estimate - COALESCE(r.lead_reward_estimate, 0)) * 0.80, 2
                ) END,
            partner_reward_fact = CASE WHEN r.bank_income_fact IS NULL THEN NULL
                ELSE ROUND((r.bank_income_fact - COALESCE(r.lead_cost, 0)) * 0.20, 2) END,
            team_profit_fact = CASE WHEN r.bank_income_fact IS NULL THEN NULL
                ELSE ROUND((r.bank_income_fact - COALESCE(r.lead_cost, 0)) * 0.80, 2) END
        FROM repricable r
        WHERE lb.id = r.id
        """
    )
    op.execute(
        """
        UPDATE payments p
        SET partner_reward_fact = lb.partner_reward_fact
        FROM lead_banks lb
        WHERE p.lead_bank_id = lb.id
          AND p.status NOT IN ('confirmed', 'in_registry', 'paid')
          AND lb.partner_percent_snapshot = 20
          AND EXISTS (SELECT 1 FROM leads l WHERE l.id = lb.lead_id AND l.partner_id IS NOT NULL)
        """
    )


def downgrade() -> None:
    raise RuntimeError("Исторические финансовые значения невозможно восстановить автоматически")
