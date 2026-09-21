"""Assign anutka_rko as the default support manager for all leads."""

from collections.abc import Sequence

from alembic import op

revision: str = "20260920_15"
down_revision: str | None = "20260919_14"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE
            manager_count integer;
        BEGIN
            SELECT count(*)
            INTO manager_count
            FROM users
            WHERE lower(telegram_username) = 'anutka_rko';

            IF manager_count > 1 THEN
                RAISE EXCEPTION 'Found multiple users with username anutka_rko';
            END IF;

            IF manager_count = 0 THEN
                INSERT INTO users (id, telegram_username, role, access_status)
                VALUES (gen_random_uuid(), 'anutka_rko', 'manager', 'active');
            ELSE
                UPDATE users
                SET role = 'manager',
                    access_status = 'active',
                    updated_at = now()
                WHERE lower(telegram_username) = 'anutka_rko';
            END IF;
        END
        $$;
        """
    )
    op.execute(
        """
        UPDATE leads AS lead
        SET manager_id = manager.id,
            workflow_stage = CASE
                WHEN lead.workflow_stage = 'awaiting_manager' THEN 'manager_processing'
                ELSE lead.workflow_stage
            END,
            internal_status = CASE
                WHEN lead.workflow_stage = 'awaiting_manager' THEN 'preparing_applications'
                ELSE lead.internal_status
            END,
            external_status = CASE
                WHEN lead.workflow_stage = 'awaiting_manager' THEN 'opening_accounts'
                ELSE lead.external_status
            END,
            last_updated_at = now()
        FROM users AS manager
        WHERE lower(manager.telegram_username) = 'anutka_rko'
          AND manager.role = 'manager'
          AND manager.access_status = 'active'
        """
    )


def downgrade() -> None:
    # Existing manager assignments cannot be distinguished safely from manual ones.
    pass
