import logging
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from aiogram import Bot, F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message, ReplyKeyboardRemove
from sqlalchemy import select

from app.bot.keyboards import (
    admin_menu_keyboard,
    admin_new_lead_keyboard,
    application_edit_keyboard,
    application_review_keyboard,
    cabinet_keyboard,
    consent_document_keyboard,
    consent_keyboard,
    continue_keyboard,
    manager_leads_keyboard,
    manager_menu_keyboard,
    partner_menu_keyboard,
    phone_keyboard,
    resubmit_application_keyboard,
    retry_submission_keyboard,
    yes_no_keyboard,
)
from app.bot.states import LeadApplication
from app.bot.texts import CONSENT_TEXT, PARTNER_START_TEXT, START_TEXT, consent_prompt
from app.config import Settings
from app.database import Database
from app.domain.enums import AccessStatus, LeadWorkflowStage, UserRole
from app.domain.intake import (
    QUESTIONS,
    QuestionKind,
    normalize_email,
    normalize_full_name,
    normalize_phone,
)
from app.domain.operations import DomainError
from app.models import Bank, Channel, Lead, LeadBank, Partner, User
from app.reports.partner_report import build_partner_report
from app.services.lead_intake import LeadIntakeService, SubmissionStatus
from app.services.lead_workflow import LeadWorkflowService
from app.services.partner_cabinet import partner_cabinet_data, partner_contact
from app.services.user_access import UserAccessService
from app.services.workflow import WorkflowService

router = Router(name="common")
logger = logging.getLogger(__name__)

QUESTION_REVIEW_LABELS = tuple(question.review_label for question in QUESTIONS)

PARTNER_STATUS_LABELS = {
    "new": "Новая",
    "in_progress": "В работе",
    "opening_accounts": "Открываем счета",
    "partially_completed": "Часть счетов открыта",
    "completed": "Завершена",
    "paused": "Приостановлена",
    "closed_without_result": "Закрыта без результата",
}


async def get_current_lead(database: Database, telegram_id: str) -> Lead | None:
    async with database.session() as session:
        return cast(
            Lead | None,
            await session.scalar(
                select(Lead)
                .where(Lead.telegram_id == telegram_id, Lead.archived_at.is_(None))
                .order_by(Lead.application_at.desc())
                .limit(1)
            ),
        )


async def get_partner(database: Database, telegram_id: str) -> Partner | None:
    async with database.session() as session:
        return cast(
            Partner | None,
            await session.scalar(
                select(Partner)
                .join(User, User.id == Partner.telegram_user_id)
                .where(User.telegram_id == telegram_id, Partner.active.is_(True))
            ),
        )


@router.message(CommandStart())
async def start(
    message: Message,
    state: FSMContext,
    command: CommandObject,
    database: Database,
    settings: Settings,
) -> None:
    await state.clear()
    user = message.from_user
    clicked_at = datetime.now(UTC)
    requested_referral_code = command.args
    if user is None:
        await message.answer(
            "Не удалось определить ваш Telegram-аккаунт. Отправьте /start ещё раз."
        )
        return
    role = await UserAccessService(database, settings).resolve_role(
        telegram_id=str(user.id), telegram_username=user.username
    )
    if requested_referral_code and requested_referral_code.startswith("partner_"):
        if role in {UserRole.ADMIN, UserRole.MANAGER}:
            await message.answer("Сотрудника нельзя активировать как партнёра.")
            return
        try:
            await WorkflowService(database).activate_partner_with_token(
                telegram_id=str(user.id),
                telegram_username=user.username,
                token=requested_referral_code.removeprefix("partner_"),
            )
        except DomainError as error:
            await message.answer(str(error))
            return
        await message.answer(
            PARTNER_START_TEXT,
            parse_mode="HTML",
            reply_markup=partner_menu_keyboard(settings.mini_app_url),
        )
        return
    if role is UserRole.ADMIN:
        await message.answer(
            "Кабинет администратора",
            reply_markup=admin_menu_keyboard(settings.mini_app_url),
        )
        return
    if role is UserRole.MANAGER:
        await message.answer(
            "Кабинет менеджера. Здесь доступны ваши заявки, банки и рабочие статусы.",
            reply_markup=manager_menu_keyboard(settings.mini_app_url),
        )
        return
    if role is UserRole.PARTNER:
        await message.answer(
            PARTNER_START_TEXT,
            parse_mode="HTML",
            reply_markup=partner_menu_keyboard(settings.mini_app_url),
        )
        return
    current_lead = await get_current_lead(database, str(user.id))
    if current_lead is not None:
        await message.answer(START_TEXT, parse_mode="HTML", reply_markup=continue_keyboard())
        return
    try:
        first_click = await LeadIntakeService(database).record_first_click(
            telegram_id=str(user.id),
            referral_code=requested_referral_code,
            clicked_at=clicked_at,
        )
    except Exception:
        logger.exception("Failed to record first click")
        await message.answer("Сервис временно недоступен. Попробуйте /start чуть позже.")
        return
    referral_code = first_click.referral_code
    clicked_at = first_click.first_click_at
    await state.update_data(
        referral_code=referral_code,
        first_click_at=clicked_at.isoformat(),
        telegram_id=str(user.id) if user else None,
        telegram_username=user.username if user else None,
        display_name=user.full_name if user else "Пользователь Telegram",
    )
    start_text = START_TEXT
    if requested_referral_code and first_click.is_new and first_click.referral_code is None:
        start_text = f"Эта партнёрская ссылка недействительна или отключена.\n\n{START_TEXT}"
    await message.answer(start_text, parse_mode="HTML", reply_markup=continue_keyboard())


@router.callback_query(F.data == "manager:leads")
async def manager_leads(
    callback: CallbackQuery,
    database: Database,
    settings: Settings,
) -> None:
    async with database.session() as session:
        manager = await session.scalar(
            select(User).where(
                User.telegram_id == str(callback.from_user.id),
                User.role == UserRole.MANAGER,
                User.access_status == AccessStatus.ACTIVE,
            )
        )
        leads = (
            list(
                await session.scalars(
                    select(Lead)
                    .where(
                        Lead.manager_id == manager.id,
                        Lead.archived_at.is_(None),
                        Lead.bank_selection_submitted_at.is_not(None),
                        Lead.workflow_stage.in_(
                            {
                                LeadWorkflowStage.AWAITING_MANAGER,
                                LeadWorkflowStage.MANAGER_PROCESSING,
                            }
                        ),
                    )
                    .order_by(Lead.last_updated_at.desc())
                    .limit(20)
                )
            )
            if manager is not None
            else []
        )
    if callback.message is None:
        await callback.answer()
        return
    if manager is None:
        await callback.answer("Раздел доступен менеджеру", show_alert=True)
        return
    buttons = [
        (
            str(lead.id),
            f"{'🆕 ' if lead.manager_started_at is None else ''}"
            f"{lead.short_id} · {lead.display_name}",
        )
        for lead in leads
    ]
    await callback.message.answer(
        "Мои заявки" if leads else "Закреплённых заявок пока нет",
        reply_markup=(
            manager_leads_keyboard(buttons)
            if buttons
            else manager_menu_keyboard(settings.mini_app_url)
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "manager:home")
async def manager_home(callback: CallbackQuery, database: Database, settings: Settings) -> None:
    async with database.session() as session:
        is_manager = await session.scalar(
            select(User.id).where(
                User.telegram_id == str(callback.from_user.id),
                User.role == UserRole.MANAGER,
                User.access_status == AccessStatus.ACTIVE,
            )
        )
    if is_manager is None:
        await callback.answer("Раздел доступен менеджеру", show_alert=True)
        return
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            "Кабинет менеджера",
            reply_markup=manager_menu_keyboard(settings.mini_app_url),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("manager:lead:"))
async def manager_lead(
    callback: CallbackQuery,
    database: Database,
    notification_bots: tuple[Bot, ...],
) -> None:
    try:
        lead_id = UUID((callback.data or "").removeprefix("manager:lead:"))
    except ValueError:
        await callback.answer("Некорректная заявка", show_alert=True)
        return
    async with database.session() as session:
        manager = await session.scalar(
            select(User).where(
                User.telegram_id == str(callback.from_user.id),
                User.role == UserRole.MANAGER,
                User.access_status == AccessStatus.ACTIVE,
            )
        )
        previous_manager_started_at = await session.scalar(
            select(Lead.manager_started_at).where(Lead.id == lead_id)
        )
    if manager is None:
        await callback.answer("Раздел доступен менеджеру", show_alert=True)
        return
    try:
        lead = await LeadWorkflowService(database).claim_by_manager(
            actor_role=UserRole.MANAGER,
            actor_id=manager.id,
            lead_id=lead_id,
        )
    except DomainError as error:
        await callback.answer(str(error), show_alert=True)
        return
    async with database.session() as session:
        bank_names = list(
            await session.scalars(
                select(Bank.name)
                .join(LeadBank, LeadBank.bank_id == Bank.id)
                .where(LeadBank.lead_id == lead.id, LeadBank.selected_by_lead.is_(True))
                .order_by(Bank.name)
            )
        )
    username = f"@{lead.telegram_username}" if lead.telegram_username else "не указан"
    text = (
        f"Заявка {lead.short_id} в работе\n\n"
        f"Клиент: {lead.display_name}\n"
        f"Телефон: {lead.phone}\n"
        f"Telegram: {username}\n"
        f"Выбранные банки: {', '.join(bank_names) if bank_names else 'нет'}"
    )
    if isinstance(callback.message, Message):
        await callback.message.edit_text(text)
    if previous_manager_started_at is None:
        manager_name = (
            f"@{manager.telegram_username}"
            if manager.telegram_username
            else manager.telegram_id or "менеджер"
        )
        for bot in notification_bots:
            try:
                await bot.send_message(
                    chat_id=int(lead.telegram_id),
                    text=(
                        f"Ваш персональный менеджер — {manager_name}. "
                        "Скоро он свяжется с вами и создаст отдельную группу "
                        "для сопровождения."
                    ),
                )
            except Exception:
                logger.exception(
                    "Failed to notify client %s after manager opened lead %s via bot %s",
                    lead.telegram_id,
                    lead.id,
                    bot.id,
                )
    await callback.answer("Заявка переведена в работу")


async def partner_for_callback(callback: CallbackQuery, database: Database) -> Partner | None:
    partner = await get_partner(database, str(callback.from_user.id))
    if partner is None:
        await callback.answer("Партнёрский кабинет не найден", show_alert=True)
    return partner


@router.callback_query(F.data == "partner:summary")
async def partner_summary(callback: CallbackQuery, database: Database, settings: Settings) -> None:
    partner = await partner_for_callback(callback, database)
    if partner is None or callback.message is None:
        return
    metrics = (await partner_cabinet_data(database, partner.id))["metrics"]
    await callback.message.answer(
        "Сводка партнёра\n\n"
        f"Всего заявок: {metrics['total']}\n"
        f"Новые заявки: {metrics['new']}\n"
        f"Заявки в работе: {metrics['active']}\n"
        f"Счета в процессе открытия: {metrics['planned_banks']}\n"
        f"Активированные счета: {metrics['opened_banks']}\n"
        f"Ожидаемая выплата: {metrics['estimated_payout']} ₽\n"
        f"Последняя выплата: {metrics['last_payout']} ₽\n"
        f"Выплачено всего: {metrics['paid']} ₽\n"
        f"Завершённые заявки: {metrics['completed']}\n"
        f"Отменённые заявки: {metrics['cancelled']}",
        reply_markup=partner_menu_keyboard(settings.mini_app_url),
    )
    await callback.answer()


async def send_partner_leads(
    callback: CallbackQuery,
    database: Database,
    settings: Settings,
    *,
    active_only: bool,
) -> None:
    partner = await partner_for_callback(callback, database)
    if partner is None or callback.message is None:
        return
    leads = (await partner_cabinet_data(database, partner.id))["leads"]
    if active_only:
        leads = [
            lead
            for lead in leads
            if lead["status"]
            in {"in_progress", "opening_accounts", "partially_completed", "paused"}
        ]
    lines = [
        f"{lead['short_id']} · {lead['name']} · {lead['channel']} · "
        f"{PARTNER_STATUS_LABELS.get(lead['status'], 'Статус уточняется')}"
        for lead in leads[:20]
    ]
    title = "Активные заявки" if active_only else "Мои заявки"
    suffix = (
        f"\n\nПоказаны первые 20 из {len(leads)}. Полный список — в кабинете."
        if len(leads) > 20
        else ""
    )
    await callback.message.answer(
        f"{title}\n\n" + ("\n".join(lines) if lines else "Пока пусто") + suffix,
        reply_markup=partner_menu_keyboard(settings.mini_app_url),
    )
    await callback.answer()


@router.callback_query(F.data == "partner:leads")
async def partner_leads(callback: CallbackQuery, database: Database, settings: Settings) -> None:
    await send_partner_leads(callback, database, settings, active_only=False)


@router.callback_query(F.data == "partner:active")
async def partner_active(callback: CallbackQuery, database: Database, settings: Settings) -> None:
    await send_partner_leads(callback, database, settings, active_only=True)


@router.callback_query(F.data.in_({"partner:opened", "partner:payments"}))
async def partner_finances(callback: CallbackQuery, database: Database, settings: Settings) -> None:
    partner = await partner_for_callback(callback, database)
    if partner is None or callback.message is None:
        return
    data = await partner_cabinet_data(database, partner.id)
    if callback.data == "partner:opened":
        rows = [
            f"{lead['short_id']} · {bank['bank']} · {bank['reward_fact']} ₽"
            for lead in data["leads"]
            for bank in lead["banks"]
            if bank["status"] == "opened"
        ]
        text = "Активированные счета\n\n" + ("\n".join(rows[:30]) if rows else "Пока пусто")
    else:
        metrics = data["metrics"]
        text = (
            "Выплаты\n\n"
            f"Ожидается: {metrics['estimated_payout']} ₽\n"
            f"Последняя выплата: {metrics['last_payout']} ₽\n"
            f"Выплачено всего: {metrics['paid']} ₽"
        )
    await callback.message.answer(text, reply_markup=partner_menu_keyboard(settings.mini_app_url))
    await callback.answer()


@router.callback_query(F.data == "partner:channels")
async def partner_channels(callback: CallbackQuery, database: Database, settings: Settings) -> None:
    partner = await partner_for_callback(callback, database)
    if partner is None or callback.message is None:
        return
    async with database.session() as session:
        channels = list(
            await session.scalars(
                select(Channel).where(Channel.partner_id == partner.id).order_by(Channel.name)
            )
        )
    lines = [f"{channel.name}:\n{channel.referral_link}" for channel in channels]
    await callback.message.answer(
        "Каналы\n\n"
        + ("\n\n".join(lines) if lines else "Каналов пока нет. Добавить можно в мини-приложении."),
        reply_markup=partner_menu_keyboard(settings.mini_app_url),
    )
    await callback.answer()


@router.callback_query(F.data == "partner:contact")
async def partner_contact_handler(callback: CallbackQuery, database: Database) -> None:
    partner = await partner_for_callback(callback, database)
    if partner is None or callback.message is None:
        return
    contact = await partner_contact(database, partner.id)
    text = f"Ваш администратор: {contact['name']}"
    if contact["url"]:
        text += f"\n{contact['url']}"
    else:
        text += "\nПока не назначен. Напишите в общий чат команды."
    await callback.message.answer(text)
    await callback.answer()


@router.callback_query(F.data == "partner:report")
async def partner_report_handler(callback: CallbackQuery, database: Database) -> None:
    partner = await partner_for_callback(callback, database)
    if partner is None or callback.message is None:
        return
    report = await build_partner_report(database, partner.id)
    await callback.message.answer_document(
        BufferedInputFile(report, filename="rko-partner-report.xlsx"),
        caption="Отчёт за всё время. Произвольный период можно выбрать в мини-приложении.",
    )
    await callback.answer()


@router.callback_query(F.data == "application:begin")
async def begin_application(
    callback: CallbackQuery,
    state: FSMContext,
    database: Database,
    settings: Settings,
) -> None:
    role = await UserAccessService(database, settings).resolve_role(
        telegram_id=str(callback.from_user.id),
        telegram_username=callback.from_user.username,
    )
    if role is UserRole.PARTNER:
        await state.clear()
        if callback.message:
            await callback.message.answer(
                "Это партнёрский аккаунт. Оставить с него заявку как клиент нельзя.",
                reply_markup=cabinet_keyboard(settings.mini_app_url),
            )
        await callback.answer("Заявка недоступна партнёру", show_alert=True)
        return
    await state.set_state(LeadApplication.consent)
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(
            consent_prompt(settings.mini_app_url),
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=consent_keyboard(),
        )
    await callback.answer()


@router.callback_query(F.data == "application:resubmit")
async def resubmit_application(
    callback: CallbackQuery,
    state: FSMContext,
    database: Database,
    settings: Settings,
) -> None:
    telegram_id = str(callback.from_user.id)
    async with database.session() as session:
        previous = await session.scalar(
            select(Lead)
            .where(
                Lead.telegram_id == telegram_id,
                Lead.archived_at.is_(None),
                Lead.workflow_stage == LeadWorkflowStage.NOT_ELIGIBLE,
            )
            .order_by(Lead.application_at.desc())
            .limit(1)
        )
    if previous is None:
        await callback.answer("Повторная подача для этой заявки недоступна", show_alert=True)
        return
    await state.clear()
    repeat_data: dict[str, Any] = {
        "referral_code": previous.first_referral_code,
        "first_click_at": previous.first_click_at.isoformat(),
        "telegram_id": telegram_id,
        "telegram_username": callback.from_user.username,
        "display_name": callback.from_user.full_name,
        "repeat_of_id": str(previous.id),
    }
    if previous.consent_status:
        repeat_data["consent_at"] = previous.consent_at.isoformat()
    await state.update_data(repeat_data)
    has_valid_consent = previous.consent_status
    await state.set_state(LeadApplication.phone if has_valid_consent else LeadApplication.consent)
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(reply_markup=None)
        if has_valid_consent:
            await callback.message.answer(
                "Отправьте номер кнопкой ниже или введите его сообщением.",
                reply_markup=phone_keyboard(),
            )
        else:
            await callback.message.answer(
                consent_prompt(settings.mini_app_url),
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=consent_keyboard(),
            )
    await callback.answer()


@router.callback_query(F.data == "privacy:show")
async def show_privacy_before_application(callback: CallbackQuery) -> None:
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            CONSENT_TEXT,
            reply_markup=consent_document_keyboard(application_started=False),
        )
    await callback.answer()


@router.callback_query(F.data == "privacy:back")
async def return_from_privacy(callback: CallbackQuery) -> None:
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            START_TEXT,
            parse_mode="HTML",
            reply_markup=continue_keyboard(),
        )
    await callback.answer()


@router.callback_query(LeadApplication.consent, F.data == "consent:show")
async def show_privacy_during_application(callback: CallbackQuery) -> None:
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            CONSENT_TEXT,
            reply_markup=consent_document_keyboard(application_started=True),
        )
    await callback.answer()


@router.callback_query(LeadApplication.consent, F.data == "consent:back")
async def return_to_consent(callback: CallbackQuery, settings: Settings) -> None:
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            consent_prompt(settings.mini_app_url),
            parse_mode="HTML",
            disable_web_page_preview=True,
            reply_markup=consent_keyboard(),
        )
    await callback.answer()


@router.callback_query(LeadApplication.consent, F.data == "consent:decline")
async def decline_consent(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message:
        await callback.message.answer(
            "Без согласия создать заявку не получится. Если передумаете, "
            "нажмите «Продолжить» в сообщении выше или отправьте /start."
        )
    await callback.answer()


@router.callback_query(LeadApplication.consent, F.data == "consent:accept")
async def accept_consent(
    callback: CallbackQuery,
    state: FSMContext,
    database: Database,
    settings: Settings,
) -> None:
    consent_at = datetime.now(UTC)
    telegram_id = str(callback.from_user.id)
    await state.update_data(consent_at=consent_at.isoformat())
    current_lead = await get_current_lead(database, telegram_id)
    if current_lead is not None:
        async with database.session() as session:
            stored_lead = await session.get(Lead, current_lead.id)
            if stored_lead is not None:
                stored_lead.consent_status = True
                stored_lead.consent_at = consent_at
                await session.commit()
        await state.clear()
        if callback.message:
            await callback.message.edit_reply_markup(reply_markup=None)
            if current_lead.workflow_stage is LeadWorkflowStage.NOT_ELIGIBLE:
                await callback.message.answer(
                    f"Заявка {current_lead.short_id} имеет статус «Не подходит».\n\n"
                    "Вы можете подать заявку повторно, если указали что-то неверно "
                    "или ваша ситуация изменилась.",
                    reply_markup=resubmit_application_keyboard(),
                )
            else:
                await callback.message.answer(
                    "Кабинет клиента. Здесь видны статус заявки, назначенные банки "
                    "и условия их активации.",
                    reply_markup=cabinet_keyboard(settings.mini_app_url),
                )
        await callback.answer()
        return
    await state.set_state(LeadApplication.phone)
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(
            "Отправьте номер кнопкой ниже или введите его сообщением.",
            reply_markup=phone_keyboard(),
        )
    await callback.answer()


@router.message(LeadApplication.phone)
async def receive_phone(message: Message, state: FSMContext, database: Database) -> None:
    if message.contact and message.from_user and message.contact.user_id != message.from_user.id:
        await message.answer("Отправьте, пожалуйста, именно свой номер.")
        return
    raw_phone = message.contact.phone_number if message.contact else message.text or ""
    try:
        phone = normalize_phone(raw_phone)
    except ValueError as error:
        await message.answer(str(error))
        return
    data = await state.get_data()
    if data.get("review_edit"):
        await state.update_data(phone=phone, review_edit=False)
        await message.answer("Номер обновлён.", reply_markup=ReplyKeyboardRemove())
        await show_application_review(message, state)
        return
    await state.update_data(phone=phone, answers={}, question_index=0)
    await state.set_state(LeadApplication.questionnaire)
    await message.answer(
        "Спасибо. Теперь несколько коротких вопросов.", reply_markup=ReplyKeyboardRemove()
    )
    await ask_current_question(message, state, database)


@router.callback_query(LeadApplication.questionnaire, F.data.startswith("answer:"))
async def receive_yes_no(callback: CallbackQuery, state: FSMContext, database: Database) -> None:
    data = await state.get_data()
    index = int(data["question_index"])
    if index >= len(QUESTIONS):
        await callback.answer("Анкета уже заполнена")
        return
    question = QUESTIONS[index]
    try:
        callback_index, answer = parse_answer_callback(callback.data or "")
    except ValueError:
        await callback.answer("Некорректный ответ")
        return
    if callback_index != index:
        await callback.answer("Этот вопрос уже обработан")
        return
    if question.kind is not QuestionKind.YES_NO:
        await callback.answer("Ответьте текстом")
        return
    answers = dict(data["answers"])
    answers[question.key] = answer
    await state.update_data(answers=answers, question_index=index + 1)
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(reply_markup=None)
        if data.get("review_edit"):
            await state.update_data(review_edit=False)
            await show_application_review(callback.message, state)
            return
        await ask_current_question(callback.message, state, database)


@router.message(LeadApplication.questionnaire)
async def receive_text_answer(message: Message, state: FSMContext, database: Database) -> None:
    data = await state.get_data()
    index = int(data["question_index"])
    if index >= len(QUESTIONS):
        await state.set_state(LeadApplication.submitting)
        await message.answer(
            "Анкета уже заполнена. Повтори сохранение.",
            reply_markup=retry_submission_keyboard(),
        )
        return
    question = QUESTIONS[index]
    if question.kind is not QuestionKind.TEXT:
        await message.answer("Выберите «Да» или «Нет» кнопкой под вопросом.")
        return
    value = (message.text or "").strip()
    try:
        if question.key == "full_name":
            value = normalize_full_name(value)
        elif question.key == "email":
            value = normalize_email(value)
        elif len(value) < 2:
            raise ValueError("Напишите название города полностью")
    except ValueError as error:
        await message.answer(str(error))
        return
    answers = dict(data["answers"])
    answers[question.key] = value
    await state.update_data(answers=answers, question_index=index + 1)
    if data.get("review_edit"):
        await state.update_data(review_edit=False)
        await show_application_review(message, state)
        return
    await ask_current_question(message, state, database)


async def ask_current_question(message: Message, state: FSMContext, database: Database) -> None:
    data = await state.get_data()
    index = int(data["question_index"])
    if index >= len(QUESTIONS):
        await show_application_review(message, state)
        return
    question = QUESTIONS[index]
    keyboard = yes_no_keyboard(index) if question.kind is QuestionKind.YES_NO else None
    await message.answer(question.text, reply_markup=keyboard)


async def show_application_review(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.set_state(LeadApplication.review)
    await message.answer(
        format_application_review(data),
        reply_markup=application_review_keyboard(),
    )


@router.callback_query(LeadApplication.review, F.data == "application:edit")
async def choose_application_field(callback: CallbackQuery) -> None:
    if isinstance(callback.message, Message):
        items = list(enumerate(QUESTION_REVIEW_LABELS))
        await callback.message.edit_reply_markup(reply_markup=application_edit_keyboard(items))
    await callback.answer("Что изменить?")


@router.callback_query(LeadApplication.review, F.data == "application:edit:back")
async def return_to_application_review(callback: CallbackQuery) -> None:
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(reply_markup=application_review_keyboard())
    await callback.answer()


@router.callback_query(LeadApplication.review, F.data == "application:edit:phone")
async def edit_application_phone(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(review_edit=True)
    await state.set_state(LeadApplication.phone)
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(
            "Отправьте исправленный номер.",
            reply_markup=phone_keyboard(),
        )
    await callback.answer()


@router.callback_query(
    LeadApplication.review,
    F.data.startswith("application:edit:question:"),
)
async def edit_application_answer(callback: CallbackQuery, state: FSMContext) -> None:
    try:
        index = int((callback.data or "").removeprefix("application:edit:question:"))
        if index < 0:
            raise IndexError
        question = QUESTIONS[index]
    except (ValueError, IndexError):
        await callback.answer("Не удалось открыть вопрос", show_alert=True)
        return
    await state.update_data(question_index=index, review_edit=True)
    await state.set_state(LeadApplication.questionnaire)
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(reply_markup=None)
        keyboard = yes_no_keyboard(index) if question.kind is QuestionKind.YES_NO else None
        await callback.message.answer(question.text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(LeadApplication.review, F.data == "application:confirm")
async def confirm_application(
    callback: CallbackQuery,
    state: FSMContext,
    database: Database,
    notification_bots: tuple[Bot, ...],
    settings: Settings,
) -> None:
    await state.set_state(LeadApplication.submitting)
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(reply_markup=None)
        await finish_application(
            callback.message,
            state,
            database,
            notification_bots,
            settings,
        )


async def finish_application(
    message: Message,
    state: FSMContext,
    database: Database,
    notification_bots: tuple[Bot, ...],
    settings: Settings,
) -> None:
    await state.set_state(LeadApplication.submitting)
    data = await state.get_data()
    if not data.get("telegram_id"):
        await message.answer("Не удалось определить Telegram-пользователя. Запусти /start ещё раз.")
        return
    try:
        result = await LeadIntakeService(database).submit(
            telegram_id=data["telegram_id"],
            telegram_username=data.get("telegram_username"),
            display_name=data["display_name"],
            phone=data["phone"],
            referral_code=data.get("referral_code"),
            first_click_at=datetime.fromisoformat(data["first_click_at"]),
            consent_at=datetime.fromisoformat(data["consent_at"]),
            answers=data["answers"],
            repeat_of_id=(UUID(data["repeat_of_id"]) if data.get("repeat_of_id") else None),
        )
    except DomainError as error:
        await state.clear()
        await message.answer(str(error), reply_markup=ReplyKeyboardRemove())
        return
    except Exception:
        logger.error("Failed to submit lead application", exc_info=True)
        await message.answer(
            "Не удалось сохранить заявку. Нажмите «Повторить отправку».",
            reply_markup=retry_submission_keyboard(),
        )
        return
    await state.clear()
    if result.status is SubmissionStatus.DUPLICATE_TELEGRAM:
        await message.answer("Ваша заявка уже зарегистрирована.")
    elif result.status is SubmissionStatus.DUPLICATE_PHONE:
        await message.answer("Этот номер уже есть в системе. Менеджер проверит заявку вручную.")
    else:
        if result.eligible:
            await message.answer(
                f"Отлично, заявка {result.short_id} зарегистрирована. "
                "Скоро с вами свяжется специалист."
            )
        else:
            await message.answer(
                f"Заявка {result.short_id} сохранена. К сожалению, по текущим "
                "условиям мы пока не сможем помочь с открытием счетов.\n\n"
                "Вы можете подать заявку повторно, если указали что-то неверно "
                "или ваша ситуация изменилась.",
                reply_markup=resubmit_application_keyboard(),
            )
        if result.lead_id is not None:
            await notify_responsible_admins(
                notification_bots,
                database,
                result.lead_id,
            )


@router.callback_query(LeadApplication.submitting, F.data == "application:retry")
async def retry_submission(
    callback: CallbackQuery,
    state: FSMContext,
    database: Database,
    notification_bots: tuple[Bot, ...],
    settings: Settings,
) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(reply_markup=None)
        await finish_application(
            callback.message,
            state,
            database,
            notification_bots,
            settings,
        )


async def notify_responsible_admins(
    bots: tuple[Bot, ...], database: Database, lead_id: UUID
) -> None:
    async with database.session() as session:
        lead = await session.get(Lead, lead_id)
        channel = (
            await session.get(Channel, lead.channel_id)
            if lead is not None and lead.channel_id is not None
            else None
        )
        recipient_ids: list[str] = []
        if lead is not None and lead.primary_admin_id is not None:
            recipient = await session.scalar(
                select(User.telegram_id).where(
                    User.id == lead.primary_admin_id,
                    User.role == UserRole.ADMIN,
                    User.access_status == AccessStatus.ACTIVE,
                )
            )
            if recipient:
                recipient_ids.append(recipient)
        if lead is not None and not recipient_ids:
            recipient_ids = list(
                await session.scalars(
                    select(User.telegram_id).where(
                        User.role == UserRole.ADMIN,
                        User.access_status == AccessStatus.ACTIVE,
                        User.telegram_id.is_not(None),
                    )
                )
            )
    if lead is None:
        return
    notification_text = format_admin_lead_notification(lead, channel)
    for bot in bots:
        for telegram_id in recipient_ids:
            try:
                await bot.send_message(
                    chat_id=int(telegram_id),
                    text=notification_text,
                    reply_markup=admin_new_lead_keyboard(str(lead.id)),
                )
            except Exception:
                logger.exception(
                    "Failed to notify admin %s about lead %s via bot %s",
                    telegram_id,
                    lead.id,
                    bot.id,
                )


def format_admin_lead_notification(lead: Lead, channel: Channel | None) -> str:
    city = lead.questionnaire_answers.get("city") or "Не указан"
    eligibility_notice = (
        "\n\n🔴 НЕ ПОДХОДИТ ПО УСЛОВИЯМ АНКЕТЫ"
        if lead.workflow_stage is LeadWorkflowStage.NOT_ELIGIBLE
        else ""
    )
    return (
        f"{'Повторная' if lead.is_repeat else 'Новая'} заявка {lead.short_id}\n\n"
        f"Источник: {channel.name if channel else 'Прямая заявка'}\n"
        f"Город: {city}"
        f"{eligibility_notice}"
    )


def parse_answer_callback(value: str) -> tuple[int, str]:
    try:
        prefix, raw_index, answer = value.split(":", maxsplit=2)
        if prefix != "answer" or answer not in {"yes", "no"}:
            raise ValueError
        return int(raw_index), answer
    except ValueError as error:
        raise ValueError("Некорректный ответ анкеты") from error


def format_application_review(data: dict[str, object]) -> str:
    answers = data.get("answers")
    answer_values = answers if isinstance(answers, dict) else {}
    lines = ["Проверьте данные перед отправкой:", "", f"Телефон: {data.get('phone', '—')}"]
    for index, question in enumerate(QUESTIONS):
        value = answer_values.get(question.key, "—")
        if value == "yes":
            value = "Да"
        elif value == "no":
            value = "Нет"
        lines.append(f"{QUESTION_REVIEW_LABELS[index]}: {value}")
    lines.extend(["", "Если всё правильно, нажмите «Да, всё верно»."])
    return "\n".join(lines)
