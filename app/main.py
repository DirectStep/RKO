import asyncio
import logging
from contextlib import suppress

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import SimpleEventIsolation

from app.bot.admin_catalog_handlers import router as admin_catalog_router
from app.bot.admin_handlers import router as admin_router
from app.bot.handlers import router
from app.config import get_settings
from app.database import Database
from app.logging import configure_logging
from app.workers.sheets_sync import run_sheets_sync

logger = logging.getLogger(__name__)


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    database = Database(settings)
    bot = Bot(token=settings.bot_token.get_secret_value())
    dispatcher = Dispatcher(events_isolation=SimpleEventIsolation())
    dispatcher.include_router(admin_router)
    dispatcher.include_router(admin_catalog_router)
    dispatcher.include_router(router)
    sheets_task = asyncio.create_task(run_sheets_sync(database, settings))

    logger.info("Starting RKO bot in %s environment", settings.app_env)
    try:
        await database.ping()
        await dispatcher.start_polling(bot, database=database, settings=settings)
    finally:
        sheets_task.cancel()
        with suppress(asyncio.CancelledError):
            await sheets_task
        await bot.session.close()
        await database.close()


if __name__ == "__main__":
    asyncio.run(run())
