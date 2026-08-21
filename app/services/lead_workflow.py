from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from app.database import Database
from app.domain.enums import (
    LeadInternalStatus,
    LeadWorkflowStage,
    UserRole,
)
from app.domain.operations import DomainError
from app.domain.statuses import external_lead_status
from app.models import Lead, LeadBank


class LeadWorkflowService:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def claim_by_admin(
        self, *, actor_role: UserRole, actor_id: UUID, lead_id: UUID
    ) -> Lead:
        if actor_role is not UserRole.ADMIN:
            raise DomainError("Первично взять заявку может только администратор")
        async with self.database.session() as session, session.begin():
            lead = await session.scalar(
                select(Lead).where(Lead.id == lead_id).with_for_update()
            )
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

    async def publish_banks(
        self, *, actor_role: UserRole, actor_id: UUID, lead_id: UUID
    ) -> Lead:
        if actor_role is not UserRole.ADMIN:
            raise DomainError("Опубликовать банки может только администратор")
        async with self.database.session() as session, session.begin():
            lead = await session.scalar(
                select(Lead).where(Lead.id == lead_id).with_for_update()
            )
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
                    select(LeadBank)
                    .where(LeadBank.lead_id == lead_id)
                    .with_for_update()
                )
            )
            if not lead_banks:
                raise DomainError("Сначала добавь хотя бы один банк")
            for lead_bank in lead_banks:
                lead_bank.offered_to_lead = True
                lead_bank.selected_by_lead = None
            now = datetime.now(UTC)
            lead.workflow_stage = LeadWorkflowStage.AWAITING_CLIENT_SELECTION
            lead.banks_published_at = now
            lead.bank_selection_submitted_at = None
            lead.internal_status = LeadInternalStatus.SELECTING_BANKS
            lead.external_status = external_lead_status(lead.internal_status)
            lead.last_updated_at = now
            return lead

    async def submit_bank_selection(
        self, *, lead_id: UUID, selected_bank_ids: set[UUID]
    ) -> Lead:
        if not selected_bank_ids:
            raise DomainError("Выбери хотя бы один банк")
        async with self.database.session() as session, session.begin():
            lead = await session.scalar(
                select(Lead).where(Lead.id == lead_id).with_for_update()
            )
            if lead is None:
                raise DomainError("Заявка не найдена")
            if lead.workflow_stage is not LeadWorkflowStage.AWAITING_CLIENT_SELECTION:
                raise DomainError("Выбор банков уже отправлен или пока недоступен")
            lead_banks = list(
                await session.scalars(
                    select(LeadBank)
                    .where(
                        LeadBank.lead_id == lead_id,
                        LeadBank.offered_to_lead.is_(True),
                    )
                    .with_for_update()
                )
            )
            offered_ids = {lead_bank.bank_id for lead_bank in lead_banks}
            if not selected_bank_ids.issubset(offered_ids):
                raise DomainError("В списке есть недоступный банк")
            for lead_bank in lead_banks:
                lead_bank.selected_by_lead = lead_bank.bank_id in selected_bank_ids
            now = datetime.now(UTC)
            lead.workflow_stage = LeadWorkflowStage.AWAITING_MANAGER
            lead.bank_selection_submitted_at = now
            lead.internal_status = LeadInternalStatus.DATA_RECEIVED
            lead.external_status = external_lead_status(lead.internal_status)
            lead.last_updated_at = now
            return lead

    async def claim_by_manager(
        self, *, actor_role: UserRole, actor_id: UUID, lead_id: UUID
    ) -> Lead:
        if actor_role is not UserRole.MANAGER:
            raise DomainError("На этой стадии заявку может взять только менеджер")
        async with self.database.session() as session, session.begin():
            lead = await session.scalar(
                select(Lead).where(Lead.id == lead_id).with_for_update()
            )
            if lead is None:
                raise DomainError("Заявка не найдена")
            if lead.manager_id == actor_id:
                return lead
            if (
                lead.workflow_stage is not LeadWorkflowStage.AWAITING_MANAGER
                or lead.manager_id is not None
            ):
                raise DomainError("Заявка уже взята или ещё не готова")
            now = datetime.now(UTC)
            lead.manager_id = actor_id
            lead.workflow_stage = LeadWorkflowStage.MANAGER_PROCESSING
            lead.internal_status = LeadInternalStatus.PREPARING_APPLICATIONS
            lead.external_status = external_lead_status(lead.internal_status)
            lead.last_updated_at = now
            return lead
