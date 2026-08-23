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
    raise ValueError(f"Строка {row}: в «{column}» укажи Да или Нет")


def parse_bank_rate_rows(values: list[list[str]]) -> list[BankRateRow]:
    if not values:
        raise ValueError("Лист ставок банков пуст")
    headers = tuple(cell.strip() for cell in values[0][: len(EXPECTED_HEADERS)])
    if headers != EXPECTED_HEADERS:
        raise ValueError("Заголовки листа ставок банков не совпадают с шаблоном")

    rows: list[BankRateRow] = []
    for source_row, values_row in enumerate(values[1:], start=2):
        cells = [*values_row, *("" for _ in EXPECTED_HEADERS)][: len(EXPECTED_HEADERS)]
        if not any(cell.strip() for cell in cells):
            continue
        offer_code, bank_name, online_text = (cell.strip() for cell in cells[:3])
        if not offer_code or not bank_name:
            raise ValueError(f"Строка {source_row}: заполни код и название предложения")
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
