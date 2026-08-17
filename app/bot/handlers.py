import logging
from datetime import UTC, datetime

from aiogram import F, Router
from aiogram.filters import CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from app.bot.keyboards import (
    admin_menu_keyboard,
    consent_document_keyboard,
    consent_keyboard,
    continue_keyboard,
    phone_keyboard,
    retry_submission_keyboard,
    yes_no_keyboard,
)
from app.bot.states import LeadApplication
from app.bot.texts import CONSENT_PROMPT, CONSENT_TEXT, START_TEXT
from app.config import Settings
from app.database import Database
from app.domain.enums import UserRole
from app.domain.intake import QUESTIONS, QuestionKind, normalize_phone
from app.services.lead_intake import LeadIntakeService, SubmissionStatus
from app.services.user_access import UserAccessService

router = Router(name="common")
logger = logging.getLogger(__name__)


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
    referral_code = command.args
    if user is None:
        await message.answer("Не удалось определить Telegram-пользователя.")
        return
    role = await UserAccessService(database, settings).resolve_role(
        telegram_id=str(user.id), telegram_username=user.username
    )
    if role is UserRole.ADMIN:
        await message.answer(
            "Кабинет администратора",
            reply_markup=admin_menu_keyboard(settings.mini_app_url),
        )
        return
    try:
        first_click = await LeadIntakeService(database).record_first_click(
            telegram_id=str(user.id), referral_code=referral_code, clicked_at=clicked_at
        )
    except Exception:
        logger.exception("Failed to record first click")
        await message.answer("Сервис временно недоступен. Попробуй /start чуть позже.")
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
    await message.answer(START_TEXT, reply_markup=continue_keyboard())


@router.callback_query(F.data == "application:begin")
async def begin_application(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(LeadApplication.consent)
    if callback.message:
        await callback.message.answer(
            CONSENT_PROMPT,
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
        await callback.message.edit_text(START_TEXT, reply_markup=continue_keyboard())
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
async def return_to_consent(callback: CallbackQuery) -> None:
    if isinstance(callback.message, Message):
        await callback.message.edit_text(CONSENT_PROMPT, reply_markup=consent_keyboard())
    await callback.answer()


@router.callback_query(LeadApplication.consent, F.data == "consent:decline")
async def decline_consent(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message:
        await callback.message.answer("Без согласия создать заявку не получится.")
    await callback.answer()


@router.callback_query(LeadApplication.consent, F.data == "consent:accept")
async def accept_consent(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(consent_at=datetime.now(UTC).isoformat())
    await state.set_state(LeadApplication.phone)
    if callback.message:
        await callback.message.answer(
            "Отправь номер кнопкой ниже или введи его сообщением.", reply_markup=phone_keyboard()
        )
    await callback.answer()


@router.message(LeadApplication.phone)
async def receive_phone(message: Message, state: FSMContext, database: Database) -> None:
    if message.contact and message.from_user and message.contact.user_id != message.from_user.id:
        await message.answer("Отправь, пожалуйста, именно свой номер.")
        return
    raw_phone = message.contact.phone_number if message.contact else message.text or ""
    try:
        phone = normalize_phone(raw_phone)
    except ValueError as error:
        await message.answer(str(error))
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
        await callback.answer("Ответь текстом")
        return
    answers = dict(data["answers"])
    answers[question.key] = answer
    await state.update_data(answers=answers, question_index=index + 1)
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(reply_markup=None)
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
        await message.answer("Выбери «Да» или «Нет» кнопкой под вопросом.")
        return
    value = (message.text or "").strip()
    if len(value) < 2:
        await message.answer("Напиши название города полностью.")
        return
    answers = dict(data["answers"])
    answers[question.key] = value
    await state.update_data(answers=answers, question_index=index + 1)
    await ask_current_question(message, state, database)


async def ask_current_question(message: Message, state: FSMContext, database: Database) -> None:
    data = await state.get_data()
    index = int(data["question_index"])
    if index >= len(QUESTIONS):
        await finish_application(message, state, database)
        return
    question = QUESTIONS[index]
    keyboard = yes_no_keyboard(index) if question.kind is QuestionKind.YES_NO else None
    await message.answer(question.text, reply_markup=keyboard)


async def finish_application(message: Message, state: FSMContext, database: Database) -> None:
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
        )
    except Exception:
        logger.error("Failed to submit lead application", exc_info=True)
        await message.answer(
            "Не удалось сохранить заявку.", reply_markup=retry_submission_keyboard()
        )
        return
    await state.clear()
    if result.status is SubmissionStatus.DUPLICATE_TELEGRAM:
        await message.answer("Твоя заявка уже зарегистрирована.")
    elif result.status is SubmissionStatus.DUPLICATE_PHONE:
        await message.answer("Этот номер уже есть в системе. Менеджер проверит заявку вручную.")
    else:
        await message.answer(
            f"Отлично, заявка {result.short_id} зарегистрирована. Скоро свяжется менеджер."
        )


@router.callback_query(LeadApplication.submitting, F.data == "application:retry")
async def retry_submission(callback: CallbackQuery, state: FSMContext, database: Database) -> None:
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.edit_reply_markup(reply_markup=None)
        await finish_application(callback.message, state, database)


def parse_answer_callback(value: str) -> tuple[int, str]:
    try:
        prefix, raw_index, answer = value.split(":", maxsplit=2)
        if prefix != "answer" or answer not in {"yes", "no"}:
            raise ValueError
        return int(raw_index), answer
    except ValueError as error:
        raise ValueError("Некорректный ответ анкеты") from error
