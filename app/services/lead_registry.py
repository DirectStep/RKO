from datetime import datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.database import Database
from app.domain.enums import BankInternalStatus
from app.integrations.google_sheets import LeadRegistryRow
from app.models import Bank, Lead, LeadBank, User


class LeadRegistryService:
    def __init__(self, database: Database, timezone_name: str) -> None:
        self.database = database
        self.timezone = ZoneInfo(timezone_name)

    async def activation_row(self, lead_bank_id: UUID, manager_id: UUID) -> LeadRegistryRow:
        async with self.database.session() as session:
            lead_bank = await session.get(LeadBank, lead_bank_id)
            lead = await session.get(Lead, lead_bank.lead_id) if lead_bank else None
            bank = await session.get(Bank, lead_bank.bank_id) if lead_bank else None
            manager = await session.get(User, manager_id)
        if (lead is None or bank is None or manager is None or lead_bank is None
                or lead_bank.opened_at is None):
            raise RuntimeError("Не удалось собрать данные активации для Google Sheets")
        activation = lead_bank.opened_at
        local_activation = activation.astimezone(self.timezone)
        return LeadRegistryRow(
            application_id=lead.short_id,
            activated_at=local_activation.strftime("%d.%m.%Y %H:%M"),
            lead=self._telegram_name(lead.telegram_username, lead.telegram_id),
            manager=self._telegram_name(manager.telegram_username, manager.telegram_id),
            bank=bank.name,
            application_status="Счёт активирован",
            expected_payment_at=expected_payment_date(activation, self.timezone),
        )

    async def payment_values(self, lead_bank_id: UUID) -> tuple[str, str, str, float, str]:
        async with self.database.session() as session:
            lead_bank = await session.get(LeadBank, lead_bank_id)
            lead = await session.get(Lead, lead_bank.lead_id) if lead_bank else None
            bank = await session.get(Bank, lead_bank.bank_id) if lead_bank else None
        if (lead is None or bank is None or lead_bank is None
                or lead_bank.lead_reward_paid_at is None):
            raise RuntimeError("Не удалось собрать данные выплаты для Google Sheets")
        return (
            lead.short_id,
            bank.name,
            lead_bank.lead_reward_paid_at.astimezone(self.timezone).strftime("%d.%m.%Y %H:%M"),
            float(lead_bank.lead_reward_fact or 0),
            "Выплачено",
        )

    @staticmethod
    def _telegram_name(username: str | None, telegram_id: str | None) -> str:
        return f"@{username}" if username else telegram_id or "Не указан"


def expected_payment_date(activated_at: datetime, timezone: ZoneInfo) -> str:
    return (activated_at.astimezone(timezone) + timedelta(days=30)).strftime("%d.%m.%Y")
