import asyncio
import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, func, select

from app.config import Settings
from app.database import Database
from app.domain.enums import UserRole
from app.models import DuplicateLeadReview, Lead, LeadDraft, User
from app.services.lead_intake import LeadIntakeService, SubmissionStatus
from app.services.user_access import UserAccessService

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


@pytest.mark.asyncio
async def test_configured_admin_is_created_and_resolved() -> None:
    settings = Settings(
        bot_token="123456:test-token",
        app_env="test",
        database_url=TEST_DATABASE_URL or "postgresql+asyncpg://unused",
        admin_telegram_ids="99001",
    )
    database = Database(settings)
    try:
        async with database.session() as session, session.begin():
            await session.execute(delete(User).where(User.telegram_id == "99001"))

        role = await UserAccessService(database, settings).resolve_role(
            telegram_id="99001", telegram_username="admin"
        )

        assert role is UserRole.ADMIN
        async with database.session() as session:
            user = await session.scalar(select(User).where(User.telegram_id == "99001"))
            assert user is not None
            assert user.role is UserRole.ADMIN
    finally:
        await database.close()
