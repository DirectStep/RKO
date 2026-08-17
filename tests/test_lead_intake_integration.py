import asyncio
import os
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select

from app.config import Settings
from app.database import Database
from app.domain.enums import AssignmentStatus, UserRole
from app.models import Channel, DuplicateLeadReview, Lead, LeadDraft, Partner, User
from app.services.admin_catalog import AdminCatalogService
from app.services.admin_dashboard import AdminDashboardService
from app.services.lead_assignment import LeadAssignmentService
from app.services.lead_intake import LeadIntakeService, SubmissionStatus
from app.services.sheets_snapshot import SheetsSnapshotService
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

        sheets = await SheetsSnapshotService(database).build()
        leads_sheet = next(sheet for sheet in sheets if sheet.title == "Заявки")
        assert len(leads_sheet.rows) == 1
        assert "questionnaire_answers" in leads_sheet.headers
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


@pytest.mark.asyncio
async def test_admin_creates_referral_channel_and_confirms_source() -> None:
    database = Database(
        Settings(
            bot_token="123456:test-token",
            app_env="test",
            database_url=TEST_DATABASE_URL or "postgresql+asyncpg://unused",
        )
    )
    suffix = uuid4().hex[:10]
    catalog = AdminCatalogService(database)
    assignments = LeadAssignmentService(database)
    partner_id = None
    channel_id = None
    lead_id = None
    try:
        partner = await catalog.create_partner(
            actor_role=UserRole.ADMIN,
            name=f"Тестовый партнёр {suffix}",
            commission_percent=Decimal("17.50"),
        )
        partner_id = partner.id
        channel = await catalog.create_channel(
            actor_role=UserRole.ADMIN,
            partner_id=partner.id,
            name="Telegram",
            bot_username="RKOrko_bot",
        )
        channel_id = channel.id
        assert channel.referral_link.startswith("https://t.me/RKOrko_bot?start=")

        now = datetime.now(UTC)
        async with database.session() as session, session.begin():
            lead = Lead(
                short_id=f"TEST-{suffix}",
                telegram_id=f"9{suffix}",
                display_name="Тест",
                phone=f"+7000{suffix}",
                consent_status=True,
                consent_at=now,
                first_referral_code=channel.referral_code,
                proposed_partner_id=partner.id,
                proposed_channel_id=channel.id,
                assignment_status=AssignmentStatus.PENDING,
                questionnaire_answers={"city": "Москва"},
                first_click_at=now,
                application_at=now,
            )
            session.add(lead)
            await session.flush()
            lead_id = lead.id

        confirmed = await assignments.confirm_proposed(actor_role=UserRole.ADMIN, lead_id=lead_id)
        assert confirmed.assignment_status is AssignmentStatus.CONFIRMED
        assert confirmed.partner_id == partner.id
        assert confirmed.channel_id == channel.id
        assert confirmed.assignment_confirmed_at is not None
        assert await AdminDashboardService(database).get_assignment_label(confirmed) == (
            f"Подтверждён: {partner.name} · {channel.name}"
        )
    finally:
        async with database.session() as session, session.begin():
            if lead_id is not None:
                await session.execute(delete(Lead).where(Lead.id == lead_id))
            if channel_id is not None:
                await session.execute(delete(Channel).where(Channel.id == channel_id))
            if partner_id is not None:
                await session.execute(delete(Partner).where(Partner.id == partner_id))
        await database.close()
