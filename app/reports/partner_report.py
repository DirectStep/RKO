import csv
import io
from uuid import UUID

from sqlalchemy import select

from app.database import Database
from app.domain.enums import AssignmentStatus, PaymentStatus
from app.models import Bank, Channel, Lead, LeadBank, Payment

LEAD_STATUS_LABELS = {
    "new": "Новая",
    "in_progress": "В работе",
    "opening_accounts": "Открытие счетов",
    "partially_completed": "Частично завершена",
    "completed": "Завершена",
    "paused": "На паузе",
    "closed_without_result": "Закрыта без результата",
}
PAYMENT_STATUS_LABELS = {
    "not_calculated": "Не рассчитана",
    "calculated": "Рассчитана",
    "awaiting_confirmation": "Ждёт подтверждения",
    "confirmed": "Подтверждена",
    "in_registry": "В реестре",
    "paid": "Выплачена",
    "cancelled": "Отменена",
}


async def build_partner_report(database: Database, partner_id: UUID) -> bytes:
    async with database.session() as session:
        result = await session.execute(
            select(Lead, Channel.name, LeadBank, Bank.name, Payment)
            .join(Channel, Channel.id == Lead.channel_id)
            .outerjoin(LeadBank, LeadBank.lead_id == Lead.id)
            .outerjoin(Bank, Bank.id == LeadBank.bank_id)
            .outerjoin(Payment, Payment.lead_bank_id == LeadBank.id)
            .where(
                Lead.partner_id == partner_id,
                Lead.assignment_status == AssignmentStatus.CONFIRMED,
            )
            .order_by(Lead.application_at.desc(), Bank.name)
        )
        report_rows = list(result)

    output = io.StringIO(newline="")
    output.write("\ufeff")
    writer = csv.writer(output, delimiter=";")
    writer.writerow(
        [
            "Заявка",
            "Дата",
            "Статус",
            "Канал",
            "Банк",
            "Статус банка",
            "Вознаграждение",
            "Выплата",
        ]
    )
    for lead, channel_name, lead_bank, bank_name, payment in report_rows:
        payment_status = payment.status if payment else PaymentStatus.NOT_CALCULATED
        writer.writerow(
            [
                lead.short_id,
                lead.application_at.date().isoformat(),
                LEAD_STATUS_LABELS[lead.external_status.value],
                channel_name,
                bank_name or "",
                lead_bank.external_status.value if lead_bank else "",
                lead_bank.partner_reward_fact or "" if lead_bank else "",
                PAYMENT_STATUS_LABELS[payment_status.value],
            ]
        )
    return output.getvalue().encode("utf-8")
