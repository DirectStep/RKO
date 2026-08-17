from sqlalchemy import func, select

from app.config import Settings
from app.database import Database
from app.domain.enums import AccessStatus, UserRole
from app.models import User


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

            if user is None or user.access_status == AccessStatus.BLOCKED:
                return None
            if user.telegram_username != telegram_username:
                user.telegram_username = telegram_username
            return user.role
