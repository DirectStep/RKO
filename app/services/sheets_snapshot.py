import json
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.database import Database
from app.integrations.google_sheets import SheetData
from app.models import Bank, Channel, DuplicateLeadReview, Lead, LeadBank, Partner, Payment, User

SHEET_MODELS = (
    ("Пользователи", User),
    ("Партнёры", Partner),
    ("Каналы", Channel),
    ("Заявки", Lead),
    ("Банки", Bank),
    ("Банки заявок", LeadBank),
    ("Выплаты", Payment),
    ("Проверка дублей", DuplicateLeadReview),
)


class SheetsSnapshotService:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def build(self) -> list[SheetData]:
        sheets: list[SheetData] = []
        async with self.database.session() as session:
            for title, model in SHEET_MODELS:
                columns = tuple(column.name for column in model.__table__.columns)
                entities = await session.scalars(select(model).order_by(model.id))
                rows = [
                    [serialize_cell(getattr(entity, column)) for column in columns]
                    for entity in entities
                ]
                sheets.append(SheetData(title=title, headers=columns, rows=rows))
        sheets.extend(
            [
                SheetData("Справочники", ("group", "key", "value", "active"), []),
                SheetData("Ошибки синхронизации", ("created_at", "sheet", "row_id", "error"), []),
            ]
        )
        return sheets


def serialize_cell(value: Any) -> str | int | float | bool:
    if value is None:
        return ""
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
