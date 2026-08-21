"""Add two-stage lead workflow and client bank selection."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260821_08"
down_revision: str | None = "20260821_07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STAGES = (
    "awaiting_admin",
    "admin_processing",
    "awaiting_client_selection",
    "awaiting_manager",
    "manager_processing",
    "not_eligible",
)


def upgrade() -> None:
    op.add_column("leads", sa.Column("email", sa.String(length=254), nullable=True))
    op.add_column(
        "leads",
        sa.Column("primary_admin_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "leads",
        sa.Column(
            "workflow_stage",
            sa.String(length=32),
            server_default="awaiting_admin",
            nullable=False,
        ),
    )
    op.add_column(
        "leads", sa.Column("banks_published_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "leads",
        sa.Column("bank_selection_submitted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "leads_primary_admin_id_fkey", "leads", "users", ["primary_admin_id"], ["id"]
    )
    op.create_check_constraint(
        "leadworkflowstage_values",
        "leads",
        f"workflow_stage IN ({', '.join(repr(stage) for stage in STAGES)})",
    )
    op.add_column(
        "lead_banks",
        sa.Column("offered_to_lead", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "lead_banks", sa.Column("selected_by_lead", sa.Boolean(), nullable=True)
    )

    op.execute(
        """
        UPDATE leads
        SET workflow_stage = CASE
            WHEN internal_status = 'not_eligible' THEN 'not_eligible'
            WHEN manager_id IS NOT NULL THEN 'manager_processing'
            WHEN EXISTS (SELECT 1 FROM lead_banks lb WHERE lb.lead_id = leads.id)
                THEN 'awaiting_client_selection'
            ELSE 'awaiting_admin'
        END,
        banks_published_at = CASE
            WHEN EXISTS (SELECT 1 FROM lead_banks lb WHERE lb.lead_id = leads.id)
                THEN now()
            ELSE NULL
        END
        """
    )
    op.execute("UPDATE lead_banks SET offered_to_lead = true")


def downgrade() -> None:
    op.drop_column("lead_banks", "selected_by_lead")
    op.drop_column("lead_banks", "offered_to_lead")
    op.drop_constraint("leadworkflowstage_values", "leads", type_="check")
    op.drop_constraint("leads_primary_admin_id_fkey", "leads", type_="foreignkey")
    op.drop_column("leads", "bank_selection_submitted_at")
    op.drop_column("leads", "banks_published_at")
    op.drop_column("leads", "workflow_stage")
    op.drop_column("leads", "primary_admin_id")
    op.drop_column("leads", "email")
