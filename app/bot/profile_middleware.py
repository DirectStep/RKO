import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from aiogram import BaseMiddleware, Bot
from aiogram.types import CallbackQuery, Message, TelegramObject

from app.database import Database
from app.services.telegram_profiles import observe_telegram_profile

logger = logging.getLogger(__name__)


class TelegramProfileMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, (Message, CallbackQuery)) and event.from_user:
            database: Database = data["database"]
            bots: tuple[Bot, ...] = data["notification_bots"]
            try:
                await observe_telegram_profile(
                    database,
                    bots,
                    str(event.from_user.id),
                    event.from_user.username,
                    event.date if isinstance(event, Message) else datetime.now(UTC),
                )
            except Exception:
                logger.exception("Could not update Telegram username from bot event")
        return await handler(event, data)
