import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import gspread

EXPECTED_HEADERS = (
    "Код предложения",
    "Название предложения",
    "Можно открыть онлайн",
    "База выплаты",
    "Выплата лиду",
    "Выплату лиду платит банк отдельно",
    "Активно",
    "Порядок",
)

FORMULA_ERRORS = ("#REF!", "#N/A", "#VALUE!", "#NAME?", "#DIV/0!")


@dataclass(frozen=True)
class BankRateRow:
    offer_code: str
    bank_name: str
    online_text: str
    base_payout: Decimal
    lead_payout: Decimal
    lead_payout_paid_separately: bool
    active: bool
    display_order: int
    source_row: int


@dataclass(frozen=True)
class BankRateWrite:
    target_row: int
    previous: tuple[str, ...]
    serialized: tuple[str, ...]


def _decimal(value: str, row: int, column: str) -> Decimal:
    clean = re.sub(r"[^0-9,.\-]", "", value).replace(",", ".")
    try:
        result = Decimal(clean)
    except InvalidOperation as error:
        raise ValueError(f"Строка {row}: «{column}» должна быть числом") from error
    if not result.is_finite() or result < 0:
        raise ValueError(f"Строка {row}: «{column}» должна быть неотрицательным числом")
    return result.quantize(Decimal("0.01"))


def _boolean(value: str, row: int, column: str) -> bool:
    normalized = value.strip().casefold()
    if normalized in {"да", "yes", "true", "1"}:
        return True
    if normalized in {"нет", "no", "false", "0"}:
        return False
    raise ValueError(f"Строка {row}: в «{column}» укажите Да или Нет")


def parse_bank_rate_rows(values: list[list[str]]) -> list[BankRateRow]:
    if not values:
        raise ValueError("Лист ставок банков пуст")
    headers = tuple(cell.strip() for cell in values[0][: len(EXPECTED_HEADERS)])
    if headers != EXPECTED_HEADERS:
        raise ValueError("Заголовки листа ставок банков не совпадают с шаблоном")

    rows: list[BankRateRow] = []
    seen_codes: dict[str, int] = {}
    seen_names: dict[str, int] = {}
    for source_row, values_row in enumerate(values[1:], start=2):
        cells = [*values_row, *("" for _ in EXPECTED_HEADERS)][: len(EXPECTED_HEADERS)]
        if not any(cell.strip() for cell in cells):
            continue
        for cell in cells:
            if cell.strip().upper().startswith(FORMULA_ERRORS):
                raise ValueError(f"Строка {source_row}: ошибка формулы Google Sheets")
        offer_code, bank_name, online_text = (cell.strip() for cell in cells[:3])
        if not offer_code or not bank_name:
            raise ValueError(f"Строка {source_row}: заполни код и название предложения")
        normalized_code = offer_code.casefold()
        normalized_name = " ".join(bank_name.casefold().split())
        if normalized_code in seen_codes:
            raise ValueError(
                f"Строки {seen_codes[normalized_code]} и {source_row}: код указан дважды"
            )
        if normalized_name in seen_names:
            raise ValueError(
                f"Строки {seen_names[normalized_name]} и {source_row}: название указано дважды"
            )
        seen_codes[normalized_code] = source_row
        seen_names[normalized_name] = source_row
        try:
            display_order = int(cells[7].strip())
        except ValueError as error:
            raise ValueError(f"Строка {source_row}: «Порядок» должен быть целым числом") from error
        if display_order < 0:
            raise ValueError(f"Строка {source_row}: «Порядок» не может быть отрицательным")
        rows.append(
            BankRateRow(
                offer_code=offer_code,
                bank_name=bank_name,
                online_text=online_text or "Уточняется",
                base_payout=_decimal(cells[3], source_row, "База выплаты"),
                lead_payout=_decimal(cells[4], source_row, "Выплата лиду"),
                lead_payout_paid_separately=_boolean(
                    cells[5], source_row, "Выплату лиду платит банк отдельно"
                ),
                active=_boolean(cells[6], source_row, "Активно"),
                display_order=display_order,
                source_row=source_row,
            )
        )
    return rows


class BankRatesGateway:
    def __init__(self, spreadsheet_id: str, worksheet_title: str, credentials_file: str) -> None:
        client = gspread.service_account(filename=credentials_file)
        self.worksheet = client.open_by_key(spreadsheet_id).worksheet(worksheet_title)

    def fetch(self) -> list[BankRateRow]:
        return parse_bank_rate_rows(self.worksheet.get_all_values())

    def plan_upsert(
        self,
        row: BankRateRow,
        *,
        original_offer_code: str | None = None,
    ) -> BankRateWrite:
        values = self.worksheet.get_all_values()
        parse_bank_rate_rows(values)
        lookup = (original_offer_code or row.offer_code).casefold()
        target_row = next(
            (
                number
                for number, cells in enumerate(values[1:], start=2)
                if cells and cells[0].strip().casefold() == lookup
            ),
            None,
        )
        if original_offer_code is not None and target_row is None:
            raise ValueError("Редактируемое предложение не найдено в Google Sheets")
        if target_row is None:
            target_row = len(values) + 1
        serialized = (
            row.offer_code,
            row.bank_name,
            row.online_text,
            str(row.base_payout),
            str(row.lead_payout),
            "Да" if row.lead_payout_paid_separately else "Нет",
            "Да" if row.active else "Нет",
            str(row.display_order),
        )
        prospective = [list(cells) for cells in values]
        while len(prospective) < target_row:
            prospective.append([])
        previous = tuple([*prospective[target_row - 1], *("" for _ in range(8))][:8])
        current_condition = (
            prospective[target_row - 1][8]
            if len(prospective[target_row - 1]) > 8
            else ""
        )
        prospective[target_row - 1] = [*serialized, current_condition]
        parse_bank_rate_rows(prospective)
        return BankRateWrite(target_row, previous, serialized)

    def apply(self, write: BankRateWrite) -> list[BankRateRow]:
        self.worksheet.update(
            [list(write.serialized)],
            f"A{write.target_row}:H{write.target_row}",
            raw=True,
        )
        return self.fetch()

    def rollback(self, write: BankRateWrite) -> list[BankRateRow]:
        self.worksheet.update(
            [list(write.previous)],
            f"A{write.target_row}:H{write.target_row}",
            raw=True,
        )
        return self.fetch()

    def upsert(
        self,
        row: BankRateRow,
        *,
        original_offer_code: str | None = None,
    ) -> list[BankRateRow]:
        return self.apply(
            self.plan_upsert(row, original_offer_code=original_offer_code)
        )

    def set_active(self, offer_code: str, active: bool) -> list[BankRateRow]:
        values = self.worksheet.get_all_values()
        parse_bank_rate_rows(values)
        target_row = next(
            (
                number
                for number, cells in enumerate(values[1:], start=2)
                if cells and cells[0].strip().casefold() == offer_code.casefold()
            ),
            None,
        )
        if target_row is None:
            raise ValueError("Предложение банка не найдено в листе «Справочник для бота»")
        self.worksheet.update([["Да" if active else "Нет"]], f"G{target_row}", raw=True)
        return self.fetch()
