from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import or_, select

from app.database import Database
from app.domain.enums import (
    BankInternalStatus,
    LeadInternalStatus,
    LeadWorkflowStage,
    UserRole,
)
from app.domain.operations import DomainError
from app.domain.partner_economics import partner_reward
from app.domain.statuses import external_bank_status, external_lead_status
from app.models import Lead, LeadBank


class LeadWorkflowService:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def claim_by_admin(self, *, actor_role: UserRole, actor_id: UUID, lead_id: UUID) -> Lead:
        if actor_role is not UserRole.ADMIN:
            raise DomainError("Первично взять заявку может только администратор")
        async with self.database.session() as session, session.begin():
            lead = await session.scalar(select(Lead).where(Lead.id == lead_id).with_for_update())
            if lead is None:
                raise DomainError("Заявка не найдена")
            if lead.workflow_stage is LeadWorkflowStage.NOT_ELIGIBLE:
                raise DomainError("Неподходящую заявку нельзя взять в работу")
            if lead.primary_admin_id == actor_id:
                return lead
            if (
                lead.workflow_stage is not LeadWorkflowStage.AWAITING_ADMIN
                or lead.primary_admin_id is not None
            ):
                raise DomainError("Заявку уже взял другой администратор")
            lead.primary_admin_id = actor_id
            lead.workflow_stage = LeadWorkflowStage.ADMIN_PROCESSING
            lead.internal_status = LeadInternalStatus.AWAITING_FIRST_CONTACT
            lead.external_status = external_lead_status(lead.internal_status)
            lead.last_updated_at = datetime.now(UTC)
            return lead

    async def publish_banks(self, *, actor_role: UserRole, actor_id: UUID, lead_id: UUID) -> Lead:
        if actor_role is not UserRole.ADMIN:
            raise DomainError("Опубликовать банки может только администратор")
        async with self.database.session() as session, session.begin():
            lead = await session.scalar(select(Lead).where(Lead.id == lead_id).with_for_update())
            if lead is None:
                raise DomainError("Заявка не найдена")
            if lead.primary_admin_id != actor_id:
                raise DomainError("Сначала возьми заявку в работу")
            if lead.workflow_stage not in {
                LeadWorkflowStage.ADMIN_PROCESSING,
                LeadWorkflowStage.AWAITING_CLIENT_SELECTION,
            }:
                raise DomainError("На этой стадии нельзя предложить банки")
            lead_banks = list(
                await session.scalars(
                    select(LeadBank).where(LeadBank.lead_id == lead_id).with_for_update()
                )
            )
            if not lead_banks:
                raise DomainError("Сначала добавьте хотя бы один банк")
            for lead_bank in lead_banks:
                lead_bank.offered_to_lead = True
                lead_bank.selected_by_lead = None
            now = datetime.now(UTC)
            lead.workflow_stage = LeadWorkflowStage.AWAITING_CLIENT_SELECTION
            lead.banks_published_at = now
            lead.bank_selection_submitted_at = None
            lead.manager_started_at = None
            lead.internal_status = LeadInternalStatus.SELECTING_BANKS
            lead.external_status = external_lead_status(lead.internal_status)
            lead.last_updated_at = now
            return lead

    async def submit_bank_selection(self, *, lead_id: UUID, selected_bank_ids: set[UUID]) -> Lead:
        if not selected_bank_ids:
            raise DomainError("Выберите хотя бы один банк")
        async with self.database.session() as session, session.begin():
            lead = await session.scalar(select(Lead).where(Lead.id == lead_id).with_for_update())
            if lead is None:
                raise DomainError("Заявка не найдена")
            lead_banks = list(
                await session.scalars(
                    select(LeadBank)
                    .where(
                        LeadBank.lead_id == lead_id,
                        LeadBank.offered_to_lead.is_(True),
                        or_(
                            LeadBank.selected_by_lead.is_(None),
                            LeadBank.selected_by_lead.is_(False),
                        ),
                    )
                    .with_for_update()
                )
            )
            pending_ids = {lead_bank.bank_id for lead_bank in lead_banks}
            if not pending_ids:
                raise DomainError("Новых банков для выбора нет")
            if not selected_bank_ids.issubset(pending_ids):
                raise DomainError("В списке есть недоступный банк")
            now = datetime.now(UTC)
            for lead_bank in lead_banks:
                if lead_bank.bank_id in selected_bank_ids:
                    lead_bank.selected_by_lead = True
                    if lead_bank.internal_status in {
                        BankInternalStatus.CLIENT_REFUSED,
                        BankInternalStatus.NOT_OPENED,
                    }:
                        lead_bank.internal_status = BankInternalStatus.PLANNED
                        lead_bank.external_status = external_bank_status(
                            BankInternalStatus.PLANNED
                        )
                        lead_bank.closed_without_open_at = None
                        lead_bank.close_reason = None
                        if (
                            lead_bank.bank_income_estimate is not None
                            and lead_bank.partner_percent_snapshot is not None
                        ):
                            lead_bank.partner_reward_estimate = partner_reward(
                                lead_bank.bank_income_estimate,
                                lead_bank.lead_reward_estimate,
                                lead_bank.partner_percent_snapshot,
                                lead_reward_paid_separately=lead_bank.lead_reward_paid_separately,
                            )
                            lead_bank.team_profit_estimate = (
                                lead_bank.bank_income_estimate
                                - (lead_bank.partner_reward_estimate or Decimal("0"))
                                - (
                                    Decimal("0")
                                    if lead_bank.lead_reward_paid_separately
                                    else lead_bank.lead_reward_estimate or Decimal("0")
                                )
                            ).quantize(Decimal("0.01"))
                        lead_bank.partner_reward_fact = None
                        lead_bank.team_profit_fact = None
                        lead_bank.last_updated_at = now
                elif lead_bank.selected_by_lead is None:
                    lead_bank.selected_by_lead = False
            if lead.workflow_stage is LeadWorkflowStage.AWAITING_CLIENT_SELECTION:
                lead.workflow_stage = LeadWorkflowStage.AWAITING_MANAGER
                lead.internal_status = LeadInternalStatus.DATA_RECEIVED
                lead.external_status = external_lead_status(lead.internal_status)
            lead.bank_selection_submitted_at = now
            lead.manager_started_at = None
            lead.last_updated_at = now
            return lead

    async def claim_by_manager(
        self, *, actor_role: UserRole, actor_id: UUID, lead_id: UUID
    ) -> Lead:
        if actor_role is not UserRole.MANAGER:
            raise DomainError("На этой стадии заявку может взять только менеджер")
        async with self.database.session() as session, session.begin():
            lead = await session.scalar(select(Lead).where(Lead.id == lead_id).with_for_update())
            if lead is None:
                raise DomainError("Заявка не найдена")
            if lead.manager_id == actor_id and lead.manager_started_at is not None:
                return lead
            if lead.workflow_stage not in {
                LeadWorkflowStage.AWAITING_MANAGER,
                LeadWorkflowStage.MANAGER_PROCESSING,
            }:
                raise DomainError("Заявка уже взята или ещё не готова")
            if lead.manager_id is not None and lead.manager_id != actor_id:
                raise DomainError("Заявка закреплена за другим менеджером")
            now = datetime.now(UTC)
            lead.manager_id = actor_id
            lead.manager_started_at = now
            if lead.workflow_stage is LeadWorkflowStage.AWAITING_MANAGER:
                lead.workflow_stage = LeadWorkflowStage.MANAGER_PROCESSING
                lead.internal_status = LeadInternalStatus.PREPARING_APPLICATIONS
                lead.external_status = external_lead_status(lead.internal_status)
            lead.last_updated_at = now
            return lead
