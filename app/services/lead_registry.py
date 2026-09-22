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

    async def activation_row(self, lead_id: UUID, manager_id: UUID) -> LeadRegistryRow:
        async with self.database.session() as session:
            lead = await session.get(Lead, lead_id)
            manager = await session.get(User, manager_id)
            activated = list(
                (
                    await session.execute(
                        select(LeadBank, Bank.name)
                        .join(Bank, Bank.id == LeadBank.bank_id)
                        .where(
                            LeadBank.lead_id == lead_id,
                            LeadBank.internal_status == BankInternalStatus.ACCOUNT_OPENED,
                        )
                        .order_by(LeadBank.opened_at, Bank.name)
                    )
                ).all()
            )
        if lead is None or manager is None or not activated:
            raise RuntimeError("Не удалось собрать данны активации для Google Sheets")
        activation = min(item.opened_at for item, _ in activated if item.opened_at is not None)
        local_activation = activation.astimezone(self.timezone)
        return LeadRegistryRow(
            application_id=lead.short_id,
            activated_at=local_activation.strftime("%d.%m.%Y %H:%M"),
            lead=self._telegram_name(lead.telegram_username, lead.telegram_id),
            manager=self._telegram_name(manager.telegram_username, manager.telegram_id),
            bank=", ".join(name for _, name in activated),
            application_status="Счёт активирован",
            expected_payment_at=expected_payment_date(activation, self.timezone),
        )

    async def payment_values(self, lead_id: UUID) -> tuple[str, str, float, str]:
        async with self.database.session() as session:
            lead = await session.get(Lead, lead_id)
            activated = list(
                await session.scalars(
                    select(LeadBank).where(
                        LeadBank.lead_id == lead_id,
                        LeadBank.internal_status == BankInternalStatus.ACCOUNT_OPENED,
                    )
                )
            )
        if lead is None or not activated:
            raise RuntimeError("Не удалось собрать данны выплаты для Google Sheets")
        paid = [item for item in activated if item.lead_reward_paid_at is not None]
        amount = sum((item.lead_reward_fact or 0 for item in paid), start=0)
        all_paid = len(paid) == len(activated)
        latest_payment = max(item.lead_reward_paid_at for item in paid)
        return (
            lead.short_id,
            latest_payment.astimezone(self.timezone).strftime("%d.%m.%Y %H:%M"),
            float(amount),
            "Выплачено" if all_paid else "Ожидается",
        )

    @staticmethod
    def _telegram_name(username: str | None, telegram_id: str | None) -> str:
        return f"@{username}" if username else telegram_id or "Не указан"


def expected_payment_date(activated_at: datetime, timezone: ZoneInfo) -> str:
    return (activated_at.astimezone(timezone) + timedelta(days=30)).strftime("%d.%m.%Y")
