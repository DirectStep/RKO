from datetime import UTC, datetime

from sqlalchemy import delete, select

from app.database import Database
from app.integrations.bank_conditions import BankConditionRow
from app.models import BankActivationCondition


def normalize_bank_name(value: str) -> str:
    return " ".join(value.casefold().replace("ё", "е").split())


class BankConditionsService:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def replace_all(self, rows: list[BankConditionRow]) -> int:
        normalized_rows: dict[str, BankConditionRow] = {}
        for row in rows:
            normalized_name = normalize_bank_name(row.bank_name)
            if normalized_name in normalized_rows:
                other = normalized_rows[normalized_name]
                raise ValueError(
                    f"Строки {other.source_row} и {row.source_row}: банк указан дважды"
                )
            normalized_rows[normalized_name] = row

        synced_at = datetime.now(UTC)
        async with self.database.session() as session, session.begin():
            existing = list(await session.scalars(select(BankActivationCondition)))
            existing_by_name = {item.normalized_bank_name: item for item in existing}
            for display_order, (normalized_name, row) in enumerate(
                normalized_rows.items(), start=1
            ):
                condition = existing_by_name.get(normalized_name)
                if condition is None:
                    condition = BankActivationCondition(normalized_bank_name=normalized_name)
                    session.add(condition)
                condition.bank_name = row.bank_name
                condition.action_text = row.action_text
                condition.payout_text = "Уточняется"
                condition.active = True
                condition.display_order = display_order
                condition.source_row = row.source_row
                condition.synced_at = synced_at
            await session.execute(
                delete(BankActivationCondition).where(
                    BankActivationCondition.normalized_bank_name.not_in(normalized_rows)
                )
            )
        return len(normalized_rows)
