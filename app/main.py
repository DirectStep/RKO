import asyncio
import logging
from contextlib import suppress

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import SimpleEventIsolation

from app.bot.admin_catalog_handlers import router as admin_catalog_router
from app.bot.admin_handlers import router as admin_router
from app.bot.handlers import router
from app.bot.profile_middleware import TelegramProfileMiddleware
from app.config import get_settings
from app.database import Database
from app.logging import configure_logging
from app.services.telegram_profiles import run_telegram_profile_poll
from app.web import create_web_app
from app.workers.bank_conditions_sync import run_bank_conditions_sync
from app.workers.bank_rates_sync import run_bank_rates_sync
from app.workers.partner_payment_notifications import run_partner_payment_notifications
from app.workers.sheets_sync import run_sheets_sync
from app.workers.weekly_reports import run_weekly_reports

logger = logging.getLogger(__name__)


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    database = Database(settings)
    bots = tuple(Bot(token=token) for token in settings.bot_tokens)
    bot = bots[0]
    bot_users = await asyncio.gather(*(current_bot.get_me() for current_bot in bots))
    bot_usernames = tuple(user.username for user in bot_users if user.username)
    dispatcher = Dispatcher(events_isolation=SimpleEventIsolation())
    dispatcher.message.outer_middleware(TelegramProfileMiddleware())
    dispatcher.callback_query.outer_middleware(TelegramProfileMiddleware())
    dispatcher.include_router(admin_router)
    dispatcher.include_router(admin_catalog_router)
    dispatcher.include_router(router)
    sheets_task = asyncio.create_task(run_sheets_sync(database, settings))
    bank_rates_task = asyncio.create_task(run_bank_rates_sync(database, settings))
    bank_conditions_task = asyncio.create_task(run_bank_conditions_sync(database, settings))
    reports_task = asyncio.create_task(run_weekly_reports(database, bot, settings.project_timezone))
    profiles_task = asyncio.create_task(run_telegram_profile_poll(database, bots))
    payment_notifications_task = asyncio.create_task(
        run_partner_payment_notifications(database, bots)
    )
    web_server = uvicorn.Server(
        uvicorn.Config(
            create_web_app(database, settings, bot, bots[1:], bot_usernames),
            host=settings.mini_app_host,
            port=settings.mini_app_port,
            log_level=settings.log_level.lower(),
        )
    )
    web_task = asyncio.create_task(web_server.serve())

    logger.info(
        "Starting %s RKO bot(s) in %s environment: %s",
        len(bots),
        settings.app_env,
        ", ".join(f"@{username}" for username in bot_usernames),
    )
    try:
        await database.ping()
        await dispatcher.start_polling(
            *bots,
            database=database,
            settings=settings,
            notification_bots=bots,
            close_bot_session=False,
        )
    finally:
        sheets_task.cancel()
        bank_rates_task.cancel()
        bank_conditions_task.cancel()
        reports_task.cancel()
        profiles_task.cancel()
        payment_notifications_task.cancel()
        with suppress(asyncio.CancelledError):
            await sheets_task
        with suppress(asyncio.CancelledError):
            await bank_rates_task
        with suppress(asyncio.CancelledError):
            await bank_conditions_task
        with suppress(asyncio.CancelledError):
            await reports_task
        with suppress(asyncio.CancelledError):
            await profiles_task
        with suppress(asyncio.CancelledError):
            await payment_notifications_task
        web_server.should_exit = True
        await web_task
        for current_bot in bots:
            await current_bot.session.close()
        await database.close()


if __name__ == "__main__":
    asyncio.run(run())
