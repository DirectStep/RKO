from uuid import UUID

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.types import User as TelegramUser

from app.bot.keyboards import (
    admin_lead_keyboard,
    admin_leads_keyboard,
    admin_menu_keyboard,
    admin_stats_keyboard,
)
from app.config import Settings
from app.database import Database
from app.domain.enums import UserRole
from app.domain.operations import DomainError
from app.models import Lead
from app.services.admin_dashboard import AdminDashboardService
from app.services.lead_assignment import LeadAssignmentService
from app.services.user_access import UserAccessService

router = Router(name="admin")

QUESTION_LABELS = {
    "adult": "Есть 18 лет",
    "has_ip": "Открыто ИП",
    "city": "Город",
    "has_bankruptcy_or_arrests": "Были банкротства или аресты",
    "is_civil_servant": "Госслужащий",
    "has_social_benefits": "Получает социальные выплаты",
    "no_bankruptcy": "Нет банкротств или арестов",
    "not_civil_servant": "Не является госслужащим",
    "no_social_benefits": "Нет социальных выплат",
}


async def is_admin(user: TelegramUser, database: Database, settings: Settings) -> bool:
    role = await UserAccessService(database, settings).resolve_role(
        telegram_id=str(user.id), telegram_username=user.username
    )
    return role is UserRole.ADMIN


@router.message(Command("admin"))
async def open_admin_menu(
    message: Message, state: FSMContext, database: Database, settings: Settings
) -> None:
    if message.from_user is None or not await is_admin(message.from_user, database, settings):
        await message.answer("Этот раздел доступен только администратору.")
        return
    await state.clear()
    await message.answer("Кабинет администратора", reply_markup=admin_menu_keyboard())


@router.callback_query(F.data == "admin:home")
async def admin_home(
    callback: CallbackQuery, state: FSMContext, database: Database, settings: Settings
) -> None:
    if not await is_admin(callback.from_user, database, settings):
        await callback.answer("Нет доступа", show_alert=True)
        return
    await state.clear()
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            "Кабинет администратора", reply_markup=admin_menu_keyboard()
        )
    await callback.answer()


@router.callback_query(F.data == "admin:stats")
async def admin_stats(callback: CallbackQuery, database: Database, settings: Settings) -> None:
    if not await is_admin(callback.from_user, database, settings):
        await callback.answer("Нет доступа", show_alert=True)
        return
    stats = await AdminDashboardService(database).get_stats()
    text = (
        "Сводка\n\n"
        f"Всего заявок: {stats.total_leads}\n"
        f"Новых: {stats.new_leads}\n"
        f"Источник не определён: {stats.unresolved_sources}\n"
        f"Дубли на проверке: {stats.pending_duplicates}"
    )
    if isinstance(callback.message, Message):
        await callback.message.edit_text(text, reply_markup=admin_stats_keyboard())
    await callback.answer()


@router.callback_query(F.data == "admin:leads")
async def admin_leads(callback: CallbackQuery, database: Database, settings: Settings) -> None:
    if not await is_admin(callback.from_user, database, settings):
        await callback.answer("Нет доступа", show_alert=True)
        return
    leads = await AdminDashboardService(database).get_recent_leads()
    buttons = [(str(lead.id), f"{lead.short_id} · {lead.display_name}") for lead in leads]
    text = "Последние заявки" if leads else "Заявок пока нет."
    if isinstance(callback.message, Message):
        await callback.message.edit_text(text, reply_markup=admin_leads_keyboard(buttons))
    await callback.answer()


@router.callback_query(F.data.startswith("admin:lead:"))
async def admin_lead(callback: CallbackQuery, database: Database, settings: Settings) -> None:
    if not await is_admin(callback.from_user, database, settings):
        await callback.answer("Нет доступа", show_alert=True)
        return
    try:
        lead_id = UUID((callback.data or "").removeprefix("admin:lead:"))
    except ValueError:
        await callback.answer("Некорректная заявка", show_alert=True)
        return
    lead = await AdminDashboardService(database).get_lead(lead_id)
    if lead is None:
        await callback.answer("Заявка не найдена", show_alert=True)
        return
    assignment_label = await AdminDashboardService(database).get_assignment_label(lead)
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            format_lead(lead, assignment_label),
            reply_markup=admin_lead_keyboard(str(lead.id), lead.assignment_status.value),
        )
    await callback.answer()


def format_lead(lead: Lead, assignment_label: str | None = None) -> str:
    username = f"@{lead.telegram_username}" if lead.telegram_username else "не указан"
    answers = "\n".join(
        f"{QUESTION_LABELS.get(key, key)}: {format_answer(value)}"
        for key, value in lead.questionnaire_answers.items()
    )
    return (
        f"Заявка {lead.short_id}\n\n"
        f"Имя: {lead.display_name}\n"
        f"Telegram: {username}\n"
        f"Телефон: {lead.phone}\n"
        f"Статус: {lead.internal_status.value}\n"
        f"Источник: {assignment_label or lead.assignment_status.value}\n\n"
        f"Анкета:\n{answers}"
    )


def format_answer(value: str) -> str:
    return {"yes": "Да", "no": "Нет"}.get(value, value)


@router.callback_query(F.data.startswith("admin:source:confirm:"))
async def confirm_lead_source(
    callback: CallbackQuery, database: Database, settings: Settings
) -> None:
    if not await is_admin(callback.from_user, database, settings):
        await callback.answer("Нет доступа", show_alert=True)
        return
    try:
        lead_id = UUID((callback.data or "").removeprefix("admin:source:confirm:"))
        lead = await LeadAssignmentService(database).confirm_proposed(
            actor_role=UserRole.ADMIN, lead_id=lead_id
        )
    except (ValueError, DomainError) as error:
        await callback.answer(str(error), show_alert=True)
        return
    assignment_label = await AdminDashboardService(database).get_assignment_label(lead)
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            format_lead(lead, assignment_label),
            reply_markup=admin_lead_keyboard(str(lead.id), lead.assignment_status.value),
        )
    await callback.answer("Источник подтверждён")


@router.callback_query(F.data.startswith("admin:source:direct:"))
async def mark_lead_direct(callback: CallbackQuery, database: Database, settings: Settings) -> None:
    if not await is_admin(callback.from_user, database, settings):
        await callback.answer("Нет доступа", show_alert=True)
        return
    try:
        lead_id = UUID((callback.data or "").removeprefix("admin:source:direct:"))
        lead = await LeadAssignmentService(database).mark_direct(
            actor_role=UserRole.ADMIN, lead_id=lead_id
        )
    except (ValueError, DomainError) as error:
        await callback.answer(str(error), show_alert=True)
        return
    assignment_label = await AdminDashboardService(database).get_assignment_label(lead)
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            format_lead(lead, assignment_label),
            reply_markup=admin_lead_keyboard(str(lead.id), lead.assignment_status.value),
        )
    await callback.answer("Заявка отмечена как прямая")
