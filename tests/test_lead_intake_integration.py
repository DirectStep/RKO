import asyncio
import os
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, select

from app.config import Settings
from app.database import Database
from app.domain.enums import (
    AssignmentStatus,
    BankInternalStatus,
    LeadInternalStatus,
    LeadWorkflowStage,
    PaymentStatus,
    UserRole,
)
from app.domain.operations import DomainError
from app.models import (
    Bank,
    Channel,
    DuplicateLeadReview,
    Lead,
    LeadBank,
    LeadDraft,
    Partner,
    Payment,
    User,
)
from app.reports.partner_report import build_partner_report
from app.services.admin_catalog import AdminCatalogService
from app.services.admin_dashboard import AdminDashboardService
from app.services.lead_assignment import LeadAssignmentService
from app.services.lead_intake import LeadIntakeService, SubmissionStatus
from app.services.lead_workflow import LeadWorkflowService
from app.services.sheets_snapshot import SheetsSnapshotService
from app.services.user_access import UserAccessService
from app.services.workflow import WorkflowService

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
            direct_lead = await session.scalar(select(Lead))
            assert direct_lead is not None
            assert direct_lead.assignment_status is AssignmentStatus.DIRECT

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
async def test_staff_invite_is_claimed_by_username_without_telegram_id() -> None:
    settings = Settings(
        bot_token="123456:test-token",
        app_env="test",
        database_url=TEST_DATABASE_URL or "postgresql+asyncpg://unused",
    )
    database = Database(settings)
    suffix = str(uuid4().int)[:10]
    username = f"manager_{suffix}"
    telegram_id = f"74{suffix}"
    invited_user_id = None
    try:
        invited = await WorkflowService(database).create_staff(
            actor_role=UserRole.ADMIN,
            telegram_username=f"@{username}",
            role=UserRole.MANAGER,
        )
        invited_user_id = invited.id
        assert invited.telegram_id is None

        role = await UserAccessService(database, settings).resolve_role(
            telegram_id, username.upper()
        )

        assert role is UserRole.MANAGER
        async with database.session() as session:
            claimed = await session.get(User, invited.id)
            assert claimed is not None
            assert claimed.telegram_id == telegram_id
    finally:
        async with database.session() as session, session.begin():
            if invited_user_id is not None:
                await session.execute(delete(User).where(User.id == invited_user_id))
        await database.close()


@pytest.mark.asyncio
async def test_partner_cannot_submit_lead_application() -> None:
    database = Database(
        Settings(
            bot_token="123456:test-token",
            app_env="test",
            database_url=TEST_DATABASE_URL or "postgresql+asyncpg://unused",
        )
    )
    suffix = str(uuid4().int)[:10]
    telegram_id = f"75{suffix}"
    phone = f"+7222{suffix}"
    now = datetime.now(UTC)
    try:
        async with database.session() as session, session.begin():
            session.add(
                User(
                    telegram_id=telegram_id,
                    telegram_username=f"partner_{suffix}",
                    role=UserRole.PARTNER,
                )
            )

        with pytest.raises(DomainError, match="Партнёрский аккаунт"):
            await LeadIntakeService(database).submit(
                telegram_id=telegram_id,
                telegram_username=f"partner_{suffix}",
                display_name="Партнёр",
                phone=phone,
                referral_code=None,
                first_click_at=now,
                consent_at=now,
                answers={"adult": "yes"},
            )

        async with database.session() as session:
            assert await session.scalar(
                select(Lead.id).where(Lead.telegram_id == telegram_id)
            ) is None
    finally:
        async with database.session() as session, session.begin():
            await session.execute(delete(User).where(User.telegram_id == telegram_id))
        await database.close()


@pytest.mark.asyncio
async def test_two_stage_lead_claim_and_bank_selection() -> None:
    database = Database(
        Settings(
            bot_token="123456:test-token",
            app_env="test",
            database_url=TEST_DATABASE_URL or "postgresql+asyncpg://unused",
        )
    )
    suffix = str(uuid4().int)[:10]
    now = datetime.now(UTC)
    lead_id = admin_id = manager_id = bank_id = None
    try:
        async with database.session() as session, session.begin():
            admin = User(
                telegram_id=f"81{suffix}",
                telegram_username=f"admin_{suffix}",
                role=UserRole.ADMIN,
            )
            manager = User(
                telegram_id=f"82{suffix}",
                telegram_username=f"manager_{suffix}",
                role=UserRole.MANAGER,
            )
            session.add_all([admin, manager])
            await session.flush()
            admin_id, manager_id = admin.id, manager.id

        result = await LeadIntakeService(database).submit(
            telegram_id=f"83{suffix}",
            telegram_username=f"lead_{suffix}",
            display_name="Тестовый лид",
            phone=f"+7333{suffix}",
            referral_code=None,
            first_click_at=now,
            consent_at=now,
            answers={
                "adult": "yes",
                "has_bankruptcy_or_arrests": "no",
                "is_civil_servant": "no",
                "full_name": "Иванов Иван Иванович",
                "email": f"lead{suffix}@example.com",
            },
        )
        assert result.eligible is True
        async with database.session() as session:
            lead = await session.scalar(
                select(Lead).where(Lead.telegram_id == f"83{suffix}")
            )
            assert lead is not None
            lead_id = lead.id
            assert lead.workflow_stage is LeadWorkflowStage.AWAITING_ADMIN

        workflow = LeadWorkflowService(database)
        await workflow.claim_by_admin(
            actor_role=UserRole.ADMIN, actor_id=admin_id, lead_id=lead_id
        )
        bank = await WorkflowService(database).create_bank(
            actor_role=UserRole.ADMIN, name=f"Банк {suffix}"
        )
        bank_id = bank.id
        await WorkflowService(database).add_bank_to_lead(
            actor_role=UserRole.ADMIN,
            actor_user_id=admin_id,
            lead_id=lead_id,
            bank_id=bank_id,
        )
        await workflow.publish_banks(
            actor_role=UserRole.ADMIN, actor_id=admin_id, lead_id=lead_id
        )
        await workflow.submit_bank_selection(
            lead_id=lead_id, selected_bank_ids={bank_id}
        )
        lead = await workflow.claim_by_manager(
            actor_role=UserRole.MANAGER,
            actor_id=manager_id,
            lead_id=lead_id,
        )

        assert lead.workflow_stage is LeadWorkflowStage.MANAGER_PROCESSING
        assert lead.primary_admin_id == admin_id
        assert lead.manager_id == manager_id
    finally:
        async with database.session() as session, session.begin():
            if lead_id is not None:
                await session.execute(delete(LeadBank).where(LeadBank.lead_id == lead_id))
                await session.execute(delete(Lead).where(Lead.id == lead_id))
            if bank_id is not None:
                await session.execute(delete(Bank).where(Bank.id == bank_id))
            user_ids = [value for value in (admin_id, manager_id) if value is not None]
            if user_ids:
                await session.execute(delete(User).where(User.id.in_(user_ids)))
        await database.close()


@pytest.mark.asyncio
async def test_partner_username_is_claimed_by_first_telegram_account() -> None:
    settings = Settings(
        bot_token="123456:test-token",
        app_env="test",
        database_url=TEST_DATABASE_URL or "postgresql+asyncpg://unused",
    )
    database = Database(settings)
    suffix = str(uuid4().int)[:10]
    username = f"partner_{suffix}"
    telegram_id = f"76{suffix}"
    partner_id = None
    user_id = None
    try:
        partner = await AdminCatalogService(database).create_partner(
            actor_role=UserRole.ADMIN,
            name=f"Партнёр username {suffix}",
            commission_percent=Decimal("10"),
            telegram_username=username,
        )
        partner_id = partner.id

        role = await UserAccessService(database, settings).resolve_role(
            telegram_id, username.upper()
        )

        assert role is UserRole.PARTNER
        async with database.session() as session:
            linked_partner = await session.get(Partner, partner_id)
            user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
            assert linked_partner is not None
            assert user is not None
            assert linked_partner.telegram_user_id == user.id
            user_id = user.id
    finally:
        async with database.session() as session, session.begin():
            if partner_id is not None:
                await session.execute(delete(Partner).where(Partner.id == partner_id))
            if user_id is not None:
                await session.execute(delete(User).where(User.id == user_id))
        await database.close()


@pytest.mark.asyncio
async def test_partner_activation_link_works_only_once() -> None:
    settings = Settings(
        bot_token="123456:test-token",
        app_env="test",
        database_url=TEST_DATABASE_URL or "postgresql+asyncpg://unused",
    )
    database = Database(settings)
    suffix = str(uuid4().int)[:10]
    telegram_id = f"77{suffix}"
    partner_id = None
    user_id = None
    try:
        catalog = AdminCatalogService(database)
        partner = await catalog.create_partner(
            actor_role=UserRole.ADMIN,
            name=f"Партнёр activation {suffix}",
            commission_percent=Decimal("10"),
        )
        partner_id = partner.id
        link = await catalog.create_partner_activation_link(
            actor_role=UserRole.ADMIN,
            partner_id=partner.id,
            bot_username="RKOrko_bot",
        )
        token = link.split("partner_", maxsplit=1)[1]

        activated = await WorkflowService(database).activate_partner_with_token(
            telegram_id=telegram_id,
            telegram_username=f"activated_{suffix}",
            token=token,
        )
        user_id = activated.telegram_user_id
        assert user_id is not None
        assert activated.activation_token_hash is None

        with pytest.raises(DomainError, match="уже использована"):
            await WorkflowService(database).activate_partner_with_token(
                telegram_id=f"78{suffix}",
                telegram_username=f"second_{suffix}",
                token=token,
            )
    finally:
        async with database.session() as session, session.begin():
            if partner_id is not None:
                await session.execute(delete(Partner).where(Partner.id == partner_id))
            if user_id is not None:
                await session.execute(delete(User).where(User.id == user_id))
        await database.close()


@pytest.mark.asyncio
async def test_invited_admin_username_is_claimed_by_first_telegram_account() -> None:
    suffix = str(uuid4().int)[:10]
    username = f"invited_{suffix}"
    settings = Settings(
        bot_token="123456:test-token",
        app_env="test",
        database_url=TEST_DATABASE_URL or "postgresql+asyncpg://unused",
        admin_telegram_usernames=username,
    )
    database = Database(settings)
    first_id = f"81{suffix}"
    second_id = f"82{suffix}"
    try:
        role = await UserAccessService(database, settings).resolve_role(first_id, username)
        repeated_role = await UserAccessService(database, settings).resolve_role(
            first_id, username
        )
        rejected_role = await UserAccessService(database, settings).resolve_role(
            second_id, username
        )

        assert role is UserRole.ADMIN
        assert repeated_role is UserRole.ADMIN
        assert rejected_role is None
    finally:
        async with database.session() as session, session.begin():
            await session.execute(delete(User).where(User.telegram_id.in_({first_id, second_id})))
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
    suffix = str(uuid4().int)[:10]
    catalog = AdminCatalogService(database)
    assignments = LeadAssignmentService(database)
    partner_id = None
    channel_id = None
    lead_id = None
    auto_lead_id = None
    referral_test_ids = {f"ref-{suffix}", f"invalid-{suffix}"}
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
        first_click = await LeadIntakeService(database).record_first_click(
            telegram_id=f"ref-{suffix}",
            referral_code=channel.referral_code,
            clicked_at=now,
        )
        repeated_click = await LeadIntakeService(database).record_first_click(
            telegram_id=f"ref-{suffix}",
            referral_code=None,
            clicked_at=now,
        )
        invalid_click = await LeadIntakeService(database).record_first_click(
            telegram_id=f"invalid-{suffix}",
            referral_code="missing-code",
            clicked_at=now,
        )
        assert first_click.referral_code == channel.referral_code
        assert first_click.partner_name == partner.name
        assert first_click.channel_name == channel.name
        assert first_click.is_new is True
        assert repeated_click.referral_code == channel.referral_code
        assert repeated_click.is_new is False
        assert invalid_click.referral_code is None

        result = await LeadIntakeService(database).submit(
            telegram_id=f"ref-{suffix}",
            telegram_username=f"ref_{suffix}",
            display_name="Лид по ссылке",
            phone=f"+7333{suffix}",
            referral_code=channel.referral_code,
            first_click_at=now,
            consent_at=now,
            answers={"city": "Москва"},
        )
        assert result.status is SubmissionStatus.CREATED
        async with database.session() as session:
            auto_lead = await session.scalar(
                select(Lead).where(Lead.telegram_id == f"ref-{suffix}")
            )
            assert auto_lead is not None
            assert auto_lead.assignment_status is AssignmentStatus.CONFIRMED
            assert auto_lead.partner_id == partner.id
            assert auto_lead.channel_id == channel.id
            assert auto_lead.assignment_confirmed_at is not None
            auto_lead_id = auto_lead.id

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

        with pytest.raises(DomainError, match="с заявками удалить нельзя"):
            await catalog.delete_partner(actor_role=UserRole.ADMIN, partner_id=partner.id)

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
            if auto_lead_id is not None:
                await session.execute(delete(Lead).where(Lead.id == auto_lead_id))
            await session.execute(
                delete(LeadDraft).where(LeadDraft.telegram_id.in_(referral_test_ids))
            )
            if channel_id is not None:
                await session.execute(delete(Channel).where(Channel.id == channel_id))
            if partner_id is not None:
                await session.execute(delete(Partner).where(Partner.id == partner_id))
        await database.close()


@pytest.mark.asyncio
async def test_partner_creates_channel_only_for_own_cabinet() -> None:
    settings = Settings(
        bot_token="123456:test-token",
        app_env="test",
        database_url=TEST_DATABASE_URL or "postgresql+asyncpg://unused",
    )
    database = Database(settings)
    suffix = str(uuid4().int)[:10]
    partner_ids: list[UUID] = []
    channel_id = None
    try:
        catalog = AdminCatalogService(database)
        owner = await catalog.create_partner(
            actor_role=UserRole.ADMIN,
            name=f"Владелец канала {suffix}",
            commission_percent=Decimal("10"),
        )
        stranger = await catalog.create_partner(
            actor_role=UserRole.ADMIN,
            name=f"Чужой партнёр {suffix}",
            commission_percent=Decimal("10"),
        )
        partner_ids.extend([owner.id, stranger.id])

        channel = await catalog.create_channel(
            actor_role=UserRole.PARTNER,
            actor_partner_id=owner.id,
            partner_id=owner.id,
            name="Собственный источник",
            bot_username="RKOrko_bot",
        )
        channel_id = channel.id
        assert channel.partner_id == owner.id
        assert channel.referral_link.startswith("https://t.me/RKOrko_bot?start=")

        with pytest.raises(DomainError, match="только своему"):
            await catalog.create_channel(
                actor_role=UserRole.PARTNER,
                actor_partner_id=owner.id,
                partner_id=stranger.id,
                name="Чужой источник",
                bot_username="RKOrko_bot",
            )
    finally:
        async with database.session() as session, session.begin():
            if channel_id is not None:
                await session.execute(delete(Channel).where(Channel.id == channel_id))
            if partner_ids:
                await session.execute(delete(Partner).where(Partner.id.in_(partner_ids)))
        await database.close()


@pytest.mark.asyncio
async def test_admin_deletes_unused_partner_and_its_channels() -> None:
    database = Database(
        Settings(
            bot_token="123456:test-token",
            app_env="test",
            database_url=TEST_DATABASE_URL or "postgresql+asyncpg://unused",
        )
    )
    suffix = str(uuid4().int)[:10]
    catalog = AdminCatalogService(database)
    partner_id = None
    channel_id = None
    try:
        partner = await catalog.create_partner(
            actor_role=UserRole.ADMIN,
            name=f"Удаляемый партнёр {suffix}",
            commission_percent=Decimal("10"),
        )
        partner_id = partner.id
        channel = await catalog.create_channel(
            actor_role=UserRole.ADMIN,
            partner_id=partner.id,
            name="Тестовый канал",
            bot_username="RKOrko_bot",
        )
        channel_id = channel.id

        updated = await catalog.update_partner_commission(
            actor_role=UserRole.ADMIN,
            partner_id=partner.id,
            commission_percent=Decimal("12.50"),
        )
        assert updated.commission_percent == Decimal("12.50")
        updated = await catalog.update_partner_username(
            actor_role=UserRole.ADMIN,
            partner_id=partner.id,
            telegram_username=f"updated_{suffix}",
        )
        assert updated.telegram_username == f"updated_{suffix}"

        await catalog.delete_partner(actor_role=UserRole.ADMIN, partner_id=partner.id)

        async with database.session() as session:
            assert await session.get(Partner, partner.id) is None
            assert await session.get(Channel, channel.id) is None
    finally:
        async with database.session() as session, session.begin():
            if channel_id is not None:
                await session.execute(delete(Channel).where(Channel.id == channel_id))
            if partner_id is not None:
                await session.execute(delete(Partner).where(Partner.id == partner_id))
        await database.close()


@pytest.mark.asyncio
async def test_full_local_workflow_from_manager_to_paid_partner() -> None:
    database = Database(
        Settings(
            bot_token="123456:test-token",
            app_env="test",
            database_url=TEST_DATABASE_URL or "postgresql+asyncpg://unused",
        )
    )
    suffix = str(uuid4().int)[:10]
    workflow = WorkflowService(database)
    catalog = AdminCatalogService(database)
    ids: dict[str, object] = {}
    try:
        manager = await workflow.create_staff(
            actor_role=UserRole.ADMIN,
            telegram_id=f"8{suffix}",
            telegram_username=f"manager_{suffix}",
            role=UserRole.MANAGER,
        )
        ids["manager"] = manager.id
        partner = await catalog.create_partner(
            actor_role=UserRole.ADMIN,
            name=f"Партнёр workflow {suffix}",
            commission_percent=Decimal("20.00"),
            telegram_username=f"partner_{suffix}",
        )
        assert partner.telegram_username == f"partner_{suffix}"
        ids["partner"] = partner.id
        partner = await workflow.bind_partner_access(
            actor_role=UserRole.ADMIN,
            partner_id=partner.id,
            telegram_id=f"7{suffix}",
            telegram_username=f"partner_{suffix}",
        )
        ids["partner_user"] = partner.telegram_user_id
        channel = await catalog.create_channel(
            actor_role=UserRole.ADMIN,
            partner_id=partner.id,
            name="Основной канал",
            bot_username="RKOrko_bot",
        )
        ids["channel"] = channel.id
        bank = await workflow.create_bank(
            actor_role=UserRole.ADMIN,
            name=f"Банк workflow {suffix}",
            display_order=1,
        )
        ids["bank"] = bank.id

        now = datetime.now(UTC)
        async with database.session() as session, session.begin():
            lead = Lead(
                short_id=f"FLOW-{suffix}",
                telegram_id=f"6{suffix}",
                display_name="Рабочий лид",
                phone=f"+7111{suffix}",
                consent_status=True,
                consent_at=now,
                proposed_partner_id=partner.id,
                proposed_channel_id=channel.id,
                partner_id=partner.id,
                channel_id=channel.id,
                assignment_status=AssignmentStatus.CONFIRMED,
                assignment_confirmed_at=now,
                questionnaire_answers={"city": "Москва"},
                first_click_at=now,
                application_at=now,
            )
            session.add(lead)
            await session.flush()
            ids["lead"] = lead.id

        lead = await workflow.update_lead(
            actor_role=UserRole.ADMIN,
            lead_id=ids["lead"],
            manager_id=manager.id,
            update_manager=True,
            internal_comment="Первичный контакт",
            update_comment=True,
        )
        assert lead.manager_id == manager.id
        assert lead.internal_status is LeadInternalStatus.MANAGER_ASSIGNED

        lead_bank = await workflow.add_bank_to_lead(
            actor_role=UserRole.MANAGER,
            lead_id=lead.id,
            bank_id=bank.id,
        )
        ids["lead_bank"] = lead_bank.id
        lead_bank = await workflow.update_lead_bank(
            actor_role=UserRole.MANAGER,
            lead_bank_id=lead_bank.id,
            status=BankInternalStatus.ACCOUNT_OPENED,
            income_estimate=Decimal("12000.00"),
            income_fact=Decimal("10000.00"),
        )
        assert lead_bank.partner_reward_estimate == Decimal("2400.00")
        assert lead_bank.partner_reward_fact == Decimal("2000.00")
        assert lead_bank.opened_at is not None

        payment = await workflow.confirm_lead_bank_payment(
            actor_role=UserRole.ADMIN,
            actor_user_id=manager.id,
            lead_bank_id=lead_bank.id,
            payment_period="2026-08",
            registry_number="REG-1",
        )
        ids["payment"] = payment.id
        assert payment.status is PaymentStatus.CONFIRMED
        payment = await workflow.change_payment_status(
            actor_role=UserRole.ADMIN,
            payment_id=payment.id,
            new_status=PaymentStatus.IN_REGISTRY,
            registry_number="REG-1",
        )
        payment = await workflow.change_payment_status(
            actor_role=UserRole.ADMIN,
            payment_id=payment.id,
            new_status=PaymentStatus.PAID,
            paid_at=date(2026, 8, 17),
        )
        assert payment.status is PaymentStatus.PAID
        report = (await build_partner_report(database, ids["partner"])).decode("utf-8-sig")
        assert lead.short_id in report
        assert "2000.00" in report
        assert lead.phone not in report
        assert "10000.00" not in report
        assert "Первичный контакт" not in report
        with pytest.raises(DomainError, match="удалить нельзя"):
            await workflow.delete_lead(actor_role=UserRole.ADMIN, lead_id=lead.id)
    finally:
        async with database.session() as session, session.begin():
            if "payment" in ids:
                await session.execute(delete(Payment).where(Payment.id == ids["payment"]))
            if "lead_bank" in ids:
                await session.execute(delete(LeadBank).where(LeadBank.id == ids["lead_bank"]))
            if "lead" in ids:
                await session.execute(delete(Lead).where(Lead.id == ids["lead"]))
            if "channel" in ids:
                await session.execute(delete(Channel).where(Channel.id == ids["channel"]))
            if "partner" in ids:
                await session.execute(delete(Partner).where(Partner.id == ids["partner"]))
            if "bank" in ids:
                await session.execute(delete(Bank).where(Bank.id == ids["bank"]))
            user_ids = [ids[key] for key in ("manager", "partner_user") if ids.get(key)]
            if user_ids:
                await session.execute(delete(User).where(User.id.in_(user_ids)))
        await database.close()
