import asyncio
import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, func, select

from app.config import Settings
from app.database import Database
from app.models import DuplicateLeadReview, Lead, LeadDraft
from app.services.lead_intake import LeadIntakeService, SubmissionStatus

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL, reason="PostgreSQL integration database is absent"
)


@pytest.mark.asyncio
async def test_concurrent_same_phone_creates_lead_and_duplicate_review() -> None:
    database = Database(
        Settings(
            bot_token="123456:test-token",
            app_env="test",
            database_url=TEST_DATABASE_URL or "postgresql+asyncpg://unused",
        )
    )
    service = LeadIntakeService(database)
    now = datetime.now(UTC)
    try:
        async with database.session() as session, session.begin():
            await session.execute(delete(DuplicateLeadReview))
            await session.execute(delete(LeadDraft))
            await session.execute(delete(Lead))

        await asyncio.gather(
            service.record_first_click(telegram_id="10001", referral_code=None, clicked_at=now),
            service.record_first_click(telegram_id="10002", referral_code=None, clicked_at=now),
        )
        results = await asyncio.gather(
            service.submit(
                telegram_id="10001",
                telegram_username="first",
                display_name="Первый",
                phone="+79990000001",
                referral_code=None,
                first_click_at=now,
                consent_at=now,
                answers={"city": "Москва"},
            ),
            service.submit(
                telegram_id="10002",
                telegram_username="second",
                display_name="Второй",
                phone="+79990000001",
                referral_code=None,
                first_click_at=now,
                consent_at=now,
                answers={"city": "Казань"},
            ),
        )

        assert {result.status for result in results} == {
            SubmissionStatus.CREATED,
            SubmissionStatus.DUPLICATE_PHONE,
        }
        async with database.session() as session:
            assert await session.scalar(select(func.count()).select_from(Lead)) == 1
            assert await session.scalar(select(func.count()).select_from(DuplicateLeadReview)) == 1
    finally:
        await database.close()
