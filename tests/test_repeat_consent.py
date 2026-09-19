from datetime import UTC, datetime
from inspect import getsource
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.bot.handlers import decline_consent, resubmit_application
from app.bot.states import LeadApplication


class FakeSession:
    def __init__(self, previous: SimpleNamespace) -> None:
        self.previous = previous

    async def scalar(self, _query: object) -> SimpleNamespace:
        return self.previous


class FakeSessionContext:
    def __init__(self, previous: SimpleNamespace) -> None:
        self.session = FakeSession(previous)

    async def __aenter__(self) -> FakeSession:
        return self.session

    async def __aexit__(self, *_args: object) -> None:
        return None


class FakeDatabase:
    def __init__(self, previous: SimpleNamespace) -> None:
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

    await resubmit_application(callback, state, FakeDatabase(previous))

    state.clear.assert_awaited_once()
    state.update_data.assert_awaited_once()
    assert state.update_data.await_args.args[0]["consent_at"] == previous.consent_at.isoformat()
    state.set_state.assert_awaited_once_with(LeadApplication.phone)
    assert "Используем согласие" not in getsource(resubmit_application)


@pytest.mark.asyncio
async def test_repeat_application_requests_consent_when_previous_one_is_missing() -> None:
    previous = previous_application(consent_status=False)
    state = AsyncMock()

    await resubmit_application(repeat_callback(), state, FakeDatabase(previous))

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
    assert "нажмите «Согласен»" in message
    assert "/start" in message
