"""Create RKO core tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260817_02"
down_revision: str | None = "20260817_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("telegram_username", sa.String(length=64)))
    op.create_check_constraint(
        "userrole_values", "users", "role IN ('lead', 'partner', 'manager', 'admin')"
    )
    op.create_check_constraint(
        "accessstatus_values", "users", "access_status IN ('active', 'blocked')"
    )
    op.create_table(
        "banks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "partners",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("partner_type", sa.String(length=32), nullable=False),
        sa.Column("commission_percent", sa.Numeric(5, 2), nullable=False),
        sa.Column("telegram_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("assigned_manager_id", postgresql.UUID(as_uuid=True)),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "commission_percent >= 0 AND commission_percent <= 100",
            name="ck_partner_commission_percent",
        ),
        sa.ForeignKeyConstraint(["assigned_manager_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["telegram_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
        sa.UniqueConstraint("telegram_user_id"),
    )
    op.create_table(
        "channels",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("channel_type", sa.String(length=32), nullable=False),
        sa.Column("referral_code", sa.String(length=64), nullable=False),
        sa.Column("referral_link", sa.String(length=255), nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "partner_id", name="uq_channel_partner"),
        sa.UniqueConstraint("referral_code"),
        sa.UniqueConstraint("referral_link"),
    )
    op.create_table(
        "leads",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("module_code", sa.String(length=16), server_default="rko", nullable=False),
        sa.Column("short_id", sa.String(length=24), nullable=False),
        sa.Column("telegram_id", sa.String(length=20), nullable=False),
        sa.Column("telegram_username", sa.String(length=64)),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("phone", sa.String(length=24), nullable=False),
        sa.Column("consent_status", sa.Boolean(), nullable=False),
        sa.Column("consent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_referral_code", sa.String(length=64)),
        sa.Column("proposed_partner_id", postgresql.UUID(as_uuid=True)),
        sa.Column("proposed_channel_id", postgresql.UUID(as_uuid=True)),
        sa.Column("partner_id", postgresql.UUID(as_uuid=True)),
        sa.Column("channel_id", postgresql.UUID(as_uuid=True)),
        sa.Column("assignment_status", sa.String(length=32), nullable=False),
        sa.Column("assignment_confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("manager_id", postgresql.UUID(as_uuid=True)),
        sa.Column("internal_status", sa.String(length=32), nullable=False),
        sa.Column("external_status", sa.String(length=32), nullable=False),
        sa.Column("payment_status", sa.String(length=32), nullable=False),
        sa.Column("internal_comment", sa.Text()),
        sa.Column("first_click_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("application_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "last_updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "assignment_status IN ('unresolved', 'pending', 'confirmed', 'direct')",
            name="assignmentstatus_values",
        ),
        sa.CheckConstraint(
            "internal_status IN ('new', 'manager_assigned', 'awaiting_first_contact', "
            "'contacted', 'awaiting_data', 'data_received', 'selecting_banks', "
            "'preparing_applications', 'applications_sent', 'opening_accounts', "
            "'partially_opened', 'all_planned_opened', 'paused', 'no_response', "
            "'lead_refused', 'not_eligible', 'completed')",
            name="leadinternalstatus_values",
        ),
        sa.CheckConstraint(
            "external_status IN ('new', 'in_progress', 'opening_accounts', "
            "'partially_completed', 'completed', 'paused', 'closed_without_result')",
            name="leadexternalstatus_values",
        ),
        sa.CheckConstraint(
            "payment_status IN ('not_calculated', 'calculated', 'awaiting_confirmation', "
            "'confirmed', 'in_registry', 'paid', 'cancelled')",
            name="paymentstatus_values",
        ),
        sa.CheckConstraint(
            "assignment_status != 'confirmed' OR (partner_id IS NOT NULL AND "
            "channel_id IS NOT NULL AND assignment_confirmed_at IS NOT NULL)",
            name="ck_lead_confirmed_assignment",
        ),
        sa.CheckConstraint(
            "assignment_status != 'direct' OR (partner_id IS NULL AND channel_id IS NULL)",
            name="ck_lead_direct_without_source",
        ),
        sa.CheckConstraint(
            "(proposed_partner_id IS NULL AND proposed_channel_id IS NULL) OR "
            "(proposed_partner_id IS NOT NULL AND proposed_channel_id IS NOT NULL)",
            name="ck_lead_proposed_source_pair",
        ),
        sa.CheckConstraint(
            "assignment_confirmed_at IS NULL OR assignment_status = 'confirmed'",
            name="ck_lead_confirmation_date_status",
        ),
        sa.ForeignKeyConstraint(
            ["channel_id", "partner_id"],
            ["channels.id", "channels.partner_id"],
            name="fk_lead_channel_partner",
        ),
        sa.ForeignKeyConstraint(["manager_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["partner_id"], ["partners.id"]),
        sa.ForeignKeyConstraint(
            ["proposed_channel_id", "proposed_partner_id"],
            ["channels.id", "channels.partner_id"],
            name="fk_lead_proposed_channel_partner",
        ),
        sa.ForeignKeyConstraint(["proposed_partner_id"], ["partners.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("short_id"),
        sa.UniqueConstraint("telegram_id"),
    )
    op.create_index("ix_leads_phone", "leads", ["phone"])
    op.create_table(
        "lead_banks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lead_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("bank_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("internal_status", sa.String(length=32), nullable=False),
        sa.Column("external_status", sa.String(length=32), nullable=False),
        sa.Column("planned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_requested_at", sa.DateTime(timezone=True)),
        sa.Column("preparation_started_at", sa.DateTime(timezone=True)),
        sa.Column("application_sent_at", sa.DateTime(timezone=True)),
        sa.Column("review_started_at", sa.DateTime(timezone=True)),
        sa.Column("revision_requested_at", sa.DateTime(timezone=True)),
        sa.Column("opened_at", sa.DateTime(timezone=True)),
        sa.Column("closed_without_open_at", sa.DateTime(timezone=True)),
        sa.Column("close_reason", sa.Text()),
        sa.Column("bank_income_estimate", sa.Numeric(14, 2)),
        sa.Column("bank_income_fact", sa.Numeric(14, 2)),
        sa.Column("partner_percent_snapshot", sa.Numeric(5, 2)),
        sa.Column("partner_reward_estimate", sa.Numeric(14, 2)),
        sa.Column("partner_reward_fact", sa.Numeric(14, 2)),
        sa.Column(
            "last_updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "partner_percent_snapshot IS NULL OR "
            "(partner_percent_snapshot >= 0 AND partner_percent_snapshot <= 100)",
            name="ck_lead_bank_partner_percent",
        ),
        sa.CheckConstraint(
            "(bank_income_estimate IS NULL OR bank_income_estimate >= 0) AND "
            "(bank_income_fact IS NULL OR bank_income_fact >= 0) AND "
            "(partner_reward_estimate IS NULL OR partner_reward_estimate >= 0) AND "
            "(partner_reward_fact IS NULL OR partner_reward_fact >= 0)",
            name="ck_lead_bank_nonnegative_money",
        ),
        sa.CheckConstraint(
            "internal_status IN ('planned', 'awaiting_data', 'preparing_application', "
            "'application_sent', 'under_review', 'revision_required', 'account_opened', "
            "'bank_rejected', 'client_refused', 'excluded')",
            name="bankinternalstatus_values",
        ),
        sa.CheckConstraint(
            "external_status IN ('planned', 'in_progress', 'opened', 'not_opened', "
            "'will_not_open')",
            name="bankexternalstatus_values",
        ),
        sa.ForeignKeyConstraint(["bank_id"], ["banks.id"]),
        sa.ForeignKeyConstraint(["lead_id"], ["leads.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lead_id", "bank_id", name="uq_lead_bank"),
    )
    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lead_bank_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("partner_reward_fact", sa.Numeric(14, 2)),
        sa.Column("payment_period", sa.String(length=20)),
        sa.Column("expected_payment_at", sa.Date()),
        sa.Column("registry_number", sa.String(length=80)),
        sa.Column("paid_at", sa.Date()),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("confirmed_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("internal_comment", sa.Text()),
        sa.CheckConstraint(
            "partner_reward_fact IS NULL OR partner_reward_fact >= 0",
            name="ck_payment_nonnegative_reward",
        ),
        sa.CheckConstraint(
            "status IN ('not_calculated', 'calculated', 'awaiting_confirmation', "
            "'confirmed', 'in_registry', 'paid', 'cancelled')",
            name="paymentstatus_values",
        ),
        sa.CheckConstraint(
            "status NOT IN ('confirmed', 'in_registry', 'paid') OR "
            "(partner_reward_fact IS NOT NULL AND confirmed_at IS NOT NULL "
            "AND confirmed_by_user_id IS NOT NULL)",
            name="ck_payment_confirmation_fields",
        ),
        sa.CheckConstraint("status != 'paid' OR paid_at IS NOT NULL", name="ck_payment_paid_date"),
        sa.CheckConstraint(
            "status != 'cancelled' OR "
            "(internal_comment IS NOT NULL AND length(trim(internal_comment)) > 0)",
            name="ck_payment_cancel_comment",
        ),
        sa.ForeignKeyConstraint(["confirmed_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["lead_bank_id"], ["lead_banks.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lead_bank_id"),
    )


def downgrade() -> None:
    op.drop_table("payments")
    op.drop_table("lead_banks")
    op.drop_index("ix_leads_phone", table_name="leads")
    op.drop_table("leads")
    op.drop_table("channels")
    op.drop_table("partners")
    op.drop_table("banks")
    op.drop_constraint("accessstatus_values", "users", type_="check")
    op.drop_constraint("userrole_values", "users", type_="check")
    op.drop_column("users", "telegram_username")
