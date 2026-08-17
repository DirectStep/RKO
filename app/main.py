import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import SimpleEventIsolation

from app.bot.admin_handlers import router as admin_router
from app.bot.handlers import router
from app.config import get_settings
from app.database import Database
from app.logging import configure_logging

logger = logging.getLogger(__name__)


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    database = Database(settings)
    bot = Bot(token=settings.bot_token.get_secret_value())
    dispatcher = Dispatcher(events_isolation=SimpleEventIsolation())
    dispatcher.include_router(admin_router)
    dispatcher.include_router(router)

    logger.info("Starting RKO bot in %s environment", settings.app_env)
    try:
        await database.ping()
        await dispatcher.start_polling(bot, database=database, settings=settings)
    finally:
        await bot.session.close()
        await database.close()


if __name__ == "__main__":
    asyncio.run(run())
