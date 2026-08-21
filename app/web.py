import csv
import hashlib
import hmac
import io
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, cast
from urllib.parse import parse_qsl
from uuid import UUID

from aiogram import Bot
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select, true
from sqlalchemy.sql.elements import ColumnElement

from app.config import Settings
from app.database import Database
from app.domain.enums import (
    AccessStatus,
    AssignmentStatus,
    LeadInternalStatus,
    PaymentStatus,
    UserRole,
)
from app.domain.operations import DomainError
from app.models import (
    Bank,
    BankActivationCondition,
    Channel,
    Lead,
    LeadBank,
    Partner,
    Payment,
    User,
)
from app.services.admin_catalog import AdminCatalogService
from app.services.bank_conditions import normalize_bank_name
from app.services.lead_assignment import LeadAssignmentService
from app.services.lead_workflow import LeadWorkflowService
from app.services.user_access import UserAccessService
from app.services.workflow import WorkflowService
from app.web_schemas import (
    BankCreate,
    ChannelCreate,
    LeadBankCreate,
    LeadBankSelection,
    LeadBankUpdate,
    LeadSourceUpdate,
    LeadUpdate,
    PartnerAccessUpdate,
    PartnerUpdate,
    PaymentConfirm,
    PaymentStatusUpdate,
    StaffCreate,
)

ASSETS_DIR = Path(__file__).parent / "web_assets"
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


def format_user_name(user: User | None) -> str:
    if user is None:
        return "Не назначен"
    if user.telegram_username:
        return f"@{user.telegram_username}"
    return user.telegram_id or "Ожидает входа"


def serialize_lead_bank(
    lead_bank: LeadBank,
    bank: Bank,
    payment: Payment | None,
    role: UserRole,
) -> dict[str, object]:
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
        "payment_id": str(payment.id) if payment else None,
        "payment_status": payment.status.value if payment else PaymentStatus.NOT_CALCULATED.value,
        "paid_at": payment.paid_at.isoformat() if payment and payment.paid_at else None,
    }
    if role is not UserRole.PARTNER:
        result.update(
            {
                "external_status": lead_bank.external_status.value,
                "close_reason": lead_bank.close_reason or "",
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
                "registry_number": payment.registry_number if payment else None,
                "offered_to_lead": lead_bank.offered_to_lead,
                "selected_by_lead": lead_bank.selected_by_lead,
            }
        )
    return result


def create_web_app(database: Database, settings: Settings, bot: Bot | None = None) -> FastAPI:
    app = FastAPI(title="РКО", docs_url=None, redoc_url=None)
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")

    async def current_user(
        telegram_init_data: str = Header(default="", alias="X-Telegram-Init-Data"),
    ) -> MiniAppUser:
        if telegram_init_data:
            try:
                telegram_user = validate_telegram_init_data(
                    telegram_init_data, settings.bot_token.get_secret_value()
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
            raise HTTPException(status_code=401, detail="Открой кабинет через Telegram")

        role = await UserAccessService(database, settings).resolve_role(telegram_id, username)
        async with database.session() as session:
            user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
            lead = await session.scalar(select(Lead).where(Lead.telegram_id == telegram_id))
        if user is not None and user.access_status is not AccessStatus.ACTIVE:
            raise HTTPException(status_code=403, detail="Доступ отключён")
        if role in {None, UserRole.LEAD}:
            if lead is None:
                raise HTTPException(status_code=403, detail="Для этого пользователя нет кабинета")
            return MiniAppUser(
                telegram_id,
                None,
                lead.display_name,
                UserRole.LEAD,
                lead_id=lead.id,
            )
        if role not in {UserRole.ADMIN, UserRole.MANAGER, UserRole.PARTNER} or user is None:
            raise HTTPException(status_code=403, detail="Для этого пользователя нет кабинета")
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
                raise HTTPException(status_code=403, detail="Партнёрский кабинет не привязан")
            partner_id = partner.id
            name = partner.name
        return MiniAppUser(telegram_id, user.id, name, role, partner_id)

    def lead_scope(user: MiniAppUser) -> ColumnElement[bool]:
        if user.role is UserRole.PARTNER:
            return (Lead.partner_id == user.partner_id) & (
                Lead.assignment_status == AssignmentStatus.CONFIRMED
            )
        return true()

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

    def require_employee(user: MiniAppUser) -> UUID:
        if user.role not in {UserRole.ADMIN, UserRole.MANAGER} or user.database_id is None:
            raise HTTPException(status_code=403, detail="Раздел доступен сотруднику")
        return user.database_id

    def domain_error(error: DomainError) -> HTTPException:
        return HTTPException(status_code=400, detail=str(error))

    async def notify_partner(lead_id: UUID, text: str) -> None:
        if bot is None:
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
        try:
            await bot.send_message(chat_id=int(telegram_id), text=text)
        except Exception:
            logger.exception("Failed to notify partner for lead %s", lead_id)

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(ASSETS_DIR / "index.html")

    @app.get("/api/session")
    async def session(
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> dict[str, str]:
        google_sheet_url = ""
        if user.role is UserRole.ADMIN and settings.google_sheet_id:
            google_sheet_url = (
                f"https://docs.google.com/spreadsheets/d/{settings.google_sheet_id}/edit"
            )
        return {
            "name": user.name,
            "role": user.role.value,
            "telegram_id": user.id,
            "google_sheet_url": google_sheet_url,
        }

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
            manager = (
                await db_session.get(User, lead.manager_id)
                if lead is not None and lead.manager_id is not None
                else None
            )
        if lead is None:
            raise HTTPException(status_code=404, detail="Заявка не найдена")
        manager_username = manager.telegram_username if manager else None
        return {
            "short_id": lead.short_id,
            "name": lead.display_name,
            "date": lead.application_at.isoformat(),
            "updated": lead.last_updated_at.isoformat(),
            "status": lead.external_status.value,
            "workflow_stage": lead.workflow_stage.value,
            "manager": format_user_name(manager),
            "manager_url": (
                f"https://t.me/{manager_username}" if manager_username else ""
            ),
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
            if lead.bank_selection_submitted_at is not None:
                bank_scope.append(LeadBank.selected_by_lead.is_(True))
            bank_rows = list(
                await db_session.execute(
                    select(LeadBank, Bank)
                    .join(Bank, Bank.id == LeadBank.bank_id)
                    .where(*bank_scope)
                    .order_by(Bank.display_order, LeadBank.planned_at)
                )
            )
            conditions = list(await db_session.scalars(select(BankActivationCondition)))
        conditions_by_name = {
            condition.normalized_bank_name: condition for condition in conditions
        }
        result: list[dict[str, object]] = []
        for lead_bank, bank in bank_rows:
            condition = conditions_by_name.get(normalize_bank_name(bank.name))
            result.append(
                {
                    "bank": bank.name,
                    "bank_id": str(bank.id),
                    "status": lead_bank.external_status.value,
                    "selected": lead_bank.selected_by_lead,
                    "selection_locked": lead.bank_selection_submitted_at is not None,
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
        result.sort(
            key=lambda item: (
                cast(int, item["order"]),
                cast(str, item["bank"]),
            )
        )
        return result

    @app.post("/api/lead/banks/selection")
    async def submit_lead_bank_selection(
        payload: LeadBankSelection,
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> dict[str, str]:
        lead_id = require_lead(user)
        try:
            lead = await LeadWorkflowService(database).submit_bank_selection(
                lead_id=lead_id,
                selected_bank_ids=set(payload.bank_ids),
            )
        except DomainError as error:
            raise domain_error(error) from error
        return {"id": str(lead.id), "workflow_stage": lead.workflow_stage.value}

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
            total = await db_session.scalar(select(func.count()).select_from(Lead).where(scope))
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
        return {
            "total": total or 0,
            "new": new or 0,
            "active": active or 0,
            "unresolved": unresolved or 0,
        }

    @app.get("/api/leads")
    async def leads(
        user: Annotated[MiniAppUser, Depends(current_user)],
        mine: bool = False,
    ) -> list[dict[str, object]]:
        require_operational_user(user)
        scope = lead_scope(user)
        if mine and user.role is UserRole.MANAGER:
            scope = scope & (Lead.manager_id == require_employee(user))
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
                "username": f"@{lead.telegram_username}" if lead.telegram_username else "",
                "status": (
                    lead.external_status.value
                    if user.role is UserRole.PARTNER
                    else lead.internal_status.value
                ),
                "date": lead.application_at.isoformat(),
                "workflow_stage": lead.workflow_stage.value,
            }
            if user.role is not UserRole.PARTNER:
                item["phone"] = lead.phone
                item["source"] = lead.assignment_status.value
                item["manager_id"] = str(lead.manager_id) if lead.manager_id else None
                item["primary_admin_id"] = (
                    str(lead.primary_admin_id) if lead.primary_admin_id else None
                )
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
                                lead.external_status.value,
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
                    else:
                        manager = (
                            await db_session.get(User, lead.manager_id)
                            if lead.manager_id
                            else None
                        )
                        rows.append(
                            [
                                lead.short_id,
                                lead.display_name,
                                lead.phone,
                                lead.application_at.date().isoformat(),
                                lead.internal_status.value,
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
        output = io.StringIO(newline="")
        output.write("\ufeff")
        writer = csv.writer(output, delimiter=";")
        if user.role is UserRole.PARTNER:
            writer.writerow(
                [
                    "Заявка", "Дата", "Статус", "Канал", "Банк", "Статус банка",
                    "Вознаграждение", "Выплата",
                ]
            )
        else:
            writer.writerow(
                [
                    "Заявка", "Клиент", "Телефон", "Дата", "Статус", "Канал",
                    "Менеджер", "Банк", "Статус банка", "Доход факт",
                    "Вознаграждение", "Выплата",
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
        async with database.session() as db_session:
            lead = await db_session.scalar(select(Lead).where(Lead.id == lead_id, lead_scope(user)))
            if lead is None:
                raise HTTPException(status_code=404, detail="Заявка не найдена")
            rows = await db_session.execute(
                select(LeadBank, Bank, Payment)
                .join(Bank, Bank.id == LeadBank.bank_id)
                .outerjoin(Payment, Payment.lead_bank_id == LeadBank.id)
                .where(LeadBank.lead_id == lead.id)
                .order_by(LeadBank.planned_at)
            )
            conditions = list(
                await db_session.scalars(select(BankActivationCondition))
            )
            manager = await db_session.get(User, lead.manager_id) if lead.manager_id else None
            primary_admin = (
                await db_session.get(User, lead.primary_admin_id)
                if lead.primary_admin_id
                else None
            )
            channel = await db_session.get(Channel, lead.channel_id) if lead.channel_id else None
        conditions_by_name = {
            condition.normalized_bank_name: condition for condition in conditions
        }
        banks = []
        for lead_bank, bank, payment in rows:
            serialized = serialize_lead_bank(lead_bank, bank, payment, user.role)
            if user.role is not UserRole.PARTNER:
                condition = conditions_by_name.get(normalize_bank_name(bank.name))
                serialized["action_text"] = condition.action_text if condition else ""
                serialized["payout_text"] = (
                    condition.payout_text if condition else "Уточняется"
                )
            banks.append(serialized)
        result: dict[str, object] = {
            "id": str(lead.id),
            "short_id": lead.short_id,
            "name": lead.display_name,
            "username": f"@{lead.telegram_username}" if lead.telegram_username else "",
            "date": lead.application_at.isoformat(),
            "updated": lead.last_updated_at.isoformat(),
            "status": (
                lead.external_status.value
                if user.role is UserRole.PARTNER
                else lead.internal_status.value
            ),
            "payment_status": lead.payment_status.value,
            "channel": channel.name if channel else "Прямой",
            "manager": format_user_name(manager),
            "primary_admin": format_user_name(primary_admin),
            "workflow_stage": lead.workflow_stage.value,
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
            "banks": banks,
        }
        if user.role is not UserRole.PARTNER:
            result.update(
                {
                    "telegram_id": lead.telegram_id,
                    "phone": lead.phone,
                    "email": lead.email or "",
                    "consent": lead.consent_status,
                    "consent_at": lead.consent_at.isoformat(),
                    "external_status": lead.external_status.value,
                    "assignment_status": lead.assignment_status.value,
                    "manager_id": str(lead.manager_id) if lead.manager_id else None,
                    "primary_admin_id": (
                        str(lead.primary_admin_id) if lead.primary_admin_id else None
                    ),
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
        require_employee(user)
        previous_external_status = None
        if payload.internal_status is not None:
            async with database.session() as db_session:
                previous_external_status = await db_session.scalar(
                    select(Lead.external_status).where(Lead.id == lead_id)
                )
        try:
            lead = await WorkflowService(database).update_lead(
                actor_role=user.role,
                lead_id=lead_id,
                internal_status=payload.internal_status,
                manager_id=payload.manager_id,
                update_manager=payload.update_manager,
                internal_comment=payload.internal_comment,
                update_comment=payload.update_comment,
            )
        except DomainError as error:
            raise domain_error(error) from error
        if (
            previous_external_status is not None
            and previous_external_status != lead.external_status
        ):
            await notify_partner(
                lead.id,
                "Статус заявки "
                f"{lead.short_id} изменён: "
                f"{EXTERNAL_STATUS_LABELS[lead.external_status.value]}",
            )
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
        require_employee(user)
        try:
            await WorkflowService(database).delete_lead(actor_role=user.role, lead_id=lead_id)
        except DomainError as error:
            raise domain_error(error) from error

    @app.put("/api/leads/{lead_id}/source")
    async def propose_lead_source(
        lead_id: UUID,
        payload: LeadSourceUpdate,
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> dict[str, str]:
        require_admin(user)
        try:
            lead = await LeadAssignmentService(database).propose_source(
                actor_role=user.role,
                lead_id=lead_id,
                partner_id=payload.partner_id,
                channel_id=payload.channel_id,
            )
        except DomainError as error:
            raise domain_error(error) from error
        return {"id": str(lead.id), "assignment_status": lead.assignment_status.value}

    @app.post("/api/leads/{lead_id}/source/confirm")
    async def confirm_lead_source(
        lead_id: UUID,
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> dict[str, str]:
        require_admin(user)
        try:
            lead = await LeadAssignmentService(database).confirm_proposed(
                actor_role=user.role, lead_id=lead_id
            )
        except DomainError as error:
            raise domain_error(error) from error
        await notify_partner(lead.id, f"Новая подтверждённая заявка: {lead.short_id}")
        return {"id": str(lead.id), "assignment_status": lead.assignment_status.value}

    @app.post("/api/leads/{lead_id}/source/direct")
    async def direct_lead_source(
        lead_id: UUID,
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> dict[str, str]:
        require_admin(user)
        try:
            lead = await LeadAssignmentService(database).mark_direct(
                actor_role=user.role, lead_id=lead_id
            )
        except DomainError as error:
            raise domain_error(error) from error
        return {"id": str(lead.id), "assignment_status": lead.assignment_status.value}

    @app.get("/api/partners")
    async def partners(
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> list[dict[str, object]]:
        require_admin(user)
        async with database.session() as db_session:
            rows = await db_session.execute(
                select(
                    Partner,
                    User.telegram_id,
                    User.telegram_username,
                    func.count(Channel.id),
                )
                .outerjoin(User, User.id == Partner.telegram_user_id)
                .outerjoin(Channel, Channel.partner_id == Partner.id)
                .group_by(Partner.id, User.telegram_id, User.telegram_username)
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
            }
            for partner, telegram_id, telegram_username, channel_count in rows
        ]

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
        return [
            {
                "id": str(channel.id),
                "partner_id": str(channel.partner_id),
                "partner": partner_name,
                "name": channel.name,
                "active": channel.active,
                "link": channel.referral_link,
            }
            for channel, partner_name in rows
        ]

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
        return {
            "id": str(channel.id),
            "partner_id": str(channel.partner_id),
            "name": channel.name,
            "active": channel.active,
            "link": channel.referral_link,
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
        if bot is not None:
            try:
                await bot.send_message(
                    chat_id=int(payload.telegram_id),
                    text="Партнёрский кабинет РКО подключён. Отправь /start, чтобы открыть его.",
                )
            except Exception:
                logger.exception("Failed to send partner access message for %s", partner.id)
        return {"id": str(partner.id), "status": "access_bound"}

    @app.patch("/api/partners/{partner_id}")
    async def update_partner(
        partner_id: UUID,
        payload: PartnerUpdate,
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> dict[str, str]:
        require_admin(user)
        if payload.commission_percent is None and payload.telegram_username is None:
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
        except DomainError as error:
            raise domain_error(error) from error
        if partner is None:
            raise HTTPException(status_code=400, detail="Не указаны изменения")
        return {"id": str(partner.id), "commission": str(partner.commission_percent)}

    @app.delete("/api/partners/{partner_id}", status_code=204)
    async def delete_partner(
        partner_id: UUID,
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> None:
        require_admin(user)
        try:
            await AdminCatalogService(database).delete_partner(
                actor_role=user.role,
                partner_id=partner_id,
            )
        except DomainError as error:
            raise domain_error(error) from error

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
                    if item.telegram_id is None
                    and item.access_status is AccessStatus.ACTIVE
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
        items = await WorkflowService(database).list_banks()
        return [
            {
                "id": str(bank.id),
                "name": bank.name,
                "active": bank.active,
                "order": bank.display_order,
            }
            for bank in items
        ]

    @app.post("/api/banks")
    async def create_bank(
        payload: BankCreate,
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> dict[str, object]:
        require_admin(user)
        try:
            bank = await WorkflowService(database).create_bank(
                actor_role=user.role,
                name=payload.name,
                display_order=payload.display_order,
            )
        except DomainError as error:
            raise domain_error(error) from error
        return {"id": str(bank.id), "name": bank.name, "active": bank.active}

    @app.post("/api/banks/{bank_id}/toggle")
    async def toggle_bank(
        bank_id: UUID,
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> dict[str, object]:
        require_admin(user)
        try:
            bank = await WorkflowService(database).toggle_bank(
                actor_role=user.role, bank_id=bank_id
            )
        except DomainError as error:
            raise domain_error(error) from error
        return {"id": str(bank.id), "active": bank.active}

    @app.post("/api/leads/{lead_id}/banks")
    async def add_lead_bank(
        lead_id: UUID,
        payload: LeadBankCreate,
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> dict[str, str]:
        actor_user_id = require_employee(user)
        try:
            lead_bank = await WorkflowService(database).add_bank_to_lead(
                actor_role=user.role,
                lead_id=lead_id,
                bank_id=payload.bank_id,
                actor_user_id=actor_user_id,
            )
        except DomainError as error:
            raise domain_error(error) from error
        return {"id": str(lead_bank.id), "status": lead_bank.internal_status.value}

    @app.post("/api/leads/{lead_id}/claim-admin")
    async def claim_lead_by_admin(
        lead_id: UUID,
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> dict[str, str]:
        actor_id = require_admin(user)
        try:
            lead = await LeadWorkflowService(database).claim_by_admin(
                actor_role=user.role,
                actor_id=actor_id,
                lead_id=lead_id,
            )
        except DomainError as error:
            raise domain_error(error) from error
        return {"id": str(lead.id), "workflow_stage": lead.workflow_stage.value}

    @app.post("/api/leads/{lead_id}/banks/publish")
    async def publish_lead_banks(
        lead_id: UUID,
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> dict[str, str]:
        actor_id = require_admin(user)
        try:
            lead = await LeadWorkflowService(database).publish_banks(
                actor_role=user.role,
                actor_id=actor_id,
                lead_id=lead_id,
            )
        except DomainError as error:
            raise domain_error(error) from error
        return {"id": str(lead.id), "workflow_stage": lead.workflow_stage.value}

    @app.post("/api/leads/{lead_id}/claim-manager")
    async def claim_lead_by_manager(
        lead_id: UUID,
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> dict[str, str]:
        actor_id = require_employee(user)
        try:
            lead = await LeadWorkflowService(database).claim_by_manager(
                actor_role=user.role,
                actor_id=actor_id,
                lead_id=lead_id,
            )
        except DomainError as error:
            raise domain_error(error) from error
        return {"id": str(lead.id), "workflow_stage": lead.workflow_stage.value}

    @app.patch("/api/lead-banks/{lead_bank_id}")
    async def update_lead_bank(
        lead_bank_id: UUID,
        payload: LeadBankUpdate,
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> dict[str, object]:
        require_employee(user)
        try:
            lead_bank = await WorkflowService(database).update_lead_bank(
                actor_role=user.role,
                lead_bank_id=lead_bank_id,
                status=payload.status,
                close_reason=payload.close_reason,
                income_estimate=payload.income_estimate,
                income_fact=payload.income_fact,
            )
        except DomainError as error:
            raise domain_error(error) from error
        return {
            "id": str(lead_bank.id),
            "status": lead_bank.internal_status.value,
            "reward_estimate": str(lead_bank.partner_reward_estimate or ""),
            "reward_fact": str(lead_bank.partner_reward_fact or ""),
        }

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
        async with database.session() as db_session:
            lead_id = await db_session.scalar(
                select(LeadBank.lead_id).where(LeadBank.id == lead_bank_id)
            )
        if lead_id is not None:
            await notify_partner(lead_id, "Вознаграждение по заявке подтверждено.")
        return {"id": str(payment.id), "status": payment.status.value}

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
        if payment.status is PaymentStatus.PAID:
            async with database.session() as db_session:
                lead_id = await db_session.scalar(
                    select(LeadBank.lead_id)
                    .join(Payment, Payment.lead_bank_id == LeadBank.id)
                    .where(Payment.id == payment.id)
                )
            if lead_id is not None:
                await notify_partner(lead_id, "Вознаграждение по заявке выплачено.")
        return {"id": str(payment.id), "status": payment.status.value}

    return app
