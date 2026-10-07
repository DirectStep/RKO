from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from aiogram.enums import MessageEntityType
from aiogram.types import MessageEntity

from app.bot.admin_handlers import extract_custom_emoji_ids
from app.bot.admin_handlers import preview_client_messages
from app.bot.texts import (
    application_registered_message,
    bank_selection_confirmation,
    client_status_changed_message,
)


@pytest.mark.parametrize(
    ("admin", "chat_type", "count"),
    [(True, "private", 4), (False, "private", 1), (True, "supergroup", 1)],
)
async def test_preview_client_messages(monkeypatch, admin, chat_type, count) -> None:
    monkeypatch.setattr("app.bot.admin_handlers.is_admin", AsyncMock(return_value=admin))
    message = SimpleNamespace(
        from_user=SimpleNamespace(username="manager", full_name="Менеджер"),
        chat=SimpleNamespace(type=chat_type),
        answer=AsyncMock(),
    )
    await preview_client_messages(message, None, None)
    assert message.answer.await_count == count
    if count == 4:
        assert [call.args[0] for call in message.answer.await_args_list[1:]] == [
            application_registered_message("RKO-TEST"),
            bank_selection_confirmation("@manager"),
            client_status_changed_message("Выберите банки"),
        ]
        assert all(
            call.kwargs == {"parse_mode": "HTML"}
            for call in message.answer.await_args_list[1:]
        )


def test_extract_custom_emoji_ids_from_text_and_caption() -> None:
    text_emoji = MessageEntity(
        type=MessageEntityType.CUSTOM_EMOJI,
        offset=0,
        length=2,
        custom_emoji_id="text-emoji-id",
    )
    caption_emoji = MessageEntity(
        type=MessageEntityType.CUSTOM_EMOJI,
        offset=0,
        length=2,
        custom_emoji_id="caption-emoji-id",
    )
    bold = MessageEntity(type=MessageEntityType.BOLD, offset=2, length=4)
    message = SimpleNamespace(
        entities=[text_emoji, bold],
        caption_entities=[caption_emoji],
    )

    assert extract_custom_emoji_ids(message) == ["text-emoji-id", "caption-emoji-id"]


def test_extract_custom_emoji_ids_requires_replied_message() -> None:
    assert extract_custom_emoji_ids(None) == []
