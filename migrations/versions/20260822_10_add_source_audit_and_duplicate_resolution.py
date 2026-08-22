"""Add source audit and duplicate review resolution fields."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260822_10"
down_revision: str | None = "20260821_09"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RESOLUTIONS = ("duplicate", "separate_lead", "update_original")


def upgrade() -> None:
    op.add_column(
        "leads",
        sa.Column("source_updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "leads", sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_foreign_key(
        "leads_source_updated_by_user_id_fkey",
        "leads",
        "users",
        ["source_updated_by_user_id"],
        ["id"],
    )
    op.add_column(
        "duplicate_lead_reviews",
        sa.Column("original_lead_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "duplicate_lead_reviews", sa.Column("resolution", sa.String(32), nullable=True)
    )
    op.add_column(
        "duplicate_lead_reviews",
        sa.Column("resolved_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "duplicate_lead_reviews",
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "duplicate_reviews_original_lead_id_fkey",
        "duplicate_lead_reviews",
        "leads",
        ["original_lead_id"],
        ["id"],
    )
    op.create_foreign_key(
        "duplicate_reviews_resolved_by_user_id_fkey",
        "duplicate_lead_reviews",
        "users",
        ["resolved_by_user_id"],
        ["id"],
    )
    op.create_check_constraint(
        "duplicateresolution_values",
        "duplicate_lead_reviews",
        f"resolution IN ({', '.join(repr(value) for value in RESOLUTIONS)})",
    )
    op.execute(
        """
        UPDATE duplicate_lead_reviews AS review
        SET original_lead_id = lead.id
        FROM leads AS lead
        WHERE review.original_lead_id IS NULL AND review.phone = lead.phone
        """
    )


def downgrade() -> None:
    op.drop_constraint(
        "duplicateresolution_values", "duplicate_lead_reviews", type_="check"
    )
    op.drop_constraint(
        "duplicate_reviews_resolved_by_user_id_fkey",
        "duplicate_lead_reviews",
        type_="foreignkey",
    )
    op.drop_constraint(
        "duplicate_reviews_original_lead_id_fkey",
        "duplicate_lead_reviews",
        type_="foreignkey",
    )
    op.drop_column("duplicate_lead_reviews", "resolved_at")
    op.drop_column("duplicate_lead_reviews", "resolved_by_user_id")
    op.drop_column("duplicate_lead_reviews", "resolution")
    op.drop_column("duplicate_lead_reviews", "original_lead_id")
    op.drop_constraint("leads_source_updated_by_user_id_fkey", "leads", type_="foreignkey")
    op.drop_column("leads", "source_updated_at")
    op.drop_column("leads", "source_updated_by_user_id")
