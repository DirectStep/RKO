import asyncio
import logging
from datetime import UTC, datetime
from html import escape

from aiogram import Bot
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from app.database import Database
from app.domain.enums import AccessStatus, UserRole
from app.models import DuplicateLeadReview, Lead, Partner, TelegramProfile, User

logger = logging.getLogger(__name__)


def _username(value: str | None) -> str | None:
    return value.strip().lstrip("@") or None if value else None


def _label(value: str | None) -> str:
    return f"@{escape(value)}" if value else "без username"


async def observe_telegram_profile(
    database: Database,
    bots: tuple[Bot, ...],
    telegram_id: str,
    username: str | None,
    observed_at: datetime,
) -> bool:
    """Apply a fresh Telegram observation once, then notify the responsible people."""
    username = _username(username)
    observed_at = observed_at.astimezone(UTC)
    notifications: list[tuple[set[str], str]] = []
    async with database.session() as session, session.begin():
        inserted = await session.execute(
            insert(TelegramProfile)
            .values(telegram_id=telegram_id, username=username, observed_at=observed_at)
            .on_conflict_do_nothing(index_elements=[TelegramProfile.telegram_id])
        )
        profile = await session.scalar(
            select(TelegramProfile)
            .where(TelegramProfile.telegram_id == telegram_id)
            .with_for_update()
        )
        if profile is None:
            return False
        active_leads = list(
            await session.scalars(
                select(Lead)
                .where(Lead.telegram_id == telegram_id, Lead.archived_at.is_(None))
                .order_by(Lead.application_at.desc())
            )
        )
        lead = active_leads[0] if active_leads else None
        any_lead = lead or await session.scalar(
            select(Lead).where(Lead.telegram_id == telegram_id).limit(1)
        )
        user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
        partner = await session.scalar(
            select(Partner).where(Partner.telegram_user_id == user.id)
            if user is not None
            else select(Partner).where(Partner.id.is_(None))
        )
        previous_lead = _username(any_lead.telegram_username) if any_lead else None
        previous_partner = _username(partner.telegram_username) if partner else None
        previous_user = _username(user.telegram_username) if user else None
        lead_changed = (
            any_lead is not None and (previous_lead or "").casefold() != (username or "").casefold()
        )
        partner_changed = (
            partner is not None
            and (previous_partner or "").casefold() != (username or "").casefold()
        )
        user_changed = (
            user is not None and (previous_user or "").casefold() != (username or "").casefold()
        )
        if profile.observed_at > observed_at:
            return False
        if profile.observed_at == observed_at and profile.username != username:
            return False
        changed = lead_changed or partner_changed or user_changed
        profile.username = username
        profile.observed_at = observed_at
        if user is not None:
            user.telegram_username = username
        if any_lead is not None:
            await session.execute(
                update(Lead)
                .where(Lead.telegram_id == telegram_id)
                .values(telegram_username=username)
            )
        await session.execute(
            update(DuplicateLeadReview)
            .where(DuplicateLeadReview.telegram_id == telegram_id)
            .values(telegram_username=username)
        )
        if partner is not None:
            partner.telegram_username = username
        if (
            lead_changed
            and (previous_lead is not None or inserted.rowcount == 0)
            and lead is not None
        ):
            recipients: set[str] = set()
            staff_ids = {
                staff_id
                for item in active_leads
                for staff_id in (item.manager_id, item.primary_admin_id)
                if staff_id is not None
            }
            for staff_id in staff_ids:
                staff = await session.get(User, staff_id)
                if (
                    staff
                    and staff.telegram_id
                    and staff.access_status == AccessStatus.ACTIVE
                    and staff.role in {UserRole.ADMIN, UserRole.MANAGER}
                ):
                    recipients.add(staff.telegram_id)
            notification = (
                f"Лид изменил username Telegram\n"
                f"Заявка: <code>{escape(lead.short_id)}</code>\n"
                f"{_label(previous_lead)} → {_label(username)}"
            )
            notifications.append((recipients, notification))
        if (
            partner_changed
            and (previous_partner is not None or inserted.rowcount == 0)
            and partner is not None
        ):
            recipients = set()
            admin = (
                await session.get(User, partner.assigned_manager_id)
                if partner.assigned_manager_id
                else None
            )
            if (
                admin
                and admin.role == UserRole.ADMIN
                and admin.access_status == AccessStatus.ACTIVE
                and admin.telegram_id
            ):
                recipients.add(admin.telegram_id)
            notification = (
                f"Партнёр {escape(partner.name)} изменил username Telegram\n"
                f"{_label(previous_partner)} → {_label(username)}"
            )
            notifications.append((recipients, notification))
    for recipients, notification in notifications:
        for recipient in recipients:
            for bot in bots:
                try:
                    await bot.send_message(int(recipient), notification, parse_mode="HTML")
                    break
                except Exception:
                    logger.warning(
                        "Could not notify %s about username change via bot %s", recipient, bot.id
                    )
            else:
                logger.error("Failed to notify %s about username change", recipient)
    return changed


async def poll_telegram_profiles(database: Database, bots: tuple[Bot, ...]) -> None:
    async with database.session() as session:
        lead_ids = await session.scalars(
            select(Lead.telegram_id).where(Lead.archived_at.is_(None)).distinct()
        )
        partner_ids = await session.scalars(
            select(User.telegram_id)
            .join(Partner, Partner.telegram_user_id == User.id)
            .where(Partner.active.is_(True), User.telegram_id.is_not(None))
        )
        telegram_ids = set(lead_ids) | set(partner_ids)
    for telegram_id in telegram_ids:
        try:
            for bot in bots:
                try:
                    chat = await asyncio.wait_for(bot.get_chat(int(telegram_id)), timeout=5)
                except Exception:
                    continue
                await observe_telegram_profile(
                    database, bots, telegram_id, chat.username, datetime.now(UTC)
                )
                break
        except Exception:
            logger.exception("Could not poll Telegram profile %s", telegram_id)


async def run_telegram_profile_poll(database: Database, bots: tuple[Bot, ...]) -> None:
    while True:
        try:
            await poll_telegram_profiles(database, bots)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Telegram username poll failed")
        await asyncio.sleep(60)
