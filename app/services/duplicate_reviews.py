from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, text

from app.database import Database
from app.domain.enums import (
    AssignmentStatus,
    DuplicateResolution,
    LeadExternalStatus,
    LeadInternalStatus,
    LeadWorkflowStage,
    UserRole,
)
from app.domain.intake import is_eligible
from app.domain.operations import DomainError
from app.models import Channel, DuplicateLeadReview, Lead, Partner


class DuplicateReviewService:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def resolve(
        self,
        *,
        actor_role: UserRole,
        actor_id: UUID,
        review_id: UUID,
        resolution: DuplicateResolution,
    ) -> tuple[DuplicateLeadReview, Lead | None]:
        if actor_role is not UserRole.ADMIN:
            raise DomainError("Дубли может проверять только администратор")
        async with self.database.session() as session, session.begin():
            review = await session.scalar(
                select(DuplicateLeadReview)
                .where(DuplicateLeadReview.id == review_id)
                .with_for_update()
            )
            if review is None:
                raise DomainError("Проверка дубля не найдена")
            if review.review_status != "pending":
                raise DomainError("Этот дубль уже проверен")
            original = (
                await session.get(Lead, review.original_lead_id)
                if review.original_lead_id
                else await session.scalar(
                    select(Lead)
                    .where(Lead.phone == review.phone)
                    .order_by(Lead.application_at)
                    .limit(1)
                )
            )
            result_lead: Lead | None = original
            if resolution is DuplicateResolution.UPDATE_ORIGINAL:
                if original is None:
                    raise DomainError("Исходная заявка не найдена")
                telegram_owner = await session.scalar(
                    select(Lead.id).where(
                        Lead.telegram_id == review.telegram_id,
                        Lead.id != original.id,
                    )
                )
                if telegram_owner:
                    raise DomainError("Этот Telegram уже привязан к другой заявке")
                original.telegram_id = review.telegram_id
                original.telegram_username = review.telegram_username
                original.display_name = (
                    review.questionnaire_answers.get("full_name") or review.display_name
                )
                original.email = review.questionnaire_answers.get("email")
                original.questionnaire_answers = review.questionnaire_answers
                original.consent_at = review.consent_at
                original.first_click_at = review.first_click_at
            elif resolution is DuplicateResolution.SEPARATE_LEAD:
                if await session.scalar(
                    select(Lead.id).where(Lead.telegram_id == review.telegram_id)
                ):
                    raise DomainError("Для этого Telegram заявка уже существует")
                channel = await session.scalar(
                    select(Channel)
                    .join(Partner, Partner.id == Channel.partner_id)
                    .where(
                        Channel.referral_code == review.referral_code,
                        Channel.active.is_(True),
                        Partner.active.is_(True),
                    )
                )
                number = await session.scalar(text("SELECT nextval('lead_short_id_seq')"))
                if number is None:
                    raise RuntimeError("Не удалось получить номер заявки")
                eligible = is_eligible(review.questionnaire_answers)
                now = datetime.now(UTC)
                result_lead = Lead(
                    short_id=f"RKO-{number:04d}",
                    telegram_id=review.telegram_id,
                    telegram_username=review.telegram_username,
                    display_name=(
                        review.questionnaire_answers.get("full_name") or review.display_name
                    ),
                    phone=review.phone,
                    email=review.questionnaire_answers.get("email"),
                    consent_status=True,
                    consent_at=review.consent_at,
                    first_referral_code=review.referral_code,
                    proposed_partner_id=channel.partner_id if channel else None,
                    proposed_channel_id=channel.id if channel else None,
                    partner_id=channel.partner_id if channel else None,
                    channel_id=channel.id if channel else None,
                    assignment_status=(
                        AssignmentStatus.CONFIRMED if channel else AssignmentStatus.DIRECT
                    ),
                    assignment_confirmed_at=now if channel else None,
                    workflow_stage=(
                        LeadWorkflowStage.AWAITING_ADMIN
                        if eligible
                        else LeadWorkflowStage.NOT_ELIGIBLE
                    ),
                    internal_status=(
                        LeadInternalStatus.NEW if eligible else LeadInternalStatus.NOT_ELIGIBLE
                    ),
                    external_status=(
                        LeadExternalStatus.NEW
                        if eligible
                        else LeadExternalStatus.CLOSED_WITHOUT_RESULT
                    ),
                    questionnaire_answers=review.questionnaire_answers,
                    first_click_at=review.first_click_at,
                    application_at=now,
                )
                session.add(result_lead)
                await session.flush()
            review.review_status = "resolved"
            review.resolution = resolution
            review.resolved_by_user_id = actor_id
            review.resolved_at = datetime.now(UTC)
            return review, result_lead
