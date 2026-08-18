from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)


def continue_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Продолжить", callback_data="application:begin")],
            [
                InlineKeyboardButton(
                    text="Согласие на обработку данных", callback_data="privacy:show"
                )
            ],
        ]
    )


def consent_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Прочитать согласие", callback_data="consent:show")],
            [InlineKeyboardButton(text="Согласен", callback_data="consent:accept")],
            [InlineKeyboardButton(text="Не согласен", callback_data="consent:decline")],
        ]
    )


def consent_document_keyboard(*, application_started: bool) -> InlineKeyboardMarkup:
    if application_started:
        rows = [
            [InlineKeyboardButton(text="Согласен", callback_data="consent:accept")],
            [InlineKeyboardButton(text="Назад", callback_data="consent:back")],
        ]
    else:
        rows = [[InlineKeyboardButton(text="К началу", callback_data="privacy:back")]]
    return InlineKeyboardMarkup(inline_keyboard=rows)


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


def application_review_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Да, всё верно", callback_data="application:confirm")],
            [InlineKeyboardButton(text="Изменить данные", callback_data="application:edit")],
        ]
    )


def application_edit_keyboard(items: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="Телефон", callback_data="application:edit:phone")]]
    rows.extend(
        [InlineKeyboardButton(text=label, callback_data=f"application:edit:question:{index}")]
        for index, label in items
    )
    rows.append([InlineKeyboardButton(text="Назад", callback_data="application:edit:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def retry_submission_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Повторить сохранение", callback_data="application:retry")]
        ]
    )


def admin_menu_keyboard(mini_app_url: str = "") -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="Сводка", callback_data="admin:stats")],
        [InlineKeyboardButton(text="Последние заявки", callback_data="admin:leads")],
        [
            InlineKeyboardButton(text="Партнёры", callback_data="admin:partners"),
            InlineKeyboardButton(text="Каналы", callback_data="admin:channels"),
        ],
    ]
    if mini_app_url.startswith("https://"):
        rows.insert(
            0,
            [
                InlineKeyboardButton(
                    text="Открыть мини-приложение",
                    web_app=WebAppInfo(url=mini_app_url),
                )
            ],
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cabinet_keyboard(mini_app_url: str = "") -> InlineKeyboardMarkup | None:
    if not mini_app_url.startswith("https://"):
        return None
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Открыть кабинет",
                    web_app=WebAppInfo(url=mini_app_url),
                )
            ]
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


def admin_partner_keyboard(
    partner_id: str,
    active: bool,
    referral_links: list[tuple[str, str]] | None = None,
) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=f"Ссылка: {name}", url=url)]
        for name, url in referral_links or []
    ]
    rows.extend(
        [
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
            [
                InlineKeyboardButton(
                    text="Удалить партнёра",
                    callback_data=f"admin:pd:a:{partner_id}",
                )
            ],
            [InlineKeyboardButton(text="К партнёрам", callback_data="admin:partners")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_partner_delete_keyboard(partner_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Да, удалить",
                    callback_data=f"admin:pd:c:{partner_id}",
                )
            ],
            [
                InlineKeyboardButton(
                    text="Отмена",
                    callback_data=f"admin:partner:{partner_id}",
                )
            ],
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
