"""Allow staff invitations before Telegram ID is known."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260818_05"
down_revision: str | None = "20260818_04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("users", "telegram_id", existing_type=sa.String(length=20), nullable=True)


def downgrade() -> None:
    op.alter_column("users", "telegram_id", existing_type=sa.String(length=20), nullable=False)
