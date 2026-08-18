from uuid import UUID

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from app.bot.admin_handlers import is_admin
from app.bot.keyboards import (
    admin_channel_keyboard,
    admin_channels_keyboard,
    admin_partner_choice_keyboard,
    admin_partner_delete_keyboard,
    admin_partner_keyboard,
    admin_partners_keyboard,
)
from app.bot.states import ChannelCreation, PartnerCreation
from app.config import Settings
from app.database import Database
from app.domain.enums import UserRole
from app.domain.operations import DomainError
from app.models import Partner
from app.services.admin_catalog import AdminCatalogService, ChannelSummary

router = Router(name="admin_catalog")


async def deny_if_not_admin(
    event: CallbackQuery | Message, database: Database, settings: Settings
) -> bool:
    if event.from_user is None or not await is_admin(event.from_user, database, settings):
        if isinstance(event, CallbackQuery):
            await event.answer("Нет доступа", show_alert=True)
        else:
            await event.answer("Этот раздел доступен только администратору.")
        return True
    return False


@router.callback_query(F.data == "admin:partners")
async def partners_list(
    callback: CallbackQuery, state: FSMContext, database: Database, settings: Settings
) -> None:
    if await deny_if_not_admin(callback, database, settings):
        return
    await state.clear()
    partners = await AdminCatalogService(database).list_partners()
    buttons = [(str(item.id), partner_button_text(item)) for item in partners]
    text = "Партнёры" if partners else "Партнёров пока нет."
    if isinstance(callback.message, Message):
        await callback.message.edit_text(text, reply_markup=admin_partners_keyboard(buttons))
    await callback.answer()


@router.callback_query(F.data == "admin:partner:new")
async def partner_new(
    callback: CallbackQuery, state: FSMContext, database: Database, settings: Settings
) -> None:
    if await deny_if_not_admin(callback, database, settings):
        return
    await state.set_state(PartnerCreation.name)
    if isinstance(callback.message, Message):
        await callback.message.answer("Как называется партнёр?")
    await callback.answer()


@router.message(PartnerCreation.name)
async def partner_name(
    message: Message, state: FSMContext, database: Database, settings: Settings
) -> None:
    if await deny_if_not_admin(message, database, settings):
        return
    name = (message.text or "").strip()
    if len(name) < 2 or len(name) > 160:
        await message.answer("Название должно быть от 2 до 160 символов.")
        return
    await state.update_data(partner_name=name)
    await state.set_state(PartnerCreation.commission)
    await message.answer("Какой процент получает партнёр? Например: 15")


@router.message(PartnerCreation.commission)
async def partner_commission(
    message: Message, state: FSMContext, database: Database, settings: Settings
) -> None:
    if await deny_if_not_admin(message, database, settings):
        return
    service = AdminCatalogService(database)
    try:
        commission = service.parse_commission(message.text or "")
        data = await state.get_data()
        partner = await service.create_partner(
            actor_role=UserRole.ADMIN,
            name=str(data["partner_name"]),
            commission_percent=commission,
        )
    except DomainError as error:
        await message.answer(str(error))
        return
    await state.clear()
    await message.answer(
        format_partner(partner, []),
        reply_markup=admin_partner_keyboard(str(partner.id), partner.active),
    )


@router.callback_query(F.data.startswith("admin:partner:toggle:"))
async def partner_toggle(callback: CallbackQuery, database: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, database, settings):
        return
    try:
        partner_id = UUID((callback.data or "").removeprefix("admin:partner:toggle:"))
        service = AdminCatalogService(database)
        partner = await service.toggle_partner(
            actor_role=UserRole.ADMIN, partner_id=partner_id
        )
        channels = await service.list_partner_channels(partner.id)
        access = await service.get_partner_access(partner.id)
    except (ValueError, DomainError) as error:
        await callback.answer(str(error), show_alert=True)
        return
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            format_partner(
                partner,
                channels,
                access.telegram_id if access else None,
                access.telegram_username if access else None,
            ),
            reply_markup=admin_partner_keyboard(
                str(partner.id),
                partner.active,
                [(item.channel.name, item.channel.referral_link) for item in channels],
            ),
        )
    await callback.answer("Статус изменён")


@router.callback_query(F.data.startswith("admin:pd:a:"))
async def partner_delete_ask(
    callback: CallbackQuery,
    database: Database,
    settings: Settings,
) -> None:
    if await deny_if_not_admin(callback, database, settings):
        return
    try:
        partner_id = UUID((callback.data or "").removeprefix("admin:pd:a:"))
    except ValueError:
        await callback.answer("Некорректный партнёр", show_alert=True)
        return
    partner = await AdminCatalogService(database).get_partner(partner_id)
    if partner is None:
        await callback.answer("Партнёр не найден", show_alert=True)
        return
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            f"Удалить партнёра «{partner.name}» и все его каналы?\n\n"
            "Если у партнёра есть заявки, удаление будет запрещено.",
            reply_markup=admin_partner_delete_keyboard(str(partner.id)),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:pd:c:"))
async def partner_delete_confirm(
    callback: CallbackQuery,
    database: Database,
    settings: Settings,
) -> None:
    if await deny_if_not_admin(callback, database, settings):
        return
    try:
        partner_id = UUID((callback.data or "").removeprefix("admin:pd:c:"))
        await AdminCatalogService(database).delete_partner(
            actor_role=UserRole.ADMIN,
            partner_id=partner_id,
        )
    except (ValueError, DomainError) as error:
        await callback.answer(str(error), show_alert=True)
        return
    partners = await AdminCatalogService(database).list_partners()
    buttons = [(str(item.id), partner_button_text(item)) for item in partners]
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            "Партнёр удалён." if not partners else "Партнёр удалён.\n\nПартнёры",
            reply_markup=admin_partners_keyboard(buttons),
        )
    await callback.answer("Партнёр удалён")


@router.callback_query(F.data.startswith("admin:partner:"))
async def partner_card(callback: CallbackQuery, database: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, database, settings):
        return
    try:
        partner_id = UUID((callback.data or "").removeprefix("admin:partner:"))
    except ValueError:
        await callback.answer("Некорректный партнёр", show_alert=True)
        return
    service = AdminCatalogService(database)
    partner = await service.get_partner(partner_id)
    if partner is None:
        await callback.answer("Партнёр не найден", show_alert=True)
        return
    channels = await service.list_partner_channels(partner.id)
    access = await service.get_partner_access(partner.id)
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            format_partner(
                partner,
                channels,
                access.telegram_id if access else None,
                access.telegram_username if access else None,
            ),
            reply_markup=admin_partner_keyboard(
                str(partner.id),
                partner.active,
                [(item.channel.name, item.channel.referral_link) for item in channels],
            ),
        )
    await callback.answer()


@router.callback_query(F.data == "admin:channels")
async def channels_list(
    callback: CallbackQuery, state: FSMContext, database: Database, settings: Settings
) -> None:
    if await deny_if_not_admin(callback, database, settings):
        return
    await state.clear()
    channels = await AdminCatalogService(database).list_channels()
    buttons = [(str(item.channel.id), channel_button_text(item)) for item in channels]
    text = "Каналы привлечения" if channels else "Каналов пока нет."
    if isinstance(callback.message, Message):
        await callback.message.edit_text(text, reply_markup=admin_channels_keyboard(buttons))
    await callback.answer()


@router.callback_query(F.data == "admin:channel:new")
async def channel_new(
    callback: CallbackQuery, state: FSMContext, database: Database, settings: Settings
) -> None:
    if await deny_if_not_admin(callback, database, settings):
        return
    partners = [item for item in await AdminCatalogService(database).list_partners() if item.active]
    if not partners:
        await callback.answer("Сначала создай активного партнёра", show_alert=True)
        return
    await state.set_state(ChannelCreation.partner)
    buttons = [(str(item.id), item.name) for item in partners]
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            "Для какого партнёра создать канал?",
            reply_markup=admin_partner_choice_keyboard(buttons),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("admin:channel:new:"))
async def channel_new_for_partner(
    callback: CallbackQuery, state: FSMContext, database: Database, settings: Settings
) -> None:
    if await deny_if_not_admin(callback, database, settings):
        return
    try:
        partner_id = UUID((callback.data or "").removeprefix("admin:channel:new:"))
    except ValueError:
        await callback.answer("Некорректный партнёр", show_alert=True)
        return
    await state.set_state(ChannelCreation.name)
    await state.update_data(channel_partner_id=str(partner_id))
    if isinstance(callback.message, Message):
        await callback.message.answer("Как назвать канал? Например: Telegram Ивана")
    await callback.answer()


@router.callback_query(ChannelCreation.partner, F.data.startswith("admin:channel:owner:"))
async def channel_owner(
    callback: CallbackQuery, state: FSMContext, database: Database, settings: Settings
) -> None:
    if await deny_if_not_admin(callback, database, settings):
        return
    try:
        partner_id = UUID((callback.data or "").removeprefix("admin:channel:owner:"))
    except ValueError:
        await callback.answer("Некорректный партнёр", show_alert=True)
        return
    await state.update_data(channel_partner_id=str(partner_id))
    await state.set_state(ChannelCreation.name)
    if isinstance(callback.message, Message):
        await callback.message.answer("Как назвать канал? Например: Telegram Ивана")
    await callback.answer()


@router.message(ChannelCreation.name)
async def channel_name(
    message: Message, state: FSMContext, database: Database, settings: Settings
) -> None:
    if await deny_if_not_admin(message, database, settings):
        return
    data = await state.get_data()
    try:
        partner_id = UUID(str(data["channel_partner_id"]))
        if message.bot is None:
            raise DomainError("Не удалось определить Telegram-бота")
        bot_user = await message.bot.get_me()
        channel = await AdminCatalogService(database).create_channel(
            actor_role=UserRole.ADMIN,
            partner_id=partner_id,
            name=message.text or "",
            bot_username=bot_user.username or "RKOrko_bot",
        )
    except (ValueError, KeyError, DomainError) as error:
        await message.answer(str(error))
        return
    await state.clear()
    summary = await AdminCatalogService(database).get_channel(channel.id)
    if summary is None:
        await message.answer("Канал создан, но не удалось открыть его карточку.")
        return
    await message.answer(
        format_channel(summary),
        reply_markup=admin_channel_keyboard(str(channel.id), channel.active),
    )


@router.callback_query(F.data.startswith("admin:channel:toggle:"))
async def channel_toggle(callback: CallbackQuery, database: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, database, settings):
        return
    try:
        channel_id = UUID((callback.data or "").removeprefix("admin:channel:toggle:"))
        channel = await AdminCatalogService(database).toggle_channel(
            actor_role=UserRole.ADMIN, channel_id=channel_id
        )
        summary = await AdminCatalogService(database).get_channel(channel.id)
        if summary is None:
            raise DomainError("Канал не найден")
    except (ValueError, DomainError) as error:
        await callback.answer(str(error), show_alert=True)
        return
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            format_channel(summary),
            reply_markup=admin_channel_keyboard(str(channel.id), channel.active),
        )
    await callback.answer("Статус изменён")


@router.callback_query(F.data.startswith("admin:channel:"))
async def channel_card(callback: CallbackQuery, database: Database, settings: Settings) -> None:
    if await deny_if_not_admin(callback, database, settings):
        return
    try:
        channel_id = UUID((callback.data or "").removeprefix("admin:channel:"))
    except ValueError:
        await callback.answer("Некорректный канал", show_alert=True)
        return
    summary = await AdminCatalogService(database).get_channel(channel_id)
    if summary is None:
        await callback.answer("Канал не найден", show_alert=True)
        return
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            format_channel(summary),
            reply_markup=admin_channel_keyboard(str(summary.channel.id), summary.channel.active),
        )
    await callback.answer()


def partner_button_text(partner: Partner) -> str:
    return f"{'🟢' if partner.active else '⚪️'} {partner.name}"


def channel_button_text(summary: ChannelSummary) -> str:
    channel = summary.channel
    return f"{'🟢' if channel.active else '⚪️'} {summary.partner_name} · {channel.name}"


def format_partner(
    partner: Partner,
    channels: list[ChannelSummary],
    telegram_id: str | None = None,
    telegram_username: str | None = None,
) -> str:
    status = "работает" if partner.active else "выключен"
    telegram = f"@{telegram_username}" if telegram_username else "не привязан"
    if telegram_id:
        telegram = f"{telegram} · ID {telegram_id}"
    text = (
        f"Партнёр: {partner.name}\n\n"
        f"Процент: {partner.commission_percent}%\n"
        f"Статус: {status}\n"
        f"Telegram: {telegram}"
    )
    if not channels:
        return f"{text}\n\nКаналов пока нет."
    links = "\n\n".join(
        f"{item.channel.name}:\n{item.channel.referral_link}" for item in channels
    )
    return f"{text}\n\nРеферальные ссылки:\n\n{links}"


def format_channel(summary: ChannelSummary) -> str:
    channel = summary.channel
    status = "работает" if channel.active else "выключен"
    return (
        f"Канал: {channel.name}\n\n"
        f"Партнёр: {summary.partner_name}\n"
        f"Статус: {status}\n\n"
        f"Реферальная ссылка:\n{channel.referral_link}"
    )
