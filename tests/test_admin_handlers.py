from types import SimpleNamespace

from aiogram.enums import MessageEntityType
from aiogram.types import MessageEntity

from app.bot.admin_handlers import extract_custom_emoji_ids


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
