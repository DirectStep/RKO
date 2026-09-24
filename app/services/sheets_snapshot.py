import json
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select

from app.database import Database
from app.domain.enums import BankInternalStatus, PaymentStatus
from app.integrations.google_sheets import PARTNER_PAYOUTS_TITLE, SheetData
from app.models import (
    Bank,
    BankRate,
    Channel,
    DuplicateLeadReview,
    Lead,
    LeadBank,
    Partner,
    Payment,
    User,
)

SHEET_MODELS = (
    ("Пользователи", User),
    ("Партнёры", Partner),
    ("Каналы", Channel),
    ("Заявки", Lead),
    ("Банки", Bank),
    ("Ставки банков", BankRate),
    ("Банки заявок", LeadBank),
    ("Выплаты", Payment),
    ("Проверка дублей", DuplicateLeadReview),
)
PARTNER_PAYOUTS_HEADERS = (
    "Партнёр",
    "Лид",
    "Банк",
    "Дата заявки",
    "Статус",
    "Фактическая сумма выплаты",
    "Статус выплаты",
    "Дата выплаты",
)


class SheetsSnapshotService:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def build(self) -> list[SheetData]:
        sheets: list[SheetData] = []
        async with self.database.session() as session:
            for title, model in SHEET_MODELS:
                columns = tuple(column.name for column in model.__table__.columns)
                entities = await session.scalars(select(model).order_by(model.id))
                rows = [
                    [serialize_cell(getattr(entity, column)) for column in columns]
                    for entity in entities
                ]
                sheets.append(SheetData(title=title, headers=columns, rows=rows))
            payout_rows = await session.execute(
                select(Partner, Lead, LeadBank, Bank, Payment)
                .join(Lead, Lead.partner_id == Partner.id)
                .join(LeadBank, LeadBank.lead_id == Lead.id)
                .join(Bank, Bank.id == LeadBank.bank_id)
                .outerjoin(Payment, Payment.lead_bank_id == LeadBank.id)
                .where(
                    or_(
                        LeadBank.selected_by_lead.is_(True),
                        LeadBank.internal_status == BankInternalStatus.CLIENT_REFUSED,
                        LeadBank.internal_status == BankInternalStatus.NOT_OPENED,
                    )
                )
                .order_by(Lead.application_at, Lead.short_id, Bank.name)
            )
            rows = [partner_payout_row(*record) for record in payout_rows]
            sheets.append(SheetData(PARTNER_PAYOUTS_TITLE, PARTNER_PAYOUTS_HEADERS, rows))
        sheets.extend(
            [
                SheetData("Справочники", ("group", "key", "value", "active"), []),
                SheetData("Ошибки синхронизации", ("created_at", "sheet", "row_id", "error"), []),
            ]
        )
        return sheets


def partner_payout_row(
    partner: Partner, lead: Lead, lead_bank: LeadBank, bank: Bank, payment: Payment | None
) -> list[str | float]:
    amount = (
        payment.partner_reward_fact
        if payment and payment.partner_reward_fact is not None
        else lead_bank.partner_reward_fact
    )
    if payment is not None and payment.status is PaymentStatus.CANCELLED:
        amount = None
    paid = payment is not None and payment.status is PaymentStatus.PAID
    activated = lead_bank.internal_status is BankInternalStatus.ACCOUNT_OPENED
    if (
        not activated
        or (lead_bank.lead_reward_paid_at is None and not lead_bank.lead_reward_paid_separately)
    ) and not paid:
        amount = None
    return [
        f"@{partner.telegram_username}" if partner.telegram_username else partner.name,
        f"@{lead.telegram_username}" if lead.telegram_username else lead.telegram_id,
        bank.name,
        lead.application_at.astimezone(ZoneInfo("Europe/Moscow")).strftime("%d.%m.%Y"),
        "Активирован" if activated else "Не активирован",
        float(amount) if amount is not None else "",
        "Выплачено" if paid else "Не выплачено" if amount is not None else "",
        payment.paid_at.strftime("%d.%m.%Y") if paid and payment and payment.paid_at else "",
    ]


def serialize_cell(value: Any) -> str | int | float | bool:
    if value is None:
        return ""
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
