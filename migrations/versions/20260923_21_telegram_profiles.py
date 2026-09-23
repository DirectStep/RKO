"""Remember the freshest observed Telegram username by immutable Telegram ID."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260923_21"
down_revision: str | None = "20260923_20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telegram_profiles",
        sa.Column("telegram_id", sa.String(length=20), primary_key=True),
        sa.Column("username", sa.String(length=64)),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("telegram_profiles")
