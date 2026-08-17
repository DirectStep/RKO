from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)


def continue_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Продолжить", callback_data="application:begin")]
        ]
    )


def consent_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Согласен", callback_data="consent:accept")],
            [InlineKeyboardButton(text="Не согласен", callback_data="consent:decline")],
        ]
    )


def phone_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отправить мой номер", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def yes_no_keyboard(question_index: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Да", callback_data=f"answer:{question_index}:yes"),
                InlineKeyboardButton(text="Нет", callback_data=f"answer:{question_index}:no"),
            ]
        ]
    )


def retry_submission_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Повторить сохранение", callback_data="application:retry")]
        ]
    )


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Сводка", callback_data="admin:stats")],
            [InlineKeyboardButton(text="Последние заявки", callback_data="admin:leads")],
            [
                InlineKeyboardButton(text="Партнёры", callback_data="admin:partners"),
                InlineKeyboardButton(text="Каналы", callback_data="admin:channels"),
            ],
        ]
    )


def admin_leads_keyboard(leads: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"admin:lead:{lead_id}")]
        for lead_id, label in leads
    ]
    rows.append([InlineKeyboardButton(text="Назад", callback_data="admin:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_stats_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Последние заявки", callback_data="admin:leads")],
            [InlineKeyboardButton(text="В главное меню", callback_data="admin:home")],
        ]
    )


def admin_lead_keyboard(lead_id: str, assignment_status: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if assignment_status == "pending":
        rows.append(
            [
                InlineKeyboardButton(
                    text="Подтвердить источник",
                    callback_data=f"admin:source:confirm:{lead_id}",
                )
            ]
        )
    if assignment_status in {"pending", "unresolved"}:
        rows.append(
            [
                InlineKeyboardButton(
                    text="Это прямая заявка",
                    callback_data=f"admin:source:direct:{lead_id}",
                )
            ]
        )
    rows.extend(
        [
            [InlineKeyboardButton(text="К заявкам", callback_data="admin:leads")],
            [InlineKeyboardButton(text="В главное меню", callback_data="admin:home")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_partners_keyboard(partners: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"admin:partner:{partner_id}")]
        for partner_id, label in partners
    ]
    rows.extend(
        [
            [InlineKeyboardButton(text="Добавить партнёра", callback_data="admin:partner:new")],
            [InlineKeyboardButton(text="В главное меню", callback_data="admin:home")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_partner_keyboard(partner_id: str, active: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Добавить канал", callback_data=f"admin:channel:new:{partner_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="Выключить" if active else "Включить",
                    callback_data=f"admin:partner:toggle:{partner_id}",
                )
            ],
            [InlineKeyboardButton(text="К партнёрам", callback_data="admin:partners")],
        ]
    )


def admin_channels_keyboard(channels: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"admin:channel:{channel_id}")]
        for channel_id, label in channels
    ]
    rows.extend(
        [
            [InlineKeyboardButton(text="Добавить канал", callback_data="admin:channel:new")],
            [InlineKeyboardButton(text="В главное меню", callback_data="admin:home")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_partner_choice_keyboard(partners: list[tuple[str, str]]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"admin:channel:owner:{partner_id}")]
        for partner_id, label in partners
    ]
    rows.append([InlineKeyboardButton(text="Отмена", callback_data="admin:channels")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_channel_keyboard(channel_id: str, active: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Выключить" if active else "Включить",
                    callback_data=f"admin:channel:toggle:{channel_id}",
                )
            ],
            [InlineKeyboardButton(text="К каналам", callback_data="admin:channels")],
        ]
    )
