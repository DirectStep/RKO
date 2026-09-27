"""Record separate partner offer acceptance and personal-data consent."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260927_27"
down_revision: str | None = "20260926_26"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("partners", sa.Column("offer_accepted_at", sa.DateTime(timezone=True)))
    op.add_column("partners", sa.Column("offer_accepted_version", sa.String(length=20)))
    op.add_column("partners", sa.Column("pdn_consented_at", sa.DateTime(timezone=True)))
    op.add_column("partners", sa.Column("pdn_consent_version", sa.String(length=20)))


def downgrade() -> None:
    op.drop_column("partners", "pdn_consent_version")
    op.drop_column("partners", "pdn_consented_at")
    op.drop_column("partners", "offer_accepted_version")
    op.drop_column("partners", "offer_accepted_at")
