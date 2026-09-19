"""Assign existing partner leads to their partner administrator."""

from collections.abc import Sequence

from alembic import op

revision: str = "20260919_13"
down_revision: str | None = "20260823_12"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE leads AS lead
        SET primary_admin_id = partner.assigned_manager_id,
            workflow_stage = CASE
                WHEN lead.workflow_stage = 'awaiting_admin' THEN 'admin_processing'
                ELSE lead.workflow_stage
            END,
            internal_status = CASE
                WHEN lead.workflow_stage = 'awaiting_admin'
                    AND lead.internal_status = 'new'
                    THEN 'awaiting_first_contact'
                ELSE lead.internal_status
            END,
            external_status = CASE
                WHEN lead.workflow_stage = 'awaiting_admin'
                    AND lead.external_status = 'new'
                    THEN 'in_progress'
                ELSE lead.external_status
            END,
            last_updated_at = now()
        FROM partners AS partner
        WHERE lead.partner_id = partner.id
          AND lead.primary_admin_id IS NULL
          AND lead.archived_at IS NULL
          AND partner.assigned_manager_id IS NOT NULL
          AND lead.workflow_stage != 'not_eligible'
        """
    )


def downgrade() -> None:
    # The previous responsible administrator cannot be reconstructed safely.
    pass
