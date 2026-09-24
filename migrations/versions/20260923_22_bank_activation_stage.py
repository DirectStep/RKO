"""Add opened-account stage before bank activation."""

from collections.abc import Sequence

from alembic import op

revision: str = "20260923_23"
down_revision: str | None = "20260924_23"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("bankinternalstatus_values", "lead_banks", type_="check")
    op.create_check_constraint(
        "bankinternalstatus_values",
        "lead_banks",
        "internal_status IN ('planned', 'awaiting_activation', 'awaiting_data', "
        "'preparing_application', 'application_sent', 'under_review', "
        "'revision_required', 'account_opened', 'not_opened', 'cut', 'duplicate', "
        "'bank_rejected', 'client_refused', 'excluded')",
    )


def downgrade() -> None:
    op.drop_constraint("bankinternalstatus_values", "lead_banks", type_="check")
    op.create_check_constraint(
        "bankinternalstatus_values",
        "lead_banks",
        "internal_status IN ('planned', 'awaiting_data', 'preparing_application', "
        "'application_sent', 'under_review', 'revision_required', "
        "'account_opened', 'bank_rejected', 'client_refused', 'excluded')",
    )
