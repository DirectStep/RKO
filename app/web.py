import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated
from urllib.parse import parse_qsl
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select, true
from sqlalchemy.sql.elements import ColumnElement

from app.config import Settings
from app.database import Database
from app.domain.enums import AccessStatus, AssignmentStatus, LeadInternalStatus, UserRole
from app.models import Channel, Lead, Partner, User
from app.services.user_access import UserAccessService

ASSETS_DIR = Path(__file__).parent / "web_assets"


@dataclass(frozen=True)
class MiniAppUser:
    id: str
    database_id: UUID
    name: str
    role: UserRole


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


def create_web_app(database: Database, settings: Settings) -> FastAPI:
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
        if role not in {UserRole.ADMIN, UserRole.MANAGER}:
            raise HTTPException(status_code=403, detail="Кабинет доступен сотрудникам")
        async with database.session() as session:
            user = await session.scalar(select(User).where(User.telegram_id == telegram_id))
        if user is None or user.access_status is not AccessStatus.ACTIVE:
            raise HTTPException(status_code=403, detail="Доступ отключён")
        return MiniAppUser(telegram_id, user.id, name, role)

    def lead_scope(user: MiniAppUser) -> ColumnElement[bool]:
        if user.role is UserRole.MANAGER:
            return Lead.manager_id == user.database_id
        return true()

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(ASSETS_DIR / "index.html")

    @app.get("/api/session")
    async def session(
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> dict[str, str]:
        return {"name": user.name, "role": user.role.value}

    @app.get("/api/dashboard")
    async def dashboard(
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> dict[str, int]:
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
    ) -> list[dict[str, str]]:
        async with database.session() as db_session:
            result = await db_session.scalars(
                select(Lead).where(lead_scope(user)).order_by(Lead.application_at.desc()).limit(50)
            )
            items = list(result)
        return [
            {
                "id": str(lead.id),
                "short_id": lead.short_id,
                "name": lead.display_name,
                "phone": lead.phone,
                "status": lead.internal_status.value,
                "source": lead.assignment_status.value,
                "date": lead.application_at.isoformat(),
            }
            for lead in items
        ]

    @app.get("/api/partners")
    async def partners(
        user: Annotated[MiniAppUser, Depends(current_user)],
    ) -> list[dict[str, object]]:
        if user.role is not UserRole.ADMIN:
            raise HTTPException(status_code=403, detail="Раздел доступен администратору")
        async with database.session() as db_session:
            rows = await db_session.execute(
                select(Partner, func.count(Channel.id))
                .outerjoin(Channel, Channel.partner_id == Partner.id)
                .group_by(Partner.id)
                .order_by(Partner.name)
            )
        return [
            {
                "id": str(partner.id),
                "name": partner.name,
                "commission": str(partner.commission_percent),
                "active": partner.active,
                "channels": channel_count,
            }
            for partner, channel_count in rows
        ]

    return app
