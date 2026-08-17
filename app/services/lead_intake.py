from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import cast

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Database
from app.domain.enums import AssignmentStatus
from app.models import Channel, DuplicateLeadReview, Lead, LeadDraft


class SubmissionStatus(StrEnum):
    CREATED = "created"
    DUPLICATE_TELEGRAM = "duplicate_telegram"
    DUPLICATE_PHONE = "duplicate_phone"


@dataclass(frozen=True)
class SubmissionResult:
    status: SubmissionStatus
    short_id: str | None = None


@dataclass(frozen=True)
class FirstClick:
    referral_code: str | None
    first_click_at: datetime


class LeadIntakeService:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def record_first_click(
        self, *, telegram_id: str, referral_code: str | None, clicked_at: datetime
    ) -> FirstClick:
        async with self.database.session() as session, session.begin():
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                {"key": f"draft:{telegram_id}"},
            )
            draft = await session.scalar(
                select(LeadDraft).where(LeadDraft.telegram_id == telegram_id).with_for_update()
            )
            if draft:
                return FirstClick(draft.referral_code, draft.first_click_at)
            channel = await self._find_channel(session, referral_code)
            session.add(
                LeadDraft(
                    telegram_id=telegram_id,
                    referral_code=referral_code,
                    proposed_partner_id=channel.partner_id if channel else None,
                    proposed_channel_id=channel.id if channel else None,
                    first_click_at=clicked_at,
                )
            )
        return FirstClick(referral_code, clicked_at)

    async def submit(
        self,
        *,
        telegram_id: str,
        telegram_username: str | None,
        display_name: str,
        phone: str,
        referral_code: str | None,
        first_click_at: datetime,
        consent_at: datetime,
        answers: dict[str, str],
    ) -> SubmissionResult:
        async with self.database.session() as session, session.begin():
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
                {"key": f"telegram:{telegram_id}"},
            )
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"phone:{phone}"}
            )
            if await session.scalar(select(Lead.id).where(Lead.telegram_id == telegram_id)):
                return SubmissionResult(SubmissionStatus.DUPLICATE_TELEGRAM)
            if await session.scalar(select(Lead.id).where(Lead.phone == phone)):
                existing_review = await session.scalar(
                    select(DuplicateLeadReview.id).where(
                        DuplicateLeadReview.telegram_id == telegram_id
                    )
                )
                if not existing_review:
                    session.add(
                        DuplicateLeadReview(
                            telegram_id=telegram_id,
                            telegram_username=telegram_username,
                            display_name=display_name,
                            phone=phone,
                            referral_code=referral_code,
                            questionnaire_answers=answers,
                            consent_at=consent_at,
                            first_click_at=first_click_at,
                        )
                    )
                return SubmissionResult(SubmissionStatus.DUPLICATE_PHONE)

            draft = await session.scalar(
                select(LeadDraft).where(LeadDraft.telegram_id == telegram_id).with_for_update()
            )
            channel = None
            if draft and draft.proposed_channel_id:
                channel = await session.get(Channel, draft.proposed_channel_id)
            elif draft is None and referral_code:
                channel = await self._find_channel(session, referral_code)
            number = await session.scalar(text("SELECT nextval('lead_short_id_seq')"))
            if number is None:
                raise RuntimeError("Не удалось получить номер заявки")
            short_id = f"RKO-{number:04d}"
            now = datetime.now(first_click_at.tzinfo)
            session.add(
                Lead(
                    short_id=short_id,
                    telegram_id=telegram_id,
                    telegram_username=telegram_username,
                    display_name=display_name,
                    phone=phone,
                    consent_status=True,
                    consent_at=consent_at,
                    first_referral_code=draft.referral_code if draft else referral_code,
                    proposed_partner_id=channel.partner_id if channel else None,
                    proposed_channel_id=channel.id if channel else None,
                    assignment_status=(
                        AssignmentStatus.PENDING if channel else AssignmentStatus.UNRESOLVED
                    ),
                    questionnaire_answers=answers,
                    first_click_at=first_click_at,
                    application_at=now,
                )
            )
            if draft:
                await session.delete(draft)
        return SubmissionResult(SubmissionStatus.CREATED, short_id)

    @staticmethod
    async def _find_channel(session: AsyncSession, referral_code: str | None) -> Channel | None:
        if not referral_code:
            return None
        return cast(
            Channel | None,
            await session.scalar(
                select(Channel).where(
                    Channel.referral_code == referral_code,
                    Channel.active.is_(True),
                )
            ),
        )
