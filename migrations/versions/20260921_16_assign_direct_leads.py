"""Assign xirasS as the primary admin for direct leads."""

from collections.abc import Sequence

from alembic import op

revision: str = "20260921_16"
down_revision: str | None = "20260920_15"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE
            admin_count integer;
        BEGIN
            SELECT count(*)
            INTO admin_count
            FROM users
            WHERE lower(telegram_username) = 'xirass';

            IF admin_count > 1 THEN
                RAISE EXCEPTION 'Found multiple users with username xirasS';
            END IF;

            IF admin_count = 0 THEN
                INSERT INTO users (id, telegram_username, role, access_status)
                VALUES (gen_random_uuid(), 'xirasS', 'admin', 'active');
            ELSE
                UPDATE users
                SET role = 'admin',
                    access_status = 'active',
                    updated_at = now()
                WHERE lower(telegram_username) = 'xirass';
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        UPDATE leads AS lead
        SET primary_admin_id = admin.id,
            last_updated_at = now()
        FROM users AS admin
        WHERE lower(admin.telegram_username) = 'xirass'
          AND admin.role = 'admin'
          AND admin.access_status = 'active'
          AND lead.assignment_status = 'direct'
        """
    )


def downgrade() -> None:
    # Existing primary-admin assignments cannot be distinguished safely from manual ones.
    pass
