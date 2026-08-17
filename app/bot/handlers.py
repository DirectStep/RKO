from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.bot.texts import START_TEXT

router = Router(name="common")


@router.message(CommandStart())
async def start(message: Message) -> None:
    await message.answer(START_TEXT)
