"""Recalculate unfinished bank-paid lead bonuses without treating them as team costs."""

from collections.abc import Sequence
from decimal import Decimal

from alembic import op
from sqlalchemy import text

revision: str = "20260924_23"
down_revision: str | None = "20260924_22"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _partner_share(income: Decimal | None, percent: Decimal | None) -> Decimal | None:
    if income is None or percent is None:
        return None
    return (income * percent / Decimal("100")).quantize(Decimal("0.01"))


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        text(
            """
            SELECT lb.id, lb.bank_income_estimate, lb.bank_income_fact,
                   lb.partner_percent_snapshot
            FROM lead_banks lb
            WHERE lb.lead_reward_paid_separately = TRUE
              AND NOT EXISTS (
                  SELECT 1 FROM payments p
                  WHERE p.lead_bank_id = lb.id
                    AND p.status IN ('confirmed', 'in_registry', 'paid')
              )
            """
        )
    ).mappings()
    updates = []
    for row in rows:
        estimate = _partner_share(row["bank_income_estimate"], row["partner_percent_snapshot"])
        actual = _partner_share(row["bank_income_fact"], row["partner_percent_snapshot"])
        updates.append(
            {
                "id": row["id"],
                "partner_estimate": estimate,
                "team_estimate": (
                    row["bank_income_estimate"] - (estimate or Decimal("0"))
                    if row["bank_income_estimate"] is not None
                    else None
                ),
                "partner_fact": actual,
                "team_fact": (
                    row["bank_income_fact"] - (actual or Decimal("0"))
                    if row["bank_income_fact"] is not None
                    else None
                ),
            }
        )
    if not updates:
        return
    connection.execute(
        text(
            """
            UPDATE lead_banks
            SET partner_reward_estimate = :partner_estimate,
                team_profit_estimate = :team_estimate,
                partner_reward_fact = :partner_fact,
                team_profit_fact = :team_fact
            WHERE id = :id
            """
        ),
        updates,
    )
    connection.execute(
        text(
            """
            UPDATE payments
            SET partner_reward_fact = :partner_fact
            WHERE lead_bank_id = :id
              AND status NOT IN ('confirmed', 'in_registry', 'paid')
            """
        ),
        updates,
    )


def downgrade() -> None:
    raise RuntimeError("Пересчитанные финансовые значения нельзя восстановить автоматически")
