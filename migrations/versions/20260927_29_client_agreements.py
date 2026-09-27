"""Record client offer acceptance separately from personal-data consent."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260927_29"
down_revision: str | None = "20260927_28"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for table in ("leads", "duplicate_lead_reviews"):
        op.add_column(table, sa.Column("offer_accepted_at", sa.DateTime(timezone=True)))
        op.add_column(table, sa.Column("offer_accepted_version", sa.String(length=20)))


def downgrade() -> None:
    for table in ("duplicate_lead_reviews", "leads"):
        op.drop_column(table, "offer_accepted_version")
        op.drop_column(table, "offer_accepted_at")
