from datetime import UTC, datetime
from inspect import getsource
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.bot.handlers import accept_consent, decline_consent, resubmit_application
from app.bot.states import LeadApplication
from app.domain.enums import LeadWorkflowStage


class FakeSession:
    def __init__(self, previous: SimpleNamespace | None) -> None:
        self.previous = previous
        self.commit = AsyncMock()

    async def scalar(self, _query: object) -> SimpleNamespace | None:
        return self.previous

    async def get(self, _model: object, _id: object) -> SimpleNamespace | None:
        return self.previous


class FakeSessionContext:
    def __init__(self, previous: SimpleNamespace | None) -> None:
        self.session = FakeSession(previous)

    async def __aenter__(self) -> FakeSession:
        return self.session

    async def __aexit__(self, *_args: object) -> None:
        return None


class FakeDatabase:
    def __init__(self, previous: SimpleNamespace | None) -> None:
        self.previous = previous

    def session(self) -> FakeSessionContext:
        return FakeSessionContext(self.previous)


def repeat_callback() -> SimpleNamespace:
    return SimpleNamespace(
        from_user=SimpleNamespace(id=123, username="test_user", full_name="Тестовый Лид"),
        message=None,
        answer=AsyncMock(),
    )


def previous_application(*, consent_status: bool) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        first_referral_code="channel-code",
        first_click_at=datetime(2026, 8, 20, 10, tzinfo=UTC),
        consent_status=consent_status,
        consent_at=datetime(2026, 8, 20, 10, 5, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_repeat_application_reuses_existing_consent_and_requests_phone() -> None:
    previous = previous_application(consent_status=True)
    state = AsyncMock()
    callback = repeat_callback()

    await resubmit_application(
        callback,
        state,
        FakeDatabase(previous),
        SimpleNamespace(mini_app_url="https://app.example.test/"),
    )

    state.clear.assert_awaited_once()
    state.update_data.assert_awaited_once()
    assert state.update_data.await_args.args[0]["consent_at"] == previous.consent_at.isoformat()
    state.set_state.assert_awaited_once_with(LeadApplication.phone)
    assert "Используем согласие" not in getsource(resubmit_application)


@pytest.mark.asyncio
async def test_repeat_application_requests_consent_when_previous_one_is_missing() -> None:
    previous = previous_application(consent_status=False)
    state = AsyncMock()

    await resubmit_application(
        repeat_callback(),
        state,
        FakeDatabase(previous),
        SimpleNamespace(mini_app_url="https://app.example.test/"),
    )

    assert "consent_at" not in state.update_data.await_args.args[0]
    state.set_state.assert_awaited_once_with(LeadApplication.consent)


@pytest.mark.asyncio
async def test_declined_consent_keeps_old_accept_button_active() -> None:
    state = AsyncMock()
    callback = SimpleNamespace(
        message=SimpleNamespace(answer=AsyncMock()),
        answer=AsyncMock(),
    )

    await decline_consent(callback, state)

    state.clear.assert_not_awaited()
    message = callback.message.answer.await_args.args[0]
    assert "нажмите «Продолжить»" in message
    assert "/start" in message


@pytest.mark.asyncio
async def test_registered_lead_reaccepts_consent_and_opens_cabinet() -> None:
    lead = previous_application(consent_status=True)
    lead.telegram_id = "123"
    lead.archived_at = None
    lead.application_at = datetime(2026, 8, 20, 10, tzinfo=UTC)
    lead.workflow_stage = LeadWorkflowStage.ADMIN_PROCESSING
    state = AsyncMock()
    message = SimpleNamespace(edit_reply_markup=AsyncMock(), answer=AsyncMock())
    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=123),
        message=message,
        answer=AsyncMock(),
    )

    await accept_consent(
        callback,
        state,
        FakeDatabase(lead),
        SimpleNamespace(mini_app_url="https://app.example.test/"),
    )

    assert lead.consent_status is True
    assert lead.consent_at > datetime(2026, 8, 20, 10, 5, tzinfo=UTC)
    state.clear.assert_awaited_once()
    state.set_state.assert_not_awaited()
    message.edit_reply_markup.assert_awaited_once_with(reply_markup=None)
    assert "Кабинет клиента" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_new_lead_acceptance_continues_to_phone_collection() -> None:
    state = AsyncMock()
    message = SimpleNamespace(edit_reply_markup=AsyncMock(), answer=AsyncMock())
    callback = SimpleNamespace(
        from_user=SimpleNamespace(id=456),
        message=message,
        answer=AsyncMock(),
    )

    await accept_consent(
        callback,
        state,
        FakeDatabase(None),
        SimpleNamespace(mini_app_url="https://app.example.test/"),
    )

    state.set_state.assert_awaited_once_with(LeadApplication.phone)
    assert "Отправьте номер" in message.answer.await_args.args[0]
