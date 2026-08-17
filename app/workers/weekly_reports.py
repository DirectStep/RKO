import asyncio
import logging
from datetime import UTC, datetime, time, timedelta, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Bot
from aiogram.types import BufferedInputFile
from sqlalchemy import select

from app.database import Database
from app.domain.enums import AccessStatus
from app.models import Partner, User
from app.reports.partner_report import build_partner_report

logger = logging.getLogger(__name__)
FRIDAY = 4


def next_report_at(now: datetime) -> datetime:
    days_ahead = (FRIDAY - now.weekday()) % 7
    target = datetime.combine(now.date() + timedelta(days=days_ahead), time(20), now.tzinfo)
    if target <= now:
        target += timedelta(days=7)
    return target


async def send_partner_reports(database: Database, bot: Bot) -> int:
    async with database.session() as session:
        rows = await session.execute(
            select(Partner, User.telegram_id)
            .join(User, User.id == Partner.telegram_user_id)
            .where(Partner.active.is_(True), User.access_status == AccessStatus.ACTIVE)
            .order_by(Partner.name)
        )
        recipients = list(rows)

    sent = 0
    for partner, telegram_id in recipients:
        try:
            report = await build_partner_report(database, partner.id)
            document = BufferedInputFile(report, filename="rko-weekly-report.csv")
            await bot.send_document(
                chat_id=int(telegram_id),
                document=document,
                caption="Еженедельный отчёт РКО. Файл открывается в Excel.",
            )
            sent += 1
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Failed to send weekly report to partner %s", partner.id)
    return sent


async def run_weekly_reports(database: Database, bot: Bot, timezone_name: str) -> None:
    try:
        timezone: tzinfo = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        logger.error("Unknown report timezone %s; UTC is used", timezone_name)
        timezone = UTC
    while True:
        now = datetime.now(timezone)
        target = next_report_at(now)
        logger.info("Next weekly partner report is scheduled for %s", target.isoformat())
        await asyncio.sleep((target - now).total_seconds())
        sent = await send_partner_reports(database, bot)
        logger.info("Weekly partner reports sent: %s", sent)
