"""Add lead questionnaire and short ID sequence."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260817_03"
down_revision: str | None = "20260817_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(sa.schema.CreateSequence(sa.Sequence("lead_short_id_seq")))
    op.create_table(
        "lead_drafts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("telegram_id", sa.String(length=20), nullable=False),
        sa.Column("referral_code", sa.String(length=64)),
        sa.Column("proposed_partner_id", postgresql.UUID(as_uuid=True)),
        sa.Column("proposed_channel_id", postgresql.UUID(as_uuid=True)),
        sa.Column("first_click_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(proposed_partner_id IS NULL AND proposed_channel_id IS NULL) OR "
            "(proposed_partner_id IS NOT NULL AND proposed_channel_id IS NOT NULL)",
            name="ck_draft_proposed_source_pair",
        ),
        sa.ForeignKeyConstraint(
            ["proposed_channel_id", "proposed_partner_id"],
            ["channels.id", "channels.partner_id"],
            name="fk_draft_channel_partner",
        ),
        sa.ForeignKeyConstraint(["proposed_partner_id"], ["partners.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_id"),
    )
    op.create_table(
        "duplicate_lead_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("telegram_id", sa.String(length=20), nullable=False),
        sa.Column("telegram_username", sa.String(length=64)),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("phone", sa.String(length=24), nullable=False),
        sa.Column("referral_code", sa.String(length=64)),
        sa.Column("questionnaire_answers", postgresql.JSONB(), nullable=False),
        sa.Column("consent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_click_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("review_status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_id"),
    )
    op.create_index("ix_duplicate_lead_reviews_phone", "duplicate_lead_reviews", ["phone"])
    op.add_column(
        "leads",
        sa.Column(
            "questionnaire_answers",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.alter_column("leads", "questionnaire_answers", server_default=None)


def downgrade() -> None:
    op.drop_column("leads", "questionnaire_answers")
    op.drop_index("ix_duplicate_lead_reviews_phone", table_name="duplicate_lead_reviews")
    op.drop_table("duplicate_lead_reviews")
    op.drop_table("lead_drafts")
    op.execute(sa.schema.DropSequence(sa.Sequence("lead_short_id_seq")))
