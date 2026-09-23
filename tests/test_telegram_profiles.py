import os
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app.config import Settings
from app.database import Database
from app.domain.enums import AccessStatus, AssignmentStatus, UserRole
from app.models import Lead, Partner, TelegramProfile, User
from app.services.telegram_profiles import observe_telegram_profile

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="PostgreSQL test DB is absent")


@pytest.mark.asyncio
async def test_lead_username_updates_history_once_and_notifies_only_active_application() -> None:
    database = Database(
        Settings(bot_token="123456:test", app_env="test", database_url=TEST_DATABASE_URL or "")
    )
    suffix = str(uuid4().int)[:10]
    telegram_id = f"8{suffix}"
    now = datetime.now(UTC)
    bot = SimpleNamespace(id=123456, send_message=AsyncMock())
    try:
        async with database.session() as session, session.begin():
            manager = User(
                telegram_id=f"1{suffix}", role=UserRole.MANAGER, access_status=AccessStatus.ACTIVE
            )
            admin = User(
                telegram_id=f"2{suffix}", role=UserRole.ADMIN, access_status=AccessStatus.ACTIVE
            )
            session.add_all([manager, admin])
            await session.flush()
            for index, archived in enumerate((True, False)):
                session.add(
                    Lead(
                        short_id=f"USR-{suffix}-{index}",
                        telegram_id=telegram_id,
                        telegram_username="old_user",
                        display_name="Тестовый лид",
                        phone=f"+790{suffix}{index}",
                        consent_status=True,
                        consent_at=now,
                        assignment_status=AssignmentStatus.DIRECT,
                        questionnaire_answers={},
                        first_click_at=now,
                        application_at=now + timedelta(seconds=index),
                        archived_at=now if archived else None,
                        manager_id=manager.id,
                        primary_admin_id=admin.id,
                    )
                )
        assert await observe_telegram_profile(database, (bot,), telegram_id, "new_user", now)
        assert not await observe_telegram_profile(
            database, (bot,), telegram_id, "new_user", now + timedelta(seconds=1)
        )
        assert not await observe_telegram_profile(
            database, (bot,), telegram_id, "old_user", now - timedelta(seconds=1)
        )
        async with database.session() as session:
            leads = list(await session.scalars(select(Lead).where(Lead.telegram_id == telegram_id)))
            assert {lead.telegram_username for lead in leads} == {"new_user"}
        assert bot.send_message.await_count == 2
        assert all("USR-" in call.args[1] for call in bot.send_message.await_args_list)
        assert await observe_telegram_profile(
            database, (bot,), telegram_id, None, now + timedelta(seconds=2)
        )
        assert bot.send_message.await_count == 4
    finally:
        async with database.session() as session, session.begin():
            await session.execute(delete(Lead).where(Lead.telegram_id == telegram_id))
            await session.execute(
                delete(TelegramProfile).where(TelegramProfile.telegram_id == telegram_id)
            )
            await session.execute(
                delete(User).where(User.telegram_id.in_([f"1{suffix}", f"2{suffix}"]))
            )
        await database.close()


@pytest.mark.asyncio
async def test_partner_username_only_notifies_assigned_admin() -> None:
    database = Database(
        Settings(bot_token="123456:test", app_env="test", database_url=TEST_DATABASE_URL or "")
    )
    suffix = str(uuid4().int)[:10]
    telegram_id = f"7{suffix}"
    bot = SimpleNamespace(id=123456, send_message=AsyncMock())
    try:
        async with database.session() as session, session.begin():
            admin = User(
                telegram_id=f"3{suffix}", role=UserRole.ADMIN, access_status=AccessStatus.ACTIVE
            )
            other_admin = User(
                telegram_id=f"4{suffix}", role=UserRole.ADMIN, access_status=AccessStatus.ACTIVE
            )
            partner_user = User(
                telegram_id=telegram_id,
                telegram_username="old_partner",
                role=UserRole.PARTNER,
                access_status=AccessStatus.ACTIVE,
            )
            session.add_all([admin, other_admin, partner_user])
            await session.flush()
            session.add(
                Partner(
                    name=f"Партнёр {suffix}",
                    telegram_username="old_partner",
                    telegram_user_id=partner_user.id,
                    assigned_manager_id=admin.id,
                    commission_percent=20,
                    active=True,
                )
            )
            now = datetime.now(UTC)
            session.add(
                Lead(
                    short_id=f"MIX-{suffix}",
                    telegram_id=telegram_id,
                    telegram_username="old_partner",
                    display_name="Партнёр как лид",
                    phone=f"+788{suffix}",
                    consent_status=True,
                    consent_at=now,
                    assignment_status=AssignmentStatus.DIRECT,
                    questionnaire_answers={},
                    first_click_at=now,
                    application_at=now,
                    primary_admin_id=other_admin.id,
                )
            )
        assert await observe_telegram_profile(
            database, (bot,), telegram_id, "new_partner", datetime.now(UTC)
        )
        assert bot.send_message.await_count == 2
        assert {call.args[0] for call in bot.send_message.await_args_list} == {
            int(admin.telegram_id),
            int(other_admin.telegram_id),
        }
        async with database.session() as session:
            partner = await session.scalar(
                select(Partner).where(Partner.telegram_user_id == partner_user.id)
            )
            assert partner.telegram_username == "new_partner"
    finally:
        async with database.session() as session, session.begin():
            await session.execute(delete(Lead).where(Lead.telegram_id == telegram_id))
            await session.execute(delete(Partner).where(Partner.name == f"Партнёр {suffix}"))
            await session.execute(
                delete(TelegramProfile).where(TelegramProfile.telegram_id == telegram_id)
            )
            await session.execute(
                delete(User).where(User.telegram_id.in_([telegram_id, f"3{suffix}", f"4{suffix}"]))
            )
        await database.close()
