from sqlalchemy import func, or_, select

from app.config import Settings
from app.database import Database
from app.domain.enums import AccessStatus, UserRole
from app.models import Partner, User


class UserAccessService:
    def __init__(self, database: Database, settings: Settings) -> None:
        self.database = database
        self.settings = settings

    async def resolve_role(
        self, telegram_id: str, telegram_username: str | None
    ) -> UserRole | None:
        async with self.database.session() as session, session.begin():
            user = await session.scalar(
                select(User).where(User.telegram_id == telegram_id).with_for_update()
            )
            normalized_username = (telegram_username or "").strip().lstrip("@").lower()
            invited_by_username = normalized_username in self.settings.admin_usernames
            if invited_by_username:
                claimed_user = await session.scalar(
                    select(User).where(
                        func.lower(User.telegram_username) == normalized_username,
                        User.role == UserRole.ADMIN,
                    )
                )
                if claimed_user is not None and claimed_user.telegram_id != telegram_id:
                    invited_by_username = False
            if telegram_id in self.settings.admin_ids or invited_by_username:
                if user is None:
                    user = User(
                        telegram_id=telegram_id,
                        telegram_username=telegram_username,
                        role=UserRole.ADMIN,
                        access_status=AccessStatus.ACTIVE,
                    )
                    session.add(user)
                else:
                    user.telegram_username = telegram_username
                    user.role = UserRole.ADMIN
                    user.access_status = AccessStatus.ACTIVE
                return UserRole.ADMIN

            partner = None
            if normalized_username:
                partner = await session.scalar(
                    select(Partner)
                    .where(
                        func.lower(Partner.telegram_username) == normalized_username,
                        Partner.active.is_(True),
                        or_(
                            Partner.telegram_user_id.is_(None),
                            Partner.telegram_user_id == (user.id if user else None),
                        ),
                    )
                    .with_for_update()
                    .limit(1)
                )
            if partner is not None and (
                user is None or user.role in {UserRole.LEAD, UserRole.PARTNER}
            ):
                if user is None:
                    user = User(
                        telegram_id=telegram_id,
                        telegram_username=telegram_username,
                        role=UserRole.PARTNER,
                        access_status=AccessStatus.ACTIVE,
                    )
                    session.add(user)
                    await session.flush()
                else:
                    user.telegram_username = telegram_username
                    user.role = UserRole.PARTNER
                    user.access_status = AccessStatus.ACTIVE
                partner.telegram_user_id = user.id
                return UserRole.PARTNER

            if user is None or user.access_status == AccessStatus.BLOCKED:
                return None
            if user.telegram_username != telegram_username:
                user.telegram_username = telegram_username
            return user.role
