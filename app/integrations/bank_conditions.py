from dataclasses import dataclass

import gspread

EXPECTED_HEADERS = (
    "Название банка",
    "Целевое действие для клиента",
)


@dataclass(frozen=True)
class BankConditionRow:
    bank_name: str
    action_text: str
    source_row: int


@dataclass(frozen=True)
class BankConditionWrite:
    target_row: int | None
    previous: tuple[str, str]
    serialized: tuple[str, str]


def parse_bank_condition_rows(values: list[list[str]]) -> list[BankConditionRow]:
    if not values:
        raise ValueError("Лист условий банков пуст")
    headers = tuple(cell.strip() for cell in values[0][: len(EXPECTED_HEADERS)])
    if headers != EXPECTED_HEADERS:
        raise ValueError("Заголовки листа условий банков не совпадают с шаблоном")

    rows: list[BankConditionRow] = []
    seen_names: dict[str, int] = {}
    for source_row, values_row in enumerate(values[1:], start=2):
        cells = [*values_row, "", ""][:2]
        if not any(cell.strip() for cell in cells):
            continue
        bank_name, action_text = (cell.strip() for cell in cells)
        if not bank_name or not action_text:
            raise ValueError(f"Строка {source_row}: заполните банк и целевое действие")
        normalized_name = _normalize(bank_name)
        if normalized_name in seen_names:
            raise ValueError(
                f"Строки {seen_names[normalized_name]} и {source_row}: банк указан дважды"
            )
        seen_names[normalized_name] = source_row
        rows.append(
            BankConditionRow(
                bank_name=bank_name,
                action_text=action_text,
                source_row=source_row,
            )
        )
    return rows


class BankConditionsGateway:
    def __init__(self, spreadsheet_id: str, worksheet_title: str, credentials_file: str) -> None:
        client = gspread.service_account(filename=credentials_file)
        self.worksheet = client.open_by_key(spreadsheet_id).worksheet(worksheet_title)

    def fetch(self) -> list[BankConditionRow]:
        return parse_bank_condition_rows(self.worksheet.get_all_values())

    def plan_upsert(
        self,
        row: BankConditionRow,
        *,
        original_bank_name: str | None = None,
    ) -> BankConditionWrite:
        values = self.worksheet.get_all_values()
        parse_bank_condition_rows(values)
        lookup = _normalize(original_bank_name or row.bank_name)
        target_row = next(
            (
                number
                for number, cells in enumerate(values[1:], start=2)
                if cells and _normalize(cells[0]) == lookup
            ),
            None,
        )
        clean_name = row.bank_name.strip()
        clean_action = row.action_text.strip()
        if not clean_action:
            if target_row is None:
                return BankConditionWrite(None, ("", ""), ("", ""))
            previous = tuple([*values[target_row - 1], "", ""][:2])
            prospective = [list(cells) for cells in values]
            prospective[target_row - 1] = []
            parse_bank_condition_rows(prospective)
            return BankConditionWrite(target_row, previous, ("", ""))

        serialized = (clean_name, clean_action)
        if target_row is None:
            target_row = len(values) + 1
            previous = ("", "")
        else:
            previous = tuple([*values[target_row - 1], "", ""][:2])
        prospective = [list(cells) for cells in values]
        while len(prospective) < target_row:
            prospective.append([])
        prospective[target_row - 1] = list(serialized)
        parse_bank_condition_rows(prospective)
        return BankConditionWrite(target_row, previous, serialized)

    def apply(self, write: BankConditionWrite) -> list[BankConditionRow]:
        if write.target_row is not None:
            self.worksheet.update(
                [list(write.serialized)],
                f"A{write.target_row}:B{write.target_row}",
                raw=True,
            )
        return self.fetch()

    def rollback(self, write: BankConditionWrite) -> list[BankConditionRow]:
        if write.target_row is not None:
            self.worksheet.update(
                [list(write.previous)],
                f"A{write.target_row}:B{write.target_row}",
                raw=True,
            )
        return self.fetch()

    def upsert(
        self,
        row: BankConditionRow,
        *,
        original_bank_name: str | None = None,
    ) -> list[BankConditionRow]:
        return self.apply(
            self.plan_upsert(row, original_bank_name=original_bank_name)
        )


def _normalize(value: str) -> str:
    return " ".join(value.casefold().replace("ё", "е").split())
