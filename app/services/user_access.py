from sqlalchemy import select

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
            if telegram_id in self.settings.admin_ids:
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
