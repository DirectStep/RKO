from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select

from app.database import Database
from app.domain.enums import AssignmentStatus, UserRole
from app.domain.operations import DomainError, confirm_assignment, mark_assignment_direct
from app.models import Channel, Lead


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
