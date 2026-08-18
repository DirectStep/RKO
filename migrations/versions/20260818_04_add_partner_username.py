"""Add partner Telegram username."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260818_04"
down_revision: str | None = "20260817_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("partners", sa.Column("telegram_username", sa.String(length=64)))


def downgrade() -> None:
    op.drop_column("partners", "telegram_username")
