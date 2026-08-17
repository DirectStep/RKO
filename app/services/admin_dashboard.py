from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select

from app.database import Database
from app.domain.enums import AssignmentStatus, LeadInternalStatus
from app.models import DuplicateLeadReview, Lead


@dataclass(frozen=True)
class AdminStats:
    total_leads: int
    new_leads: int
    unresolved_sources: int
    pending_duplicates: int


class AdminDashboardService:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def get_stats(self) -> AdminStats:
        async with self.database.session() as session:
            total_leads = await session.scalar(select(func.count()).select_from(Lead))
            new_leads = await session.scalar(
                select(func.count())
                .select_from(Lead)
                .where(Lead.internal_status == LeadInternalStatus.NEW)
            )
            unresolved_sources = await session.scalar(
                select(func.count())
                .select_from(Lead)
                .where(Lead.assignment_status == AssignmentStatus.UNRESOLVED)
            )
            pending_duplicates = await session.scalar(
                select(func.count())
                .select_from(DuplicateLeadReview)
                .where(DuplicateLeadReview.review_status == "pending")
            )
        return AdminStats(
            total_leads=total_leads or 0,
            new_leads=new_leads or 0,
            unresolved_sources=unresolved_sources or 0,
            pending_duplicates=pending_duplicates or 0,
        )

    async def get_recent_leads(self, limit: int = 10) -> list[Lead]:
        async with self.database.session() as session:
            result = await session.scalars(
                select(Lead).order_by(Lead.application_at.desc()).limit(limit)
            )
            return list(result)

    async def get_lead(self, lead_id: UUID) -> Lead | None:
        async with self.database.session() as session:
            return await session.get(Lead, lead_id)
