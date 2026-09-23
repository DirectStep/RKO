from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Database
from app.domain.enums import AssignmentStatus, PaymentStatus, UserRole
from app.domain.operations import DomainError, confirm_assignment, mark_assignment_direct
from app.domain.partner_economics import PARTNER_PERCENT, partner_reward
from app.models import Channel, Lead, LeadBank, Partner, Payment


class LeadAssignmentService:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def confirm_proposed(self, *, actor_role: UserRole, lead_id: UUID) -> Lead:
        async with self.database.session() as session, session.begin():
            lead = await session.scalar(select(Lead).where(Lead.id == lead_id).with_for_update())
            if lead is None:
                raise DomainError("Заявка не найдена")
            confirmation = confirm_assignment(
                actor_role=actor_role,
                current_status=lead.assignment_status,
                partner_id=lead.proposed_partner_id,
                channel_id=lead.proposed_channel_id,
                confirmed_at=datetime.now(UTC),
            )
            lead.partner_id = confirmation.partner_id
            lead.channel_id = confirmation.channel_id
            lead.assignment_status = AssignmentStatus.CONFIRMED
            lead.assignment_confirmed_at = confirmation.confirmed_at
            return lead

    async def propose_source(
        self,
        *,
        actor_role: UserRole,
        lead_id: UUID,
        partner_id: UUID,
        channel_id: UUID,
    ) -> Lead:
        if actor_role is not UserRole.ADMIN:
            raise DomainError("Источник может выбрать только администратор")
        async with self.database.session() as session, session.begin():
            lead = await session.scalar(select(Lead).where(Lead.id == lead_id).with_for_update())
            if lead is None:
                raise DomainError("Заявка не найдена")
            if lead.assignment_status not in {
                AssignmentStatus.UNRESOLVED,
                AssignmentStatus.PENDING,
            }:
                raise DomainError("Подтверждённый источник заявки нельзя изменить")
            channel = await session.get(Channel, channel_id)
            if channel is None or channel.partner_id != partner_id or not channel.active:
                raise DomainError("Активный канал партнёра не найден")
            lead.proposed_partner_id = partner_id
            lead.proposed_channel_id = channel_id
            lead.assignment_status = AssignmentStatus.PENDING
            return lead

    async def assign_source(
        self,
        *,
        actor_role: UserRole,
        actor_id: UUID,
        lead_id: UUID,
        partner_id: UUID,
        channel_id: UUID,
    ) -> Lead:
        if actor_role is not UserRole.ADMIN:
            raise DomainError("Источник может изменить только администратор")
        async with self.database.session() as session, session.begin():
            lead = await session.scalar(select(Lead).where(Lead.id == lead_id).with_for_update())
            if lead is None:
                raise DomainError("Заявка не найдена")
            channel = await session.get(Channel, channel_id)
            if channel is None or channel.partner_id != partner_id or not channel.active:
                raise DomainError("Активный канал партнёра не найден")
            partner = await session.get(Partner, partner_id)
            if partner is None or not partner.active:
                raise DomainError("Активный партнёр не найден")
            await self._apply_partner_economics(
                session,
                lead_id=lead.id,
                percent=PARTNER_PERCENT,
            )
            now = datetime.now(UTC)
            lead.proposed_partner_id = partner_id
            lead.proposed_channel_id = channel_id
            lead.partner_id = partner_id
            lead.channel_id = channel_id
            lead.assignment_status = AssignmentStatus.CONFIRMED
            lead.assignment_confirmed_at = now
            lead.source_updated_by_user_id = actor_id
            lead.source_updated_at = now
            return lead

    @classmethod
    async def _apply_partner_economics(
        cls,
        session: AsyncSession,
        *,
        lead_id: UUID,
        percent: Decimal | None,
    ) -> None:
        lead_banks = list(
            await session.scalars(
                select(LeadBank).where(LeadBank.lead_id == lead_id).with_for_update()
            )
        )
        if not lead_banks:
            return
        payments = list(
            await session.scalars(
                select(Payment)
                .where(Payment.lead_bank_id.in_([item.id for item in lead_banks]))
                .with_for_update()
            )
        )
        payments_by_bank = {payment.lead_bank_id: payment for payment in payments}
        if any(
            payment.status
            in {PaymentStatus.CONFIRMED, PaymentStatus.IN_REGISTRY, PaymentStatus.PAID}
            for payment in payments
        ):
            raise DomainError("Источник нельзя изменить после подтверждения партнёрской выплаты")
        now = datetime.now(UTC)
        for lead_bank in lead_banks:
            lead_bank.partner_percent_snapshot = percent
            lead_bank.partner_reward_estimate = cls._reward(
                lead_bank.bank_income_estimate, lead_bank.lead_reward_estimate
            )
            lead_bank.team_profit_estimate = cls._team_profit(
                income=lead_bank.bank_income_estimate,
                partner_reward=lead_bank.partner_reward_estimate,
                lead_reward=lead_bank.lead_reward_estimate,
                lead_reward_paid_separately=lead_bank.lead_reward_paid_separately,
            )
            if lead_bank.bank_income_fact is not None:
                lead_bank.partner_reward_fact = cls._reward(
                    lead_bank.bank_income_fact,
                    lead_bank.lead_reward_fact
                    if lead_bank.lead_reward_paid_at is not None
                    else lead_bank.lead_reward_estimate,
                )
                lead_bank.team_profit_fact = cls._team_profit(
                    income=lead_bank.bank_income_fact,
                    partner_reward=lead_bank.partner_reward_fact,
                    lead_reward=lead_bank.lead_reward_fact,
                    lead_reward_paid_separately=lead_bank.lead_reward_paid_separately,
                )
                payment = payments_by_bank.get(lead_bank.id)
                if payment is not None:
                    payment.partner_reward_fact = lead_bank.partner_reward_fact
            else:
                lead_bank.partner_reward_fact = None
                lead_bank.team_profit_fact = None
                payment = payments_by_bank.get(lead_bank.id)
                if payment is not None:
                    payment.partner_reward_fact = None
            lead_bank.last_updated_at = now

    @staticmethod
    def _reward(income: Decimal | None, lead_reward: Decimal | None) -> Decimal | None:
        return partner_reward(income, lead_reward)

    @staticmethod
    def _team_profit(
        *,
        income: Decimal | None,
        partner_reward: Decimal | None,
        lead_reward: Decimal | None,
        lead_reward_paid_separately: bool,
    ) -> Decimal | None:
        if income is None:
            return None
        profit = income - (partner_reward or Decimal("0"))
        profit -= lead_reward or Decimal("0")
        if profit < 0:
            raise DomainError("Ставки дают отрицательную командную прибыль")
        return profit.quantize(Decimal("0.01"))

    async def mark_direct(self, *, actor_role: UserRole, lead_id: UUID) -> Lead:
        async with self.database.session() as session, session.begin():
            lead = await session.scalar(select(Lead).where(Lead.id == lead_id).with_for_update())
            if lead is None:
                raise DomainError("Заявка не найдена")
            mark_assignment_direct(actor_role=actor_role, current_status=lead.assignment_status)
            lead.partner_id = None
            lead.channel_id = None
            lead.assignment_confirmed_at = None
            lead.assignment_status = AssignmentStatus.DIRECT
            return lead

    async def assign_direct(self, *, actor_role: UserRole, actor_id: UUID, lead_id: UUID) -> Lead:
        if actor_role is not UserRole.ADMIN:
            raise DomainError("Источник может изменить только администратор")
        async with self.database.session() as session, session.begin():
            lead = await session.scalar(select(Lead).where(Lead.id == lead_id).with_for_update())
            if lead is None:
                raise DomainError("Заявка не найдена")
            await self._apply_partner_economics(session, lead_id=lead.id, percent=None)
            lead.proposed_partner_id = None
            lead.proposed_channel_id = None
            lead.partner_id = None
            lead.channel_id = None
            lead.assignment_confirmed_at = None
            lead.assignment_status = AssignmentStatus.DIRECT
            lead.source_updated_by_user_id = actor_id
            lead.source_updated_at = datetime.now(UTC)
            return lead
