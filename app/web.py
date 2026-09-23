import asyncio
import csv
import hashlib
import hmac
import html
import io
import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated
from urllib.parse import parse_qsl
from uuid import UUID

from aiogram import Bot
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, or_, select, true
from sqlalchemy.orm import aliased
from sqlalchemy.sql.elements import ColumnElement
from starlette.middleware.base import RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.bot.keyboards import manager_new_lead_keyboard
from app.config import Settings
from app.database import Database
from app.domain.enums import (
    AccessStatus,
    AssignmentStatus,
    BankExternalStatus,
    BankInternalStatus,
    LeadExternalStatus,
    LeadInternalStatus,
    LeadWorkflowStage,
    PaymentStatus,
    UserRole,
)
from app.domain.operations import DomainError
from app.integrations.bank_rates import BankRateRow, BankRatesGateway
from app.integrations.google_sheets import GoogleSheetsGateway, LeadRegistryRowNotFound
from app.models import (
    Bank,
    BankActivationCondition,
    BankRate,
    Channel,
    DuplicateLeadReview,
    Lead,
    LeadBank,
    LeadDraft,
    Partner,
    Payment,
    User,
)
from app.reports.partner_report import build_partner_report
from app.services.admin_catalog import AdminCatalogService
from app.services.bank_conditions import normalize_bank_name
from app.services.bank_rates import BankRatesService
from app.services.duplicate_reviews import DuplicateReviewService
from app.services.lead_registry import LeadRegistryService
from app.services.lead_workflow import LeadWorkflowService
from app.services.partner_cabinet import partner_cabinet_data, partner_contact
from app.services.telegram_profiles import observe_telegram_profile
from app.services.user_access import UserAccessService
from app.services.workflow import WorkflowService
from app.web_schemas import (
    BankCreate,
    BankUpdate,
    ChannelCreate,
    DuplicateReviewResolve,
    LeadBankCreate,
    LeadBankSelection,
    LeadBankUpdate,
    LeadRewardPaymentConfirm,
    LeadUpdate,
    PartnerAccessUpdate,
    PartnerCreate,
    PartnerUpdate,
    PaymentConfirm,
    PaymentStatusUpdate,
    StaffCreate,
)

ASSETS_DIR = Path(__file__).parent / "web_assets"
DOCUMENTS_DIR = Path(__file__).parent / "documents"
logger = logging.getLogger(__name__)
EXTERNAL_STATUS_LABELS = {
    "new": "Новая",
    "in_progress": "В работе",
    "opening_accounts": "Открытие счетов",
    "partially_completed": "Частично завершена",
    "completed": "Завершена",
    "paused": "На паузе",
    "closed_without_result": "Закрыта без результата",
}
CLIENT_STATUS_LABELS = {
    LeadInternalStatus.NEW: "Заявка принята",
    LeadInternalStatus.MANAGER_ASSIGNED: "Менеджер назначен",
    LeadInternalStatus.AWAITING_FIRST_CONTACT: "Ожидайте связи с менеджером",
    LeadInternalStatus.CONTACTED: "Менеджер связался с вами",
    LeadInternalStatus.AWAITING_DATA: "Ожидаем данные",
    LeadInternalStatus.DATA_RECEIVED: "Данные получены",
    LeadInternalStatus.SELECTING_BANKS: "Выберите банки",
    LeadInternalStatus.PREPARING_APPLICATIONS: "Готовим заявки в банки",
    LeadInternalStatus.APPLICATIONS_SENT: "Заявки отправлены в банки",
    LeadInternalStatus.OPENING_ACCOUNTS: "Открываем счета",
    LeadInternalStatus.PARTIALLY_OPENED: "Часть счетов активирована",
    LeadInternalStatus.ALL_PLANNED_OPENED: "Все запланированные счета активированы",
    LeadInternalStatus.PAUSED: "Заявка поставлена на паузу",
    LeadInternalStatus.NO_RESPONSE: "Менеджер не смог с вами связаться",
    LeadInternalStatus.LEAD_REFUSED: "Заявка отменена",
    LeadInternalStatus.NOT_ELIGIBLE: "Пока не сможем помочь",
    LeadInternalStatus.COMPLETED: "Заявка завершена",
}


def format_reward_amount(amount: Decimal) -> str:
    amount_text = format(amount.normalize(), "f")
    integer, separator, fraction = amount_text.partition(".")
    grouped_integer = f"{int(integer):,}".replace(",", " ")
    fraction = fraction.rstrip("0")
    return (
        f"{grouped_integer},{fraction}" if separator and fraction else grouped_integer
    )


def format_lead_reward_message(bank_name: str, amount: Decimal) -> str:
    formatted_amount = format_reward_amount(amount)
    return (
        '<tg-emoji emoji-id="5357146861880760304">🎉</tg-emoji> '
        "<b>Бонус выплачен!</b>\n\n"
        '<tg-emoji emoji-id="5332455502917949981">🏦</tg-emoji> '
        f"Банк: <b>{html.escape(bank_name)}</b>\n"
        '<tg-emoji emoji-id="5224257782013769471">💰</tg-emoji> '
        f"Сумма бонуса: <b>{formatted_amount} ₽</b>\n\n"
        "<blockquote><i>Спасибо, что выбрали нас!</i></blockquote>"
    )


def format_partner_reward_message(
    application_number: str, bank_name: str, amount: Decimal
) -> str:
    return (
        '<tg-emoji emoji-id="5357146861880760304">🎉</tg-emoji> '
        "<b>Вознаграждение выплачено!</b>\n\n"
        '<tg-emoji emoji-id="5395444784611480792">📝</tg-emoji> '
        f"Заявка: <b>{html.escape(application_number)}</b>\n"
        '<tg-emoji emoji-id="5332455502917949981">🏦</tg-emoji> '
        f"Банк: <b>{html.escape(bank_name)}</b>\n"
        '<tg-emoji emoji-id="5224257782013769471">💰</tg-emoji> '
        f"Сумма выплаты: <b>{format_reward_amount(amount)} ₽</b>"
    )


def lead_cabinet_metrics(lead_banks: list[LeadBank]) -> dict[str, int | Decimal]:
    planned_banks = [
        bank
        for bank in lead_banks
        if bank.external_status in {BankExternalStatus.PLANNED, BankExternalStatus.IN_PROGRESS}
    ]
    return {
        "planned_accounts": len(planned_banks),
        "activated_accounts": sum(
            bank.external_status is BankExternalStatus.OPENED for bank in lead_banks
        ),
        "expected_payout": sum(
            (
                bank.lead_reward_estimate or Decimal("0")
                for bank in lead_banks
                if bank.lead_reward_paid_at is None
                and bank.external_status
                not in {BankExternalStatus.NOT_OPENED, BankExternalStatus.WILL_NOT_OPEN}
            ),
            start=Decimal("0"),
        ),
        "paid_total": sum(
            (
                bank.lead_reward_fact or Decimal("0")
                for bank in lead_banks
                if bank.lead_reward_paid_at is not None
            ),
            start=Decimal("0"),
        ),
    }


def online_bank_info(bank_name: str, online_text: str) -> dict[str, object]:
    normalized = online_text.strip().casefold()
    available = normalized.startswith("да") or "можно онлайн" in normalized
    is_ozon = any(name in bank_name.casefold() for name in {"озон", "ozon"})
    help_text = ""
    if available:
        help_text = (
            "Можно оформить онлайн даже без электронной подписи"
            if is_ozon
            else "Можно открыть онлайн, если есть КЭП (электронная подпись). "
            "Оформить КЭП можно бесплатно в офисе Сбера или ВТБ после открытия счёта"
        )
    return {"online_available": available, "online_help": help_text}


def lead_bank_sort_key(item: dict[str, object]) -> tuple[int, Decimal, int, str]:
    action = str(item.get("action_text") or "").casefold()
    conditions = (
        ("откры",),
        ("тариф",),
        ("холд", "удерж"),
        ("оборот",),
    )
    priority = next(
        (
            index
            for index, markers in enumerate(conditions)
            if any(marker in action for marker in markers)
        ),
        len(conditions),
    )
    payout = Decimal(str(item.get("lead_payout") or "0"))
    order_value = item.get("order")
    order = order_value if isinstance(order_value, int) else int(str(order_value or 0))
    return (
        priority,
        -payout,
        order,
        str(item.get("bank") or "").casefold(),
    )


def public_referral_links(
    bot_usernames: tuple[str, ...], start_parameter: str, fallback: str = ""
) -> list[dict[str, str]]:
    if bot_usernames:
        username = bot_usernames[-1].lstrip("@")
        return [
            {
                "bot": f"@{username}",
                "url": f"https://t.me/{username}?start={start_parameter}",
            }
        ]
    return [{"bot": "Telegram", "url": fallback}] if fallback else []


def build_mini_app_html() -> str:
    markup = (ASSETS_DIR / "index.html").read_text(encoding="utf-8")
    styles = (ASSETS_DIR / "styles.css").read_text(encoding="utf-8")
    script = (ASSETS_DIR / "app.js").read_text(encoding="utf-8")
    style_marker = (
        '<link rel="stylesheet" href="/assets/styles.css?v=20260829-01" data-inline="styles" />'
    )
    script_marker = '<script src="/assets/app.js?v=20260829-01" data-inline="app"></script>'
    if style_marker not in markup or script_marker not in markup:
        raise RuntimeError("Не найдены точки встраивания файлов мини-приложения")
    return markup.replace(style_marker, f"<style>{styles}</style>", 1).replace(
        script_marker, f"<script>{script}</script>", 1
    )


@dataclass(frozen=True)
class MiniAppUser:
    id: str
    database_id: UUID | None
    name: str
    role: UserRole
    partner_id: UUID | None = None
    lead_id: UUID | None = None


def validate_telegram_init_data(
    raw_data: str, bot_token: str, max_age: int = 86_400
) -> dict[str, object]:
    values = dict(parse_qsl(raw_data, keep_blank_values=True))
    received_hash = values.pop("hash", "")
    if not received_hash:
        raise ValueError("Telegram не передал подпись")
    data_check_string = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated_hash, received_hash):
        raise ValueError("Подпись Telegram не прошла проверку")
    try:
        auth_date = int(values["auth_date"])
    except (KeyError, ValueError) as error:
        raise ValueError("Telegram не передал время авторизации") from error
    if abs(time.time() - auth_date) > max_age:
        raise ValueError("Авторизация Telegram устарела")
    try:
        user = json.loads(values["user"])
    except (KeyError, json.JSONDecodeError) as error:
        raise ValueError("Telegram не передал пользователя") from error
    if not isinstance(user, dict) or not isinstance(user.get("id"), int):
        raise ValueError("Некорректные данные пользователя Telegram")
    return user


def validate_telegram_init_data_with_tokens(
    raw_data: str, bot_tokens: tuple[str, ...], max_age: int = 86_400
) -> dict[str, object]:
    if not bot_tokens:
        raise ValueError("Не настроен токен Telegram-бота")
    for token in bot_tokens:
        try:
            return validate_telegram_init_data(raw_data, token, max_age=max_age)
        except ValueError as error:
            if "Подпись Telegram" not in str(error):
                raise
    raise ValueError("Подпись Telegram не прошла проверку")


def format_user_name(user: User | None) -> str:
    if user is None:
        return "Не назначен"
    if user.telegram_username:
        return f"@{user.telegram_username}"
    return user.telegram_id or "Ожидает входа"


def telegram_contact_url(user: User | None) -> str:
    if user is None:
        return ""
    if user.telegram_username:
        return f"https://t.me/{user.telegram_username}"
    return f"tg://user?id={user.telegram_id}" if user.telegram_id else ""


def serialize_lead_bank(
    lead_bank: LeadBank,
    bank: Bank,
    payment: Payment | None,
    role: UserRole,
    rate: BankRate | None = None,
) -> dict[str, object]:
    online_text = rate.online_text if rate is not None else "Уточняется"
    result: dict[str, object] = {
        "id": str(lead_bank.id),
        "bank_id": str(bank.id),
        "bank": bank.name,
        "status": (
            lead_bank.external_status.value
            if role is UserRole.PARTNER
            else lead_bank.internal_status.value
        ),
        "opened_at": lead_bank.opened_at.isoformat() if lead_bank.opened_at else None,
        "payment_status": (payment.status.value if payment else PaymentStatus.NOT_CALCULATED.value),
        "online_text": online_text,
        **online_bank_info(bank.name, online_text),
    }
    if role is UserRole.PARTNER:
        result.update(
            {
                "reward_estimate": (
                    str(lead_bank.partner_reward_estimate)
                    if lead_bank.partner_reward_estimate is not None
                    else None
                ),
                "reward_fact": (
                    str(lead_bank.partner_reward_fact)
                    if lead_bank.partner_reward_fact is not None
                    else None
                ),
                "lead_reward_estimate": (
                    str(lead_bank.lead_reward_estimate)
                    if lead_bank.lead_reward_estimate is not None
                    else None
                ),
                "paid_at": payment.paid_at.isoformat() if payment and payment.paid_at else None,
            }
        )
    else:
        result.update(
            {
                "external_status": lead_bank.external_status.value,
                "close_reason": lead_bank.close_reason or "",
                "offered_to_lead": lead_bank.offered_to_lead,
                "selected_by_lead": lead_bank.selected_by_lead,
                "lead_reward_paid": lead_bank.lead_reward_paid_at is not None,
            }
        )
        if role is UserRole.ADMIN:
            result.update(
                {
                    "payment_id": str(payment.id) if payment else None,
                    "income_estimate": (
                        str(lead_bank.bank_income_estimate)
                        if lead_bank.bank_income_estimate is not None
                        else None
                    ),
                    "income_fact": (
                        str(lead_bank.bank_income_fact)
                        if lead_bank.bank_income_fact is not None
                        else None
                    ),
                    "percent": (
                        str(lead_bank.partner_percent_snapshot)
                        if lead_bank.partner_percent_snapshot is not None
                        else None
                    ),
                    "reward_estimate": (
                        str(lead_bank.partner_reward_estimate)
                        if lead_bank.partner_reward_estimate is not None
                        else None
                    ),
                    "reward_fact": (
                        str(lead_bank.partner_reward_fact)
                        if lead_bank.partner_reward_fact is not None
                        else None
                    ),
                    "lead_reward_estimate": (
                        str(lead_bank.lead_reward_estimate)
                        if lead_bank.lead_reward_estimate is not None
                        else None
                    ),
                    "lead_reward_fact": (
                        str(lead_bank.lead_reward_fact)
                        if lead_bank.lead_reward_fact is not None
                        else None
                    ),
                    "lead_reward_paid_at": (
                        lead_bank.lead_reward_paid_at.isoformat()
                        if lead_bank.lead_reward_paid_at
                        else None
                    ),
                    "lead_reward_paid_separately": lead_bank.lead_reward_paid_separately,
                    "registry_number": payment.registry_number if payment else None,
                    "team_profit_estimate": (
                        str(lead_bank.team_profit_estimate)
                        if lead_bank.team_profit_estimate is not None
                        else None
                    ),
                    "team_profit_fact": (
                        str(lead_bank.team_profit_fact)
                        if lead_bank.team_profit_fact is not None
                        else None
                    ),
                }
            )
    return result


def create_web_app(
    database: Database,
    settings: Settings,
    bot: Bot | None = None,
    additional_bots: tuple[Bot, ...] = (),
    bot_usernames: tuple[str, ...] = (),
) -> FastAPI:
    app = FastAPI(title="РКО", docs_url=None, redoc_url=None)
    mini_app_html = build_mini_app_html()
    notification_bots = ((bot,) if bot is not None else ()) + additional_bots
    lead_registry_gateway: GoogleSheetsGateway | None = None
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")
    app.mount("/documents", StaticFiles(directory=DOCUMENTS_DIR), name="documents")

    def referral_links(start_parameter: str, fallback: str = "") -> list[dict[str, str]]:
        return public_referral_links(bot_usernames, start_parameter, fallback)

    @app.middleware("http")
    async def configure_mini_app_cache(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        if request.url.path == "/":
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
        elif request.url.path.startswith("/assets/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif request.url.path.startswith("/documents/"):
            response.headers["Cache-Control"] = "public, max-age=300"
        return response

    async def current_user(
        telegram_init_data: str = Header(default="", alias="X-Telegram-Init-Data"),
    ) -> MiniAppUser:
        if telegram_init_data:
            try:
                telegram_user = validate_telegram_init_data_with_tokens(
                    telegram_init_data,
                    settings.bot_tokens,
                )
                telegram_id = str(telegram_user["id"])
                username = str(telegram_user.get("username") or "") or None
                name = str(telegram_user.get("first_name") or username or "Пользователь")
            except ValueError as error:
                raise HTTPException(status_code=401, detail=str(error)) from error
        elif settings.mini_app_local_user_id:
            telegram_id = settings.mini_app_local_user_id
            username = None
            name = "Локальный администратор"
        else:
            raise HTTPException(status_code=401, detail="Откройте кабинет кнопкой в Telegram-боте")

        role = await UserAccessService(database, settings).resolve_role(telegram_id, username)
        async with database.session() as session:
            user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
            lead = await session.scalar(
                select(Lead)
                .where(Lead.telegram_id == telegram_id, Lead.archived_at.is_(None))
                .order_by(Lead.application_at.desc())
                .limit(1)
            )
            draft = await session.scalar(
                select(LeadDraft).where(LeadDraft.telegram_id == telegram_id)
            )
        if user is not None and user.access_status is not AccessStatus.ACTIVE:
            raise HTTPException(status_code=403, detail="Доступ отключён")
        if role in {None, UserRole.LEAD}:
            if lead is None:
                raise HTTPException(
                    status_code=403,
                    detail=(
                        "Сначала ответьте на вопросы в боте. После заполнения анкеты "
                        "кабинет станет доступен."
                        if draft is not None
                        else "Кабинет не подключён. Отправьте /start боту"
                    ),
                )
            return MiniAppUser(
                telegram_id,
                None,
                lead.display_name,
                UserRole.LEAD,
                lead_id=lead.id,
            )
        if role not in {UserRole.ADMIN, UserRole.MANAGER, UserRole.PARTNER} or user is None:
            raise HTTPException(
                status_code=403,
                detail="Кабинет не подключён. Отправьте /start боту",
            )
        partner_id = None
        if role is UserRole.PARTNER:
            async with database.session() as session:
                partner = await session.scalar(
                    select(Partner).where(
                        Partner.telegram_user_id == user.id,
                        Partner.active.is_(True),
                    )
                )
            if partner is None:
                raise HTTPException(
                    status_code=403,
                    detail="Партнёрский кабинет не подключён. Обратись к администратору",
                )
            partner_id = partner.id
            name = partner.name
        return MiniAppUser(telegram_id, user.id, name, role, partner_id)

    def lead_scope(user: MiniAppUser) -> ColumnElement[bool]:
        if user.role is UserRole.PARTNER:
            return (
                (Lead.partner_id == user.partner_id)
                & (Lead.assignment_status == AssignmentStatus.CONFIRMED)
                & Lead.archived_at.is_(None)
            )
        if user.role is UserRole.MANAGER:
            return (Lead.manager_id == user.database_id) & Lead.archived_at.is_(None)
        return Lead.archived_at.is_(None)

    def require_operational_user(user: MiniAppUser) -> None:
        if user.role is UserRole.LEAD:
            raise HTTPException(status_code=403, detail="Раздел недоступен клиенту")

    def require_lead(user: MiniAppUser) -> UUID:
        if user.role is not UserRole.LEAD or user.lead_id is None:
            raise HTTPException(status_code=403, detail="Раздел доступен клиенту")
        return user.lead_id

    def require_admin(user: MiniAppUser) -> UUID:
        if user.role is not UserRole.ADMIN or user.database_id is None:
            raise HTTPException(status_code=403, detail="Раздел доступен администратору")
        return user.database_id

    def require_partner(user: MiniAppUser) -> UUID:
        if user.role is not UserRole.PARTNER or user.partner_id is None:
            raise HTTPException(status_code=403, detail="Раздел доступен партнёру")
        return user.partner_id

    def require_employee(user: MiniAppUser) -> UUID:
        if user.role not in {UserRole.ADMIN, UserRole.MANAGER} or user.database_id is None:
            raise HTTPException(status_code=403, detail="Раздел доступен сотруднику")
        return user.database_id

    def domain_error(error: DomainError) -> HTTPException:
        return HTTPException(status_code=400, detail=str(error))

    def require_bank_rates_sheet() -> BankRatesGateway:
        if not settings.bank_rates_enabled:
            raise HTTPException(
                status_code=503,
                detail="Таблица банков не подключена. Проверьте настройки Google Sheets",
            )
        return BankRatesGateway(
            settings.bank_rates_sheet_id,
            settings.bank_rates_worksheet,
            settings.google_service_account_file,
        )

    async def registry_gateway() -> GoogleSheetsGateway:
        nonlocal lead_registry_gateway
        if not settings.sheets_enabled:
            raise RuntimeError("Google Sheets не подключена")
        if lead_registry_gateway is None:
            lead_registry_gateway = await asyncio.to_thread(
                GoogleSheetsGateway,
                settings.google_sheet_id,
                settings.google_service_account_file,
            )
        return lead_registry_gateway

    async def write_bank_rate(
        payload: BankCreate | BankUpdate,
        *,
        original_offer_code: str | None = None,
    ) -> BankRate:
        row = BankRateRow(
            offer_code=payload.offer_code.strip(),
            bank_name=payload.name.strip(),
            online_text=payload.online_text.strip() or "Нет",
            base_payout=payload.base_payout,
            lead_payout=payload.lead_payout,
            lead_payout_paid_separately=payload.lead_payout_paid_separately,
            active=payload.active,
            display_order=payload.display_order,
            source_row=0,
        )
        gateway: BankRatesGateway | None = None
        rate_write = None
        write_started = False
        try:
            gateway = await asyncio.to_thread(require_bank_rates_sheet)
            rate_write = await asyncio.to_thread(
                gateway.plan_upsert,
                row,
                original_offer_code=original_offer_code,
            )
            write_started = True
            rows = await asyncio.to_thread(gateway.apply, rate_write)
            await BankRatesService(database).replace_all(rows)
        except HTTPException:
            raise
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except Exception as error:
            if write_started and gateway is not None and rate_write is not None:
                try:
                    restored_rows = await asyncio.to_thread(gateway.rollback, rate_write)
                    await BankRatesService(database).replace_all(restored_rows)
                except Exception:
                    logger.exception("Failed to roll back Google Sheets bank rate")
            logger.exception("Failed to write bank data")
            raise HTTPException(
                status_code=503,
                detail="Не удалось сохранить банк. Попробуйте ещё раз позже.",
            ) from error
        async with database.session() as db_session:
            rate = await db_session.scalar(
                select(BankRate).where(BankRate.offer_code == row.offer_code)
            )
        if rate is None:
            raise HTTPException(status_code=500, detail="Банк записан, но не синхронизирован")
        return rate

    async def notify_partner(
        lead_id: UUID, text: str, *, parse_mode: str | None = None
    ) -> None:
        if not notification_bots:
            return
        async with database.session() as db_session:
            telegram_id = await db_session.scalar(
                select(User.telegram_id)
                .join(Partner, Partner.telegram_user_id == User.id)
                .join(Lead, Lead.partner_id == Partner.id)
                .where(
                    Lead.id == lead_id,
                    Lead.assignment_status == AssignmentStatus.CONFIRMED,
                    Partner.active.is_(True),
                    User.access_status == AccessStatus.ACTIVE,
                )
            )
        if telegram_id is None:
            return
        for current_bot in notification_bots:
            try:
                await current_bot.send_message(
                    chat_id=int(telegram_id), text=text, parse_mode=parse_mode
                )
            except Exception:
                logger.exception(
                    "Failed to notify partner for lead %s via bot %s",
                    lead_id,
                    current_bot.id,
                )

    async def notify_client(
        lead_id: UUID, text: str, *, parse_mode: str | None = None
    ) -> None:
        if not notification_bots:
            return
        async with database.session() as db_session:
            telegram_id = await db_session.scalar(
                select(Lead.telegram_id).where(Lead.id == lead_id)
            )
        if telegram_id is None:
            return
        for current_bot in notification_bots:
            try:
                await current_bot.send_message(
                    chat_id=int(telegram_id), text=text, parse_mode=parse_mode
                )
            except Exception:
                logger.exception(
                    "Failed to notify client for lead %s via bot %s",
                    lead_id,
                    current_bot.id,
                )

    async def notify_client_status(lead_id: UUID, status: LeadInternalStatus) -> None:
        await notify_client(
            lead_id,
            "Статус вашей заявки изменён: "
            f"{CLIENT_STATUS_LABELS[status]}. "
            "Актуальная информация доступна в кабинете.",
        )

    async def notify_manager_new_lead(lead: Lead, manager: User | None) -> None:
        if (
            not notification_bots
            or manager is None
            or manager.telegram_id is None
            or manager.access_status is not AccessStatus.ACTIVE
        ):
            return
        text = (
            f"Новая заявка {lead.short_id}\n\n"
            f"Клиент: {lead.display_name}\n"
            "Клиент выбрал банки. Откройте заявку, чтобы взять её в работу."
        )
        for current_bot in notification_bots:
            try:
                await current_bot.send_message(
                    chat_id=int(manager.telegram_id),
                    text=text,
                    reply_markup=manager_new_lead_keyboard(str(lead.id)),
                )
            except Exception:
                logger.exception(
                    "Failed to notify manager %s about lead %s via bot %s",
                    manager.id,
                    lead.id,
                    current_bot.id,
                )

    @app.get("/", include_in_schema=False)
    async def index() -> HTMLResponse:
        return HTMLResponse(mini_app_html)

    @app.get("/api/session")
    async def session(
        user: Annotated[MiniAppUser, Depends(current_user)],
        request: Request,
    ) -> dict[str, object]:
        if request.headers.get("X-Telegram-Init-Data"):
            username = None
            observed_at = datetime.fromtimestamp(
                int(dict(parse_qsl(request.headers["X-Telegram-Init-Data"])).get("auth_date", "0")),
                UTC,
            )
            telegram_user = validate_telegram_init_data_with_tokens(
                request.headers["X-Telegram-Init-Data"], settings.bot_tokens
            )
            username = str(telegram_user.get("username") or "") or None
            live_profile = False
            for current_bot in notification_bots:
                try:
                    chat = await asyncio.wait_for(current_bot.get_chat(int(user.id)), timeout=5)
                except Exception:
                    continue
                username = chat.username
                observed_at = datetime.now(UTC)
                live_profile = True
                break
            if live_profile or (datetime.now(UTC) - observed_at).total_seconds() <= 300:
                try:
                    await observe_telegram_profile(
                        database, notification_bots, user.id, username, observed_at
                    )
                except Exception:
                    logger.exception("Could not update Telegram username on miniapp entry")
        google_sheet_url = ""
        bank_conditions_sheet_url = ""
        bank_rates_sheet_url = ""
        if user.role is UserRole.ADMIN and settings.google_sheet_id:
            google_sheet_url = (
                f"https://docs.google.com/spreadsheets/d/{settings.google_sheet_id}/edit"
            )
        if user.role is UserRole.ADMIN and settings.bank_conditions_sheet_id:
            bank_conditions_sheet_url = (
                f"https://docs.google.com/spreadsheets/d/{settings.bank_conditions_sheet_id}/edit"
            )
        if user.role is UserRole.ADMIN and settings.bank_rates_sheet_id:
            bank_rates_sheet_url = (
                f"https://docs.google.com/spreadsheets/d/{settings.bank_rates_sheet_id}/edit"
            )
        result: dict[str, object] = {
            "name": user.name,
            "role": user.role.value,
            "telegram_id": user.id,
            "google_sheet_url": google_sheet_url,
            "bank_conditions_sheet_url": bank_conditions_sheet_url,
            "bank_rates_sheet_url": bank_rates_sheet_url,
        }
        if user.role is UserRole.PARTNER and user.partner_id is not None:
            result["contact"] = await partner_contact(database, user.partner_id)
        return result

    @app.get("/api/lead/session")
    async def lead_session(
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> dict[str, str]:
        lead_id = require_lead(user)
        async with database.session() as db_session:
            lead = await db_session.get(Lead, lead_id)
        if lead is None:
            raise HTTPException(status_code=404, detail="Заявка не найдена")
        return {
            "name": lead.display_name,
            "role": UserRole.LEAD.value,
            "short_id": lead.short_id,
        }

    @app.get("/api/lead/application")
    async def lead_application(
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> dict[str, object]:
        lead_id = require_lead(user)
        async with database.session() as db_session:
            lead = await db_session.get(Lead, lead_id)
            admin_id = lead.primary_admin_id if lead is not None else None
            admin = await db_session.get(User, admin_id) if admin_id is not None else None
            manager_id = (
                lead.manager_id
                if lead is not None and lead.bank_selection_submitted_at is not None
                else None
            )
            manager = await db_session.get(User, manager_id) if manager_id is not None else None
            lead_banks = list(
                await db_session.scalars(
                    select(LeadBank).where(
                        LeadBank.lead_id == lead_id,
                        LeadBank.selected_by_lead.is_(True),
                    )
                )
            )
        if lead is None:
            raise HTTPException(status_code=404, detail="Заявка не найдена")
        metrics = lead_cabinet_metrics(lead_banks)
        return {
            "short_id": lead.short_id,
            "name": lead.display_name,
            "date": lead.application_at.isoformat(),
            "updated": lead.last_updated_at.isoformat(),
            "status": lead.external_status.value,
            "workflow_stage": lead.workflow_stage.value,
            "is_repeat": lead.is_repeat,
            "admin": format_user_name(admin),
            "admin_url": telegram_contact_url(admin),
            "manager": format_user_name(manager),
            "manager_url": telegram_contact_url(manager),
            "metrics": {
                **metrics,
                "expected_payout": str(metrics["expected_payout"]),
                "paid_total": str(metrics["paid_total"]),
            },
        }

    @app.get("/api/lead/banks")
    async def lead_banks(
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> list[dict[str, object]]:
        lead_id = require_lead(user)
        async with database.session() as db_session:
            lead = await db_session.get(Lead, lead_id)
            if lead is None:
                raise HTTPException(status_code=404, detail="Заявка не найдена")
            bank_scope = [
                LeadBank.lead_id == lead_id,
                LeadBank.offered_to_lead.is_(True),
            ]
            bank_rows = list(
                await db_session.execute(
                    select(LeadBank, Bank)
                    .join(Bank, Bank.id == LeadBank.bank_id)
                    .where(*bank_scope)
                    .order_by(Bank.display_order, LeadBank.planned_at)
                )
            )
            conditions = list(await db_session.scalars(select(BankActivationCondition)))
            rates = list(await db_session.scalars(select(BankRate)))
        conditions_by_name = {condition.normalized_bank_name: condition for condition in conditions}
        rates_by_bank = {rate.bank_id: rate for rate in rates}
        result: list[dict[str, object]] = []
        for lead_bank, bank in bank_rows:
            condition = conditions_by_name.get(normalize_bank_name(bank.name))
            online_text = (
                rates_by_bank[bank.id].online_text if bank.id in rates_by_bank else "Уточняется"
            )
            result.append(
                {
                    "bank": bank.name,
                    "bank_id": str(bank.id),
                    "status": lead_bank.external_status.value,
                    "refusal_type": (
                        lead_bank.internal_status.value
                        if lead_bank.internal_status
                        in {
                            BankInternalStatus.BANK_REJECTED,
                            BankInternalStatus.CLIENT_REFUSED,
                        }
                        else None
                    ),
                    "selected": lead_bank.selected_by_lead,
                    "selection_locked": lead_bank.selected_by_lead is True,
                    "online_text": online_text,
                    **online_bank_info(bank.name, online_text),
                    "lead_payout": (
                        str(lead_bank.lead_reward_estimate)
                        if lead_bank.lead_reward_estimate is not None
                        else "0"
                    ),
                    "lead_payout_paid_separately": lead_bank.lead_reward_paid_separately,
                    "lead_payment_status": (
                        "paid" if lead_bank.lead_reward_paid_at is not None else "pending"
                    ),
                    "action_text": (
                        condition.action_text if condition is not None and condition.active else ""
                    ),
                    "payout_text": (
                        condition.payout_text
                        if condition is not None and condition.active
                        else "Уточняется"
                    ),
                    "order": (
                        condition.display_order if condition is not None else bank.display_order
                    ),
                    "updated": lead_bank.last_updated_at.isoformat(),
                }
            )
        result.sort(key=lead_bank_sort_key)
        return result

    @app.post("/api/lead/banks/selection")
    async def submit_lead_bank_selection(
        payload: LeadBankSelection,
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> dict[str, str]:
        lead_id = require_lead(user)
        async with database.session() as db_session:
            previous_stage = await db_session.scalar(
                select(Lead.workflow_stage).where(Lead.id == lead_id)
            )
        try:
            lead = await LeadWorkflowService(database).submit_bank_selection(
                lead_id=lead_id,
                selected_bank_ids=set(payload.bank_ids),
            )
        except DomainError as error:
            raise domain_error(error) from error
        async with database.session() as db_session:
            manager = await db_session.get(User, lead.manager_id) if lead.manager_id else None
        if previous_stage is LeadWorkflowStage.AWAITING_CLIENT_SELECTION:
            await notify_manager_new_lead(lead, manager)
        await notify_client(
            lead.id,
            f"Спасибо, выбор отправлен. Менеджер сопровождения: {format_user_name(manager)}. "
            "Скоро с вами свяжутся. "
            "Для сопровождения создадим отдельную группу: там будут все инструкции, "
            "и там можно будет задать любые вопросы.",
        )
        return {"id": str(lead.id), "workflow_stage": lead.workflow_stage.value}

    @app.get("/api/partner/cabinet")
    async def partner_cabinet(
        user: Annotated[MiniAppUser, Depends(current_user)],
        date_from: date | None = None,
        date_to: date | None = None,
        channel_id: UUID | None = None,
        lead_status: LeadExternalStatus | None = None,
        payment_status: PaymentStatus | None = None,
        search: str = "",
    ) -> dict[str, object]:
        partner_id = require_partner(user)
        if date_from and date_to and date_from > date_to:
            raise HTTPException(status_code=400, detail="Начало периода позже окончания")
        data = await partner_cabinet_data(
            database,
            partner_id,
            date_from=date_from,
            date_to=date_to,
            channel_id=channel_id,
            lead_status=lead_status,
            payment_status=payment_status,
            search=search,
        )
        return {**data, "contact": await partner_contact(database, partner_id)}

    @app.get("/api/partner/report.xlsx")
    async def partner_report(
        user: Annotated[MiniAppUser, Depends(current_user)],
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> StreamingResponse:
        partner_id = require_partner(user)
        if date_from and date_to and date_from > date_to:
            raise HTTPException(status_code=400, detail="Начало периода позже окончания")
        report = await build_partner_report(
            database,
            partner_id,
            date_from=date_from,
            date_to=date_to,
        )
        headers = {"Content-Disposition": 'attachment; filename="rko-partner-report.xlsx"'}
        return StreamingResponse(
            iter([report]),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers=headers,
        )

    @app.get("/api/dashboard")
    async def dashboard(
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> dict[str, int]:
        require_operational_user(user)
        scope = lead_scope(user)
        active_statuses = {
            LeadInternalStatus.NEW,
            LeadInternalStatus.MANAGER_ASSIGNED,
            LeadInternalStatus.AWAITING_FIRST_CONTACT,
            LeadInternalStatus.CONTACTED,
            LeadInternalStatus.AWAITING_DATA,
            LeadInternalStatus.DATA_RECEIVED,
            LeadInternalStatus.SELECTING_BANKS,
            LeadInternalStatus.PREPARING_APPLICATIONS,
            LeadInternalStatus.APPLICATIONS_SENT,
            LeadInternalStatus.OPENING_ACCOUNTS,
            LeadInternalStatus.PARTIALLY_OPENED,
        }
        async with database.session() as db_session:
            total_scope = scope
            if user.role is UserRole.MANAGER:
                total_scope = total_scope & Lead.workflow_stage.in_(
                    {
                        LeadWorkflowStage.AWAITING_MANAGER,
                        LeadWorkflowStage.MANAGER_PROCESSING,
                    }
                )
            total = await db_session.scalar(
                select(func.count()).select_from(Lead).where(total_scope)
            )
            if user.role is UserRole.MANAGER:
                new = await db_session.scalar(
                    select(func.count())
                    .select_from(Lead)
                    .where(
                        total_scope,
                        Lead.bank_selection_submitted_at.is_not(None),
                        Lead.manager_started_at.is_(None),
                    )
                )
                active = await db_session.scalar(
                    select(func.count())
                    .select_from(Lead)
                    .where(total_scope, Lead.manager_started_at.is_not(None))
                )
            else:
                new = await db_session.scalar(
                    select(func.count())
                    .select_from(Lead)
                    .where(scope, Lead.internal_status == LeadInternalStatus.NEW)
                )
                active = await db_session.scalar(
                    select(func.count())
                    .select_from(Lead)
                    .where(scope, Lead.internal_status.in_(active_statuses))
                )
            unresolved = await db_session.scalar(
                select(func.count())
                .select_from(Lead)
                .where(scope, Lead.assignment_status == AssignmentStatus.UNRESOLVED)
            )
            duplicates = (
                await db_session.scalar(
                    select(func.count())
                    .select_from(DuplicateLeadReview)
                    .where(DuplicateLeadReview.review_status == "pending")
                )
                if user.role is UserRole.ADMIN
                else 0
            )
            repeats = await db_session.scalar(
                select(func.count()).select_from(Lead).where(scope, Lead.is_repeat.is_(True))
            )
        return {
            "total": total or 0,
            "new": new or 0,
            "active": active or 0,
            "unresolved": unresolved or 0,
            "duplicates": duplicates or 0,
            "repeats": repeats or 0,
        }

    @app.get("/api/duplicate-reviews")
    async def duplicate_reviews(
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> list[dict[str, object]]:
        require_admin(user)
        async with database.session() as db_session:
            rows = await db_session.execute(
                select(DuplicateLeadReview, Lead)
                .outerjoin(Lead, Lead.id == DuplicateLeadReview.original_lead_id)
                .where(DuplicateLeadReview.review_status == "pending")
                .order_by(DuplicateLeadReview.created_at)
            )
            return [
                {
                    "id": str(review.id),
                    "telegram_id": review.telegram_id,
                    "username": (
                        f"@{review.telegram_username}" if review.telegram_username else ""
                    ),
                    "name": review.questionnaire_answers.get("full_name") or review.display_name,
                    "phone": review.phone,
                    "date": review.created_at.isoformat(),
                    "referral_code": review.referral_code or "",
                    "answers": review.questionnaire_answers,
                    "original": (
                        {
                            "id": str(original.id),
                            "short_id": original.short_id,
                            "name": original.display_name,
                            "username": (
                                f"@{original.telegram_username}"
                                if original.telegram_username
                                else ""
                            ),
                            "phone": original.phone,
                        }
                        if original
                        else None
                    ),
                }
                for review, original in rows
            ]

    @app.post("/api/duplicate-reviews/{review_id}/resolve")
    async def resolve_duplicate_review(
        review_id: UUID,
        payload: DuplicateReviewResolve,
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> dict[str, str | None]:
        admin_id = require_admin(user)
        try:
            review, lead = await DuplicateReviewService(database).resolve(
                actor_role=user.role,
                actor_id=admin_id,
                review_id=review_id,
                resolution=payload.resolution,
            )
        except DomainError as error:
            raise domain_error(error) from error
        return {
            "id": str(review.id),
            "resolution": review.resolution.value if review.resolution else None,
            "lead_id": str(lead.id) if lead else None,
        }

    @app.get("/api/leads")
    async def leads(
        user: Annotated[MiniAppUser, Depends(current_user)],
        mine: bool = False,
    ) -> list[dict[str, object]]:
        require_operational_user(user)
        scope = lead_scope(user)
        if user.role is UserRole.MANAGER:
            scope = (
                scope
                & Lead.workflow_stage.in_(
                    {
                        LeadWorkflowStage.AWAITING_MANAGER,
                        LeadWorkflowStage.MANAGER_PROCESSING,
                    }
                )
                & Lead.bank_selection_submitted_at.is_not(None)
                & (
                    Lead.manager_started_at.is_not(None)
                    if mine
                    else Lead.manager_started_at.is_(None)
                )
            )
        async with database.session() as db_session:
            result = await db_session.scalars(
                select(Lead).where(scope).order_by(Lead.application_at.desc()).limit(1000)
            )
            items = list(result)
        response: list[dict[str, object]] = []
        for lead in items:
            item: dict[str, object] = {
                "id": str(lead.id),
                "short_id": lead.short_id,
                "name": lead.display_name,
                "status": (
                    lead.external_status.value
                    if user.role is UserRole.PARTNER
                    else lead.internal_status.value
                ),
                "date": lead.application_at.isoformat(),
                "is_repeat": lead.is_repeat,
                "payment_status": lead.payment_status.value,
            }
            if user.role is not UserRole.PARTNER:
                item["username"] = f"@{lead.telegram_username}" if lead.telegram_username else ""
                item["workflow_stage"] = lead.workflow_stage.value
                item["phone"] = lead.phone
                item["source"] = lead.assignment_status.value
                item["manager_id"] = str(lead.manager_id) if lead.manager_id else None
                item["manager_started"] = lead.manager_started_at is not None
                item["primary_admin_id"] = (
                    str(lead.primary_admin_id) if lead.primary_admin_id else None
                )
                item["source_partner_id"] = str(lead.partner_id) if lead.partner_id else None
                item["source_channel_id"] = str(lead.channel_id) if lead.channel_id else None
            response.append(item)
        return response

    @app.get("/api/reports/leads.csv")
    async def leads_report(
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> StreamingResponse:
        require_operational_user(user)
        async with database.session() as db_session:
            lead_items = list(
                await db_session.scalars(
                    select(Lead).where(lead_scope(user)).order_by(Lead.application_at.desc())
                )
            )
            rows: list[list[object]] = []
            for lead in lead_items:
                channel = (
                    await db_session.get(Channel, lead.channel_id) if lead.channel_id else None
                )
                lead_bank_items = list(
                    await db_session.scalars(select(LeadBank).where(LeadBank.lead_id == lead.id))
                )
                lead_banks: list[LeadBank | None] = [*lead_bank_items]
                if not lead_banks:
                    lead_banks = [None]
                for lead_bank in lead_banks:
                    bank = await db_session.get(Bank, lead_bank.bank_id) if lead_bank else None
                    payment = (
                        await db_session.scalar(
                            select(Payment).where(Payment.lead_bank_id == lead_bank.id)
                        )
                        if lead_bank
                        else None
                    )
                    if user.role is UserRole.PARTNER:
                        rows.append(
                            [
                                lead.short_id,
                                lead.application_at.date().isoformat(),
                                f"{'Повторная · ' if lead.is_repeat else ''}"
                                f"{lead.external_status.value}",
                                channel.name if channel else "Прямой",
                                bank.name if bank else "",
                                lead_bank.external_status.value if lead_bank else "",
                                (lead_bank.partner_reward_fact or "") if lead_bank else "",
                                (
                                    payment.status.value
                                    if payment
                                    else PaymentStatus.NOT_CALCULATED.value
                                ),
                            ]
                        )
                    elif user.role is UserRole.ADMIN:
                        manager = (
                            await db_session.get(User, lead.manager_id) if lead.manager_id else None
                        )
                        rows.append(
                            [
                                lead.short_id,
                                lead.display_name,
                                lead.phone,
                                lead.application_at.date().isoformat(),
                                f"{'Повторная · ' if lead.is_repeat else ''}"
                                f"{lead.internal_status.value}",
                                channel.name if channel else "Прямой",
                                format_user_name(manager),
                                bank.name if bank else "",
                                lead_bank.internal_status.value if lead_bank else "",
                                (lead_bank.bank_income_fact or "") if lead_bank else "",
                                (lead_bank.partner_reward_fact or "") if lead_bank else "",
                                (
                                    payment.status.value
                                    if payment
                                    else PaymentStatus.NOT_CALCULATED.value
                                ),
                            ]
                        )
                    else:
                        rows.append(
                            [
                                lead.short_id,
                                lead.display_name,
                                lead.phone,
                                lead.application_at.date().isoformat(),
                                f"{'Повторная · ' if lead.is_repeat else ''}"
                                f"{lead.internal_status.value}",
                                bank.name if bank else "",
                                lead_bank.internal_status.value if lead_bank else "",
                            ]
                        )
        output = io.StringIO(newline="")
        output.write("\ufeff")
        writer = csv.writer(output, delimiter=";")
        if user.role is UserRole.PARTNER:
            writer.writerow(
                [
                    "Заявка",
                    "Дата",
                    "Статус",
                    "Канал",
                    "Банк",
                    "Статус банка",
                    "Вознаграждение",
                    "Выплата",
                ]
            )
        elif user.role is UserRole.ADMIN:
            writer.writerow(
                [
                    "Заявка",
                    "Клиент",
                    "Телефон",
                    "Дата",
                    "Статус",
                    "Канал",
                    "Менеджер",
                    "Банк",
                    "Статус банка",
                    "Доход факт",
                    "Вознаграждение",
                    "Выплата",
                ]
            )
        else:
            writer.writerow(
                [
                    "Заявка",
                    "Клиент",
                    "Телефон",
                    "Дата",
                    "Статус",
                    "Банк",
                    "Статус банка",
                ]
            )
        writer.writerows(rows)
        headers = {"Content-Disposition": 'attachment; filename="rko-leads.csv"'}
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv; charset=utf-8",
            headers=headers,
        )

    @app.get("/api/leads/{lead_id}")
    async def lead_detail(
        lead_id: UUID,
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> dict[str, object]:
        require_operational_user(user)
        detail_scope = true() if user.role is UserRole.ADMIN else lead_scope(user)
        async with database.session() as db_session:
            lead = await db_session.scalar(select(Lead).where(Lead.id == lead_id, detail_scope))
            if lead is None:
                raise HTTPException(status_code=404, detail="Заявка не найдена")
            banks_query = (
                select(LeadBank, Bank, Payment)
                .join(Bank, Bank.id == LeadBank.bank_id)
                .outerjoin(Payment, Payment.lead_bank_id == LeadBank.id)
                .where(LeadBank.lead_id == lead.id)
            )
            if user.role is UserRole.MANAGER:
                banks_query = banks_query.where(
                    or_(
                        LeadBank.selected_by_lead.is_(True),
                        LeadBank.internal_status == BankInternalStatus.CLIENT_REFUSED,
                    )
                )
            rows = await db_session.execute(banks_query.order_by(LeadBank.planned_at))
            conditions = list(await db_session.scalars(select(BankActivationCondition)))
            rates = list(await db_session.scalars(select(BankRate)))
            manager = await db_session.get(User, lead.manager_id) if lead.manager_id else None
            primary_admin = (
                await db_session.get(User, lead.primary_admin_id) if lead.primary_admin_id else None
            )
            channel = await db_session.get(Channel, lead.channel_id) if lead.channel_id else None
            source_partner = (
                await db_session.get(Partner, lead.partner_id) if lead.partner_id else None
            )
            source_updated_by = (
                await db_session.get(User, lead.source_updated_by_user_id)
                if lead.source_updated_by_user_id
                else None
            )
            previous_applications = list(
                await db_session.scalars(
                    select(Lead)
                    .where(
                        Lead.telegram_id == lead.telegram_id,
                        Lead.id != lead.id,
                        Lead.application_at < lead.application_at,
                    )
                    .order_by(Lead.application_at.desc())
                )
            )
        conditions_by_name = {condition.normalized_bank_name: condition for condition in conditions}
        rates_by_bank = {rate.bank_id: rate for rate in rates}
        banks = []
        for lead_bank, bank, payment in rows:
            serialized = serialize_lead_bank(
                lead_bank, bank, payment, user.role, rates_by_bank.get(bank.id)
            )
            condition = conditions_by_name.get(normalize_bank_name(bank.name))
            serialized["action_text"] = condition.action_text if condition else ""
            serialized["payout_text"] = condition.payout_text if condition else "Уточняется"
            banks.append(serialized)
        if user.role is UserRole.PARTNER:
            contact = await partner_contact(database, require_partner(user))
            return {
                "id": str(lead.id),
                "short_id": lead.short_id,
                "name": lead.display_name,
                "date": lead.application_at.isoformat(),
                "updated": lead.last_updated_at.isoformat(),
                "status": lead.external_status.value,
                "payment_status": lead.payment_status.value,
                "channel": channel.name if channel else "Прямой",
                "is_repeat": lead.is_repeat,
                "contact": contact,
                "banks": banks,
            }
        result: dict[str, object] = {
            "id": str(lead.id),
            "short_id": lead.short_id,
            "name": lead.display_name,
            "username": f"@{lead.telegram_username}" if lead.telegram_username else "",
            "date": lead.application_at.isoformat(),
            "updated": lead.last_updated_at.isoformat(),
            "status": lead.internal_status.value,
            "payment_status": lead.payment_status.value,
            "channel": channel.name if channel else "Прямой",
            "manager": format_user_name(manager),
            "primary_admin": format_user_name(primary_admin),
            "workflow_stage": lead.workflow_stage.value,
            "is_repeat": lead.is_repeat,
            "archived": lead.archived_at is not None,
            "previous_applications": [
                {
                    "id": str(previous.id),
                    "short_id": previous.short_id,
                    "date": previous.application_at.isoformat(),
                    "status": previous.internal_status.value,
                    "is_repeat": previous.is_repeat,
                }
                for previous in previous_applications
            ],
            "banks_published_at": (
                lead.banks_published_at.isoformat() if lead.banks_published_at else None
            ),
            "bank_selection_submitted_at": (
                lead.bank_selection_submitted_at.isoformat()
                if lead.bank_selection_submitted_at
                else None
            ),
            "is_primary_admin": lead.primary_admin_id == user.database_id,
            "is_assigned_manager": lead.manager_id == user.database_id,
            "manager_started": lead.manager_started_at is not None,
            "banks": banks,
        }
        result.update(
            {
                "telegram_id": lead.telegram_id,
                "phone": lead.phone,
                "email": lead.email or "",
                "consent": lead.consent_status,
                "consent_at": lead.consent_at.isoformat(),
                "external_status": lead.external_status.value,
                "assignment_status": lead.assignment_status.value,
                "source_partner": source_partner.name if source_partner else "",
                "source_channel": channel.name if channel else "",
                "source_updated_by": format_user_name(source_updated_by),
                "source_updated_at": (
                    lead.source_updated_at.isoformat() if lead.source_updated_at else None
                ),
                "manager_id": str(lead.manager_id) if lead.manager_id else None,
                "primary_admin_id": (str(lead.primary_admin_id) if lead.primary_admin_id else None),
                "comment": lead.internal_comment or "",
                "answers": lead.questionnaire_answers,
            }
        )
        return result

    @app.patch("/api/leads/{lead_id}")
    async def update_lead(
        lead_id: UUID,
        payload: LeadUpdate,
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> dict[str, str]:
        actor_id = require_employee(user)
        try:
            lead = await WorkflowService(database).update_lead(
                actor_role=user.role,
                actor_user_id=actor_id,
                lead_id=lead_id,
                manager_id=payload.manager_id,
                update_manager=payload.update_manager,
                internal_comment=payload.internal_comment,
                update_comment=payload.update_comment,
            )
        except DomainError as error:
            raise domain_error(error) from error
        return {
            "id": str(lead.id),
            "status": lead.internal_status.value,
            "external_status": lead.external_status.value,
        }

    @app.delete("/api/leads/{lead_id}", status_code=204)
    async def delete_lead(
        lead_id: UUID,
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> None:
        actor_id = require_employee(user)
        try:
            await WorkflowService(database).delete_lead(
                actor_role=user.role,
                actor_user_id=actor_id,
                lead_id=lead_id,
            )
        except DomainError as error:
            raise domain_error(error) from error

    @app.get("/api/partners")
    async def partners(
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> list[dict[str, object]]:
        require_admin(user)
        linked_user = aliased(User)
        assigned_admin = aliased(User)
        async with database.session() as db_session:
            rows = await db_session.execute(
                select(
                    Partner,
                    linked_user.telegram_id,
                    linked_user.telegram_username,
                    assigned_admin.id,
                    assigned_admin.telegram_username,
                    assigned_admin.telegram_id,
                    func.count(Channel.id),
                )
                .outerjoin(linked_user, linked_user.id == Partner.telegram_user_id)
                .outerjoin(assigned_admin, assigned_admin.id == Partner.assigned_manager_id)
                .outerjoin(Channel, Channel.partner_id == Partner.id)
                .group_by(
                    Partner.id,
                    linked_user.telegram_id,
                    linked_user.telegram_username,
                    assigned_admin.id,
                    assigned_admin.telegram_username,
                    assigned_admin.telegram_id,
                )
                .order_by(Partner.name)
            )
        return [
            {
                "id": str(partner.id),
                "name": partner.name,
                "commission": str(partner.commission_percent),
                "active": partner.active,
                "telegram_id": telegram_id or "",
                "telegram_username": (
                    f"@{telegram_username or partner.telegram_username}"
                    if telegram_username or partner.telegram_username
                    else ""
                ),
                "channels": channel_count,
                "activated": partner.telegram_user_id is not None,
                "assigned_admin_id": str(admin_id) if admin_id else "",
                "assigned_admin": (
                    f"@{admin_username}" if admin_username else (admin_telegram_id or "Не назначен")
                ),
            }
            for (
                partner,
                telegram_id,
                telegram_username,
                admin_id,
                admin_username,
                admin_telegram_id,
                channel_count,
            ) in rows
        ]

    @app.post("/api/partners")
    async def create_partner(
        payload: PartnerCreate,
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> dict[str, object]:
        actor_id = require_admin(user)
        service = AdminCatalogService(database)
        try:
            username = (
                service.parse_telegram_username(payload.telegram_username)
                if payload.telegram_username
                else None
            )
            partner = await service.create_partner(
                actor_role=user.role,
                actor_user_id=actor_id,
                name=payload.name,
                commission_percent=payload.commission_percent,
                telegram_username=username,
            )
        except DomainError as error:
            raise domain_error(error) from error
        return {
            "id": str(partner.id),
            "name": partner.name,
            "commission": str(partner.commission_percent),
            "active": partner.active,
            "assigned_admin_id": str(actor_id),
        }

    @app.post("/api/partners/{partner_id}/activation-link")
    async def create_partner_activation_link(
        partner_id: UUID,
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> dict[str, object]:
        admin_id = require_admin(user)
        if bot is None:
            raise HTTPException(status_code=503, detail="Бот временно недоступен")
        bot_user = await bot.get_me()
        if not bot_user.username:
            raise HTTPException(status_code=503, detail="У бота не настроен username")
        try:
            link = await AdminCatalogService(database).create_partner_activation_link(
                actor_role=user.role,
                actor_user_id=admin_id,
                partner_id=partner_id,
                bot_username=bot_user.username,
            )
        except DomainError as error:
            raise domain_error(error) from error
        start_parameter = link.partition("?start=")[2]
        links = referral_links(start_parameter, link)
        return {
            "link": links[0]["url"] if links else link,
            "links": links,
        }

    @app.get("/api/channels")
    async def channels(
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> list[dict[str, object]]:
        if user.role not in {UserRole.ADMIN, UserRole.PARTNER}:
            raise HTTPException(
                status_code=403,
                detail="Каналы доступны партнёру или администратору",
            )
        async with database.session() as db_session:
            scope = true() if user.role is UserRole.ADMIN else Channel.partner_id == user.partner_id
            rows = await db_session.execute(
                select(Channel, Partner.name)
                .join(Partner, Partner.id == Channel.partner_id)
                .where(scope)
                .order_by(Partner.name, Channel.name)
            )
        result = []
        for channel, partner_name in rows:
            links = referral_links(channel.referral_code, channel.referral_link)
            result.append(
                {
                    "id": str(channel.id),
                    "partner_id": str(channel.partner_id),
                    "partner": partner_name,
                    "name": channel.name,
                    "active": channel.active,
                    "link": links[0]["url"] if links else channel.referral_link,
                    "links": links,
                }
            )
        return result

    @app.post("/api/channels")
    async def create_channel(
        payload: ChannelCreate,
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> dict[str, object]:
        if user.role not in {UserRole.ADMIN, UserRole.PARTNER}:
            raise HTTPException(status_code=403, detail="Добавление каналов недоступно")
        partner_id = user.partner_id if user.role is UserRole.PARTNER else payload.partner_id
        if partner_id is None:
            raise HTTPException(status_code=400, detail="Не указан партнёр")
        if bot is None:
            raise HTTPException(status_code=503, detail="Бот временно недоступен")
        bot_user = await bot.get_me()
        if not bot_user.username:
            raise HTTPException(status_code=503, detail="У бота не настроен username")
        try:
            channel = await AdminCatalogService(database).create_channel(
                actor_role=user.role,
                actor_partner_id=user.partner_id,
                partner_id=partner_id,
                name=payload.name,
                bot_username=bot_user.username,
            )
        except DomainError as error:
            raise domain_error(error) from error
        links = referral_links(channel.referral_code, channel.referral_link)
        return {
            "id": str(channel.id),
            "partner_id": str(channel.partner_id),
            "name": channel.name,
            "active": channel.active,
            "link": links[0]["url"] if links else channel.referral_link,
            "links": links,
        }

    @app.delete("/api/channels/{channel_id}")
    async def remove_channel(
        channel_id: UUID,
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> dict[str, object]:
        if user.role not in {UserRole.ADMIN, UserRole.PARTNER}:
            raise HTTPException(status_code=403, detail="Удаление каналов недоступно")
        try:
            deleted = await AdminCatalogService(database).remove_channel(
                actor_role=user.role,
                actor_partner_id=user.partner_id,
                channel_id=channel_id,
            )
        except DomainError as error:
            raise domain_error(error) from error
        return {
            "id": str(channel_id),
            "deleted": deleted,
            "message": ("Канал удалён" if deleted else "Канал отключён, история заявок сохранена"),
        }

    @app.put("/api/partners/{partner_id}/access")
    async def bind_partner_access(
        partner_id: UUID,
        payload: PartnerAccessUpdate,
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> dict[str, str]:
        require_admin(user)
        try:
            partner = await WorkflowService(database).bind_partner_access(
                actor_role=user.role,
                partner_id=partner_id,
                telegram_id=payload.telegram_id,
                telegram_username=payload.telegram_username,
            )
        except DomainError as error:
            raise domain_error(error) from error
        for current_bot in notification_bots:
            try:
                await current_bot.send_message(
                    chat_id=int(payload.telegram_id),
                    text=(
                        "Партнёрский кабинет РКО подключён. Отправьте /start, чтобы открыть его."
                    ),
                )
            except Exception:
                logger.exception(
                    "Failed to send partner access message for %s via bot %s",
                    partner.id,
                    current_bot.id,
                )
        return {"id": str(partner.id), "status": "access_bound"}

    @app.patch("/api/partners/{partner_id}")
    async def update_partner(
        partner_id: UUID,
        payload: PartnerUpdate,
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> dict[str, str]:
        require_admin(user)
        if (
            payload.commission_percent is None
            and payload.telegram_username is None
            and not payload.update_assigned_admin
        ):
            raise HTTPException(status_code=400, detail="Не указаны изменения")
        service = AdminCatalogService(database)
        try:
            partner = None
            if payload.commission_percent is not None:
                partner = await service.update_partner_commission(
                    actor_role=user.role,
                    partner_id=partner_id,
                    commission_percent=payload.commission_percent,
                )
            if payload.telegram_username is not None:
                partner = await service.update_partner_username(
                    actor_role=user.role,
                    partner_id=partner_id,
                    telegram_username=payload.telegram_username,
                )
            if payload.update_assigned_admin:
                partner = await service.update_partner_admin(
                    actor_role=user.role,
                    partner_id=partner_id,
                    admin_id=payload.assigned_admin_id,
                )
        except DomainError as error:
            raise domain_error(error) from error
        if partner is None:
            raise HTTPException(status_code=400, detail="Не указаны изменения")
        return {"id": str(partner.id), "commission": str(partner.commission_percent)}

    @app.delete("/api/partners/{partner_id}")
    async def delete_partner(
        partner_id: UUID,
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> dict[str, object]:
        require_admin(user)
        try:
            deleted = await AdminCatalogService(database).delete_partner(
                actor_role=user.role,
                partner_id=partner_id,
            )
        except DomainError as error:
            raise domain_error(error) from error
        return {
            "id": str(partner_id),
            "deleted": deleted,
            "message": (
                "Партнёр удалён" if deleted else "Партнёр отключён, история заявок сохранена"
            ),
        }

    @app.get("/api/staff")
    async def staff(
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> list[dict[str, str]]:
        require_employee(user)
        items = await WorkflowService(database).list_staff()
        return [
            {
                "id": str(item.id),
                "telegram_id": item.telegram_id or "",
                "username": f"@{item.telegram_username}" if item.telegram_username else "",
                "role": item.role.value,
                "status": (
                    "pending"
                    if item.telegram_id is None and item.access_status is AccessStatus.ACTIVE
                    else item.access_status.value
                ),
            }
            for item in items
        ]

    @app.post("/api/staff")
    async def create_staff(
        payload: StaffCreate,
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> dict[str, str]:
        require_admin(user)
        try:
            created = await WorkflowService(database).create_staff(
                actor_role=user.role,
                telegram_username=payload.telegram_username,
                role=payload.role,
            )
        except DomainError as error:
            raise domain_error(error) from error
        return {"id": str(created.id), "role": created.role.value}

    @app.post("/api/staff/{user_id}/toggle")
    async def toggle_staff(
        user_id: UUID,
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> dict[str, str]:
        require_admin(user)
        try:
            changed = await WorkflowService(database).toggle_user(
                actor_role=user.role, user_id=user_id
            )
        except DomainError as error:
            raise domain_error(error) from error
        return {"id": str(changed.id), "status": changed.access_status.value}

    @app.get("/api/banks")
    async def banks(
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> list[dict[str, object]]:
        if user.role is UserRole.PARTNER:
            raise HTTPException(status_code=403, detail="Справочник доступен сотруднику")
        async with database.session() as db_session:
            rows = list(
                await db_session.execute(
                    select(Bank, BankRate)
                    .outerjoin(BankRate, BankRate.bank_id == Bank.id)
                    .where(Bank.active.is_(True))
                    .order_by(Bank.display_order, Bank.name)
                )
            )
            conditions = list(await db_session.scalars(select(BankActivationCondition)))
        conditions_by_name = {condition.normalized_bank_name: condition for condition in conditions}
        result: list[dict[str, object]] = []
        for bank, rate in rows:
            condition = conditions_by_name.get(normalize_bank_name(bank.name))
            online_text = rate.online_text if rate else "Уточняется"
            item: dict[str, object] = {
                "id": str(bank.id),
                "name": bank.name,
                "active": bank.active,
                "order": bank.display_order,
                "online_text": online_text,
                **online_bank_info(bank.name, online_text),
                "action_text": condition.action_text if condition else "",
                "synced": rate.synced_at.isoformat() if rate else None,
            }
            if user.role is UserRole.ADMIN:
                item.update(
                    {
                        "offer_code": rate.offer_code if rate else "",
                        "base_payout": str(rate.base_payout) if rate else None,
                        "lead_payout": str(rate.lead_payout) if rate else None,
                        "lead_payout_paid_separately": (
                            rate.lead_payout_paid_separately if rate else False
                        ),
                    }
                )
            result.append(item)
        return result

    @app.post("/api/banks")
    async def create_bank(
        payload: BankCreate,
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> dict[str, object]:
        require_admin(user)
        async with database.session() as db_session:
            duplicate_code = await db_session.scalar(
                select(BankRate.id).where(
                    func.lower(BankRate.offer_code) == payload.offer_code.strip().lower()
                )
            )
            duplicate_name = await db_session.scalar(
                select(Bank.id).where(func.lower(Bank.name) == payload.name.strip().lower())
            )
        if duplicate_code is not None:
            raise HTTPException(status_code=400, detail="Такой код предложения уже есть")
        if duplicate_name is not None:
            raise HTTPException(status_code=400, detail="Банк с таким названием уже есть")
        rate = await write_bank_rate(payload)
        return {
            "id": str(rate.bank_id),
            "offer_code": rate.offer_code,
            "name": payload.name.strip(),
            "active": rate.active,
        }

    @app.patch("/api/banks/{bank_id}")
    async def update_bank(
        bank_id: UUID,
        payload: BankUpdate,
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> dict[str, object]:
        require_admin(user)
        async with database.session() as db_session:
            current = await db_session.scalar(select(BankRate).where(BankRate.bank_id == bank_id))
            current_bank = await db_session.get(Bank, bank_id)
        if current is None:
            raise HTTPException(status_code=404, detail="Ставка банка не найдена")
        if current_bank is None:
            raise HTTPException(status_code=404, detail="Банк не найден")
        if current.offer_code.casefold() != payload.offer_code.strip().casefold():
            raise HTTPException(
                status_code=400,
                detail="Код предложения нельзя изменить после создания банка",
            )
        rate = await write_bank_rate(
            payload,
            original_offer_code=current.offer_code,
        )
        return {
            "id": str(rate.bank_id),
            "offer_code": rate.offer_code,
            "active": rate.active,
        }

    @app.post("/api/banks/{bank_id}/toggle")
    async def toggle_bank(
        bank_id: UUID,
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> dict[str, object]:
        require_admin(user)
        async with database.session() as db_session:
            rate = await db_session.scalar(select(BankRate).where(BankRate.bank_id == bank_id))
        if rate is None:
            raise HTTPException(status_code=404, detail="Ставка банка не найдена")
        try:
            gateway = await asyncio.to_thread(require_bank_rates_sheet)
            rows = await asyncio.to_thread(gateway.set_active, rate.offer_code, not rate.active)
            await BankRatesService(database).replace_all(rows)
        except HTTPException:
            raise
        except (ValueError, OSError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {"id": str(bank_id), "active": not rate.active}

    @app.delete("/api/banks/{bank_id}")
    async def remove_bank(
        bank_id: UUID,
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> dict[str, object]:
        require_admin(user)
        async with database.session() as db_session:
            rate = await db_session.scalar(select(BankRate).where(BankRate.bank_id == bank_id))
        if rate is None:
            raise HTTPException(status_code=404, detail="Ставка банка не найдена")
        try:
            gateway = await asyncio.to_thread(require_bank_rates_sheet)
            rows = await asyncio.to_thread(gateway.set_active, rate.offer_code, False)
            await BankRatesService(database).replace_all(rows)
        except HTTPException:
            raise
        except (ValueError, OSError) as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        return {
            "id": str(bank_id),
            "active": False,
            "message": "Банк убран из справочника, история заявок сохранена",
        }

    @app.post("/api/leads/{lead_id}/banks")
    async def add_lead_bank(
        lead_id: UUID,
        payload: LeadBankCreate,
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> dict[str, object]:
        actor_user_id = require_employee(user)
        async with database.session() as db_session:
            previous_internal_status = await db_session.scalar(
                select(Lead.internal_status).where(Lead.id == lead_id)
            )
        try:
            lead_banks = await WorkflowService(database).add_banks_to_lead(
                actor_role=user.role,
                lead_id=lead_id,
                bank_ids=payload.bank_ids,
                actor_user_id=actor_user_id,
            )
        except DomainError as error:
            raise domain_error(error) from error
        async with database.session() as db_session:
            current_internal_status = await db_session.scalar(
                select(Lead.internal_status).where(Lead.id == lead_id)
            )
        if (
            current_internal_status is not None
            and previous_internal_status != current_internal_status
        ):
            await notify_client_status(lead_id, current_internal_status)
        return {
            "ids": [str(lead_bank.id) for lead_bank in lead_banks],
            "count": len(lead_banks),
        }

    @app.post("/api/leads/{lead_id}/claim-manager")
    async def claim_lead_by_manager(
        lead_id: UUID,
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> dict[str, str]:
        actor_id = require_employee(user)
        async with database.session() as db_session:
            previous_manager_started_at = await db_session.scalar(
                select(Lead.manager_started_at).where(Lead.id == lead_id)
            )
        try:
            lead = await LeadWorkflowService(database).claim_by_manager(
                actor_role=user.role,
                actor_id=actor_id,
                lead_id=lead_id,
            )
        except DomainError as error:
            raise domain_error(error) from error
        async with database.session() as db_session:
            manager = await db_session.get(User, actor_id)
        if previous_manager_started_at is None:
            manager_name = format_user_name(manager)
            await notify_client(
                lead.id,
                f"Ваш персональный менеджер — {manager_name}. "
                "Скоро он свяжется с вами и создаст отдельную группу для сопровождения.",
            )
        return {"id": str(lead.id), "workflow_stage": lead.workflow_stage.value}

    @app.patch("/api/lead-banks/{lead_bank_id}")
    async def update_lead_bank(
        lead_bank_id: UUID,
        payload: LeadBankUpdate,
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> dict[str, object]:
        actor_id = require_employee(user)
        async with database.session() as db_session:
            previous_status = await db_session.scalar(
                select(LeadBank.internal_status).where(LeadBank.id == lead_bank_id)
            )
        try:
            lead_bank = await WorkflowService(database).update_lead_bank(
                actor_role=user.role,
                actor_user_id=actor_id,
                lead_bank_id=lead_bank_id,
                status=payload.status,
                close_reason=payload.close_reason,
                income_estimate=payload.income_estimate,
                income_fact=payload.income_fact,
            )
        except DomainError as error:
            raise domain_error(error) from error
        sheet_sync_error = ""
        if (
            user.role is UserRole.ADMIN
            and payload.status is BankInternalStatus.ACCOUNT_OPENED
            and previous_status is not BankInternalStatus.ACCOUNT_OPENED
        ):
            async with database.session() as db_session:
                lead = await db_session.get(Lead, lead_bank.lead_id)
            if lead is not None:
                try:
                    registry_row = await LeadRegistryService(
                        database, settings.project_timezone
                    ).activation_row(lead_bank.id, lead.manager_id or actor_id)
                    gateway = await registry_gateway()
                    await asyncio.to_thread(gateway.upsert_lead_activation, registry_row)
                except Exception:
                    sheet_sync_error = "Счёт активирован, но Google Sheets не обновлена"
                    logger.exception(
                        "Failed to sync account activation for lead %s to Google Sheets",
                        lead.id,
                    )
        result: dict[str, object] = {
            "id": str(lead_bank.id),
            "status": lead_bank.internal_status.value,
        }
        if user.role is UserRole.ADMIN:
            result.update(
                {
                    "reward_estimate": str(lead_bank.partner_reward_estimate or ""),
                    "reward_fact": str(lead_bank.partner_reward_fact or ""),
                }
            )
        if sheet_sync_error:
            result["sheet_sync_error"] = sheet_sync_error
        return result

    @app.post("/api/lead-banks/{lead_bank_id}/payment/confirm")
    async def confirm_bank_payment(
        lead_bank_id: UUID,
        payload: PaymentConfirm,
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> dict[str, str]:
        actor_user_id = require_admin(user)
        try:
            payment = await WorkflowService(database).confirm_lead_bank_payment(
                actor_role=user.role,
                actor_user_id=actor_user_id,
                lead_bank_id=lead_bank_id,
                payment_period=payload.payment_period,
                registry_number=payload.registry_number,
            )
        except DomainError as error:
            raise domain_error(error) from error
        return {"id": str(payment.id), "status": payment.status.value}

    @app.post("/api/lead-banks/{lead_bank_id}/lead-reward/confirm")
    async def confirm_lead_reward_payment(
        lead_bank_id: UUID,
        payload: LeadRewardPaymentConfirm,
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> dict[str, str]:
        require_admin(user)
        try:
            lead_bank = await WorkflowService(database).confirm_lead_reward_payment(
                actor_role=user.role,
                lead_bank_id=lead_bank_id,
                amount=payload.amount,
            )
        except DomainError as error:
            raise domain_error(error) from error
        async with database.session() as db_session:
            reward_details = (
                await db_session.execute(
                    select(LeadBank.lead_id, Bank.name)
                    .join(Bank, Bank.id == LeadBank.bank_id)
                    .where(LeadBank.id == lead_bank_id)
                )
            ).one()
        await notify_client(
            reward_details.lead_id,
            format_lead_reward_message(
                reward_details.name,
                lead_bank.lead_reward_fact or Decimal("0"),
            ),
            parse_mode="HTML",
        )
        sheet_sync_error = ""
        try:
            application_id, bank_name, paid_at, amount, payment_status = await LeadRegistryService(
                database, settings.project_timezone
            ).payment_values(lead_bank.id)
            gateway = await registry_gateway()
            await asyncio.to_thread(
                gateway.update_lead_payment,
                application_id,
                bank_name,
                paid_at,
                amount,
                payment_status,
            )
        except LeadRegistryRowNotFound:
            sheet_sync_error = "Выплата сохранена, но заявка не найдена в Google Sheets"
            logger.exception(
                "Lead %s is missing from the Google Sheets registry", lead_bank.lead_id
            )
        except Exception:
            sheet_sync_error = "Выплата сохранена, но Google Sheets не обновлена"
            logger.exception(
                "Failed to sync lead reward payment for lead %s to Google Sheets",
                lead_bank.lead_id,
            )
        result = {
            "id": str(lead_bank.id),
            "status": "paid",
            "amount": str(lead_bank.lead_reward_fact or 0),
        }
        if sheet_sync_error:
            result["sheet_sync_error"] = sheet_sync_error
        return result

    @app.patch("/api/payments/{payment_id}")
    async def update_payment(
        payment_id: UUID,
        payload: PaymentStatusUpdate,
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> dict[str, str]:
        require_admin(user)
        try:
            payment = await WorkflowService(database).change_payment_status(
                actor_role=user.role,
                payment_id=payment_id,
                new_status=payload.status,
                paid_at=payload.paid_at,
                internal_comment=payload.internal_comment,
                registry_number=payload.registry_number,
            )
        except DomainError as error:
            raise domain_error(error) from error
        if (
            payment.status is PaymentStatus.PAID
            and payment.partner_reward_fact is not None
            and payment.partner_reward_fact > 0
        ):
            async with database.session() as db_session:
                reward_details = (
                    await db_session.execute(
                        select(LeadBank.lead_id, Lead.short_id, Bank.name)
                        .join(Lead, Lead.id == LeadBank.lead_id)
                        .join(Bank, Bank.id == LeadBank.bank_id)
                        .join(Payment, Payment.lead_bank_id == LeadBank.id)
                        .where(Payment.id == payment.id)
                    )
                ).one()
            await notify_partner(
                reward_details.lead_id,
                format_partner_reward_message(
                    reward_details.short_id,
                    reward_details.name,
                    payment.partner_reward_fact,
                ),
                parse_mode="HTML",
            )
        return {"id": str(payment.id), "status": payment.status.value}

    return app
