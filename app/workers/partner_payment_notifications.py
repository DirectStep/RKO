import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID

from aiogram import Bot
from sqlalchemy import select

from app.database import Database
from app.domain.enums import AccessStatus, AssignmentStatus, PaymentStatus
from app.models import Bank, Lead, LeadBank, Partner, Payment, User

logger = logging.getLogger(__name__)


async def deliver_partner_payment_notification(
    database: Database, bots: tuple[Bot, ...], payment_id: UUID
) -> bool:
    if not bots:
        return False
    async with database.session() as session, session.begin():
        payment = await session.scalar(
            select(Payment).where(Payment.id == payment_id).with_for_update()
        )
        if (
            payment is None
            or payment.status is not PaymentStatus.PAID
            or payment.partner_notification_sent_at is not None
            or not payment.partner_reward_fact
        ):
            return False
        details = (
            await session.execute(
                select(Lead.short_id, Bank.name, User.telegram_id)
                .select_from(Payment)
                .join(LeadBank, LeadBank.id == Payment.lead_bank_id)
                .join(Bank, Bank.id == LeadBank.bank_id)
                .join(Lead, Lead.id == LeadBank.lead_id)
                .join(Partner, Partner.id == Lead.partner_id)
                .join(User, User.id == Partner.telegram_user_id)
                .where(
                    Payment.id == payment_id,
                    Lead.assignment_status == AssignmentStatus.CONFIRMED,
                    Partner.active.is_(True),
                    User.access_status == AccessStatus.ACTIVE,
                )
            )
        ).one_or_none()
        if details is None or not details.telegram_id:
            # A partner without active Telegram access does not require a message.
            payment.partner_notification_sent_at = datetime.now(UTC)
            return False
        from app.web import format_partner_reward_message

        text = format_partner_reward_message(
            details.short_id, details.name, payment.partner_reward_fact
        )
        for bot in bots:
            try:
                await bot.send_message(
                    chat_id=int(details.telegram_id), text=text, parse_mode="HTML"
                )
                payment.partner_notification_sent_at = datetime.now(UTC)
                return True
            except Exception:
                logger.exception("Failed to notify partner for payment %s", payment_id)
        return False


async def run_partner_payment_notifications(
    database: Database, bots: tuple[Bot, ...]
) -> None:
    while True:
        try:
            async with database.session() as session:
                pending_ids = list(
                    await session.scalars(
                        select(Payment.id)
                        .where(
                            Payment.status == PaymentStatus.PAID,
                            Payment.partner_notification_sent_at.is_(None),
                            Payment.partner_reward_fact > 0,
                        )
                        .order_by(Payment.confirmed_at)
                        .limit(50)
                    )
                )
            for payment_id in pending_ids:
                await deliver_partner_payment_notification(database, bots, payment_id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Partner payment notification retry failed")
        await asyncio.sleep(30)
