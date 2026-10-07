from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.bot.texts import manager_changed_message
from app.config import Settings
from app.domain.enums import AccessStatus, LeadInternalStatus, UserRole
from app.web import MiniAppUser, create_web_app


@pytest.mark.parametrize(
    "case", ["changed", "same", "removed", "before_selection", "archived", "comment"]
)
async def test_manager_reassignment_notifications(monkeypatch, case) -> None:
    manager_id, lead_id = uuid4(), uuid4()
    if case == "removed":
        manager_id = None
    lead = SimpleNamespace(
        id=lead_id,
        manager_id=manager_id,
        bank_selection_submitted_at=None if case == "before_selection" else datetime.now(UTC),
        archived_at=datetime.now(UTC) if case == "archived" else None,
        short_id="RKO-TEST",
        is_repeat=False,
        display_name="Тестовый клиент",
        telegram_username="client",
        phone="+79990000000",
        email="test@example.com",
        street_address="Тестовая улица, 1",
        inn_draft="123456789012",
        internal_status=LeadInternalStatus.DATA_RECEIVED,
        external_status=SimpleNamespace(value="in_progress"),
        assignment_status=SimpleNamespace(value="direct"),
        questionnaire_answers={"city": "Москва", "has_ip": "yes"},
    )
    manager = SimpleNamespace(
        id=manager_id,
        telegram_id="200",
        telegram_username="new_manager",
        access_status=AccessStatus.ACTIVE,
    )
    session = SimpleNamespace(
        scalar=AsyncMock(return_value="100"),
        get=AsyncMock(return_value=manager),
        scalars=AsyncMock(return_value=["Банк А", "Банк Б"]),
    )

    @asynccontextmanager
    async def database_session():
        yield session

    database = SimpleNamespace(session=database_session)
    update = AsyncMock(
        return_value=(lead, case in {"changed", "removed", "before_selection", "archived"})
    )
    monkeypatch.setattr("app.web.WorkflowService.update_lead", update)
    bots = [SimpleNamespace(id=index, send_message=AsyncMock()) for index in (1, 2)]
    app = create_web_app(
        database=database, settings=Settings(), bot=bots[0], additional_bots=(bots[1],)
    )
    route = next(
        route
        for route in app.routes
        if getattr(route, "path", "") == "/api/leads/{lead_id}" and "PATCH" in route.methods
    )
    app.dependency_overrides[route.dependant.dependencies[0].call] = lambda: MiniAppUser(
        id="300",
        database_id=uuid4(),
        name="Админ",
        role=UserRole.ADMIN,
    )
    payload = {"update_manager": True, "manager_id": str(manager_id) if manager_id else None}
    if case == "comment":
        payload = {"update_comment": True, "internal_comment": "Комментарий"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.patch(f"/api/leads/{lead_id}", json=payload)
    assert response.status_code == 200
    for bot in bots:
        if case != "changed":
            bot.send_message.assert_not_awaited()
            continue
        assert bot.send_message.await_count == 2
        manager_call, client_call = bot.send_message.await_args_list
        assert manager_call.kwargs["chat_id"] == 200
        for value in (
            "RKO-TEST",
            "Тестовый клиент",
            "+79990000000",
            "@client",
            "Москва",
            "test@example.com",
            "Тестовая улица, 1",
            "123456789012",
            "Банк А",
            "Банк Б",
        ):
            assert value in manager_call.kwargs["text"]
        assert manager_call.kwargs["reply_markup"] is not None
        assert client_call.kwargs == {
            "chat_id": 100,
            "text": manager_changed_message("@new_manager"),
            "parse_mode": "HTML",
        }


def test_manager_changed_name_is_escaped() -> None:
    assert "&lt;имя&gt; &amp;" in manager_changed_message("<имя> &")


async def test_manager_change_is_detected_under_row_lock() -> None:
    from app.services.workflow import WorkflowService

    target_id = uuid4()
    lead = SimpleNamespace(
        manager_id=uuid4(),
        manager_started_at=datetime.now(UTC),
        internal_status=LeadInternalStatus.DATA_RECEIVED,
    )
    manager = SimpleNamespace(role=UserRole.MANAGER, access_status=AccessStatus.ACTIVE)
    statements = []

    async def read_lead(statement):
        statements.append(statement)
        return lead

    @asynccontextmanager
    async def transaction():
        yield

    session = SimpleNamespace(
        scalar=read_lead, get=AsyncMock(return_value=manager), begin=transaction
    )

    @asynccontextmanager
    async def database_session():
        yield session

    service = WorkflowService(SimpleNamespace(session=database_session))
    _, first_change = await service.update_lead(
        actor_role=UserRole.ADMIN, lead_id=uuid4(), manager_id=target_id, update_manager=True
    )
    _, second_change = await service.update_lead(
        actor_role=UserRole.ADMIN, lead_id=uuid4(), manager_id=target_id, update_manager=True
    )
    assert first_change is True
    assert second_change is False
    assert all(statement._for_update_arg is not None for statement in statements)
