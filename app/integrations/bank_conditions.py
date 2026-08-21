from dataclasses import dataclass

import gspread

EXPECTED_HEADERS = (
    "Название банка",
    "Целевое действие для клиента",
    "Выплата клиенту",
    "Активно",
    "Порядок",
)


@dataclass(frozen=True)
class BankConditionRow:
    bank_name: str
    action_text: str
    payout_text: str
    active: bool
    display_order: int
    source_row: int


def parse_bank_condition_rows(values: list[list[str]]) -> list[BankConditionRow]:
    if not values:
        raise ValueError("Лист условий банков пуст")
    headers = tuple(cell.strip() for cell in values[0][: len(EXPECTED_HEADERS)])
    if headers != EXPECTED_HEADERS:
        raise ValueError("Заголовки листа условий банков не совпадают с шаблоном")

    rows: list[BankConditionRow] = []
    for source_row, values_row in enumerate(values[1:], start=2):
        cells = [*values_row, "", "", "", "", ""][:5]
        if not any(cell.strip() for cell in cells):
            continue
        bank_name, action_text, payout_text, active_text, order_text = (
            cell.strip() for cell in cells
        )
        if not bank_name or not action_text:
            raise ValueError(f"Строка {source_row}: заполните банк и целевое действие")
        normalized_active = active_text.lower()
        if normalized_active not in {"да", "нет"}:
            raise ValueError(f"Строка {source_row}: в колонке «Активно» укажите Да или Нет")
        try:
            display_order = int(order_text or 0)
        except ValueError as error:
            raise ValueError(f"Строка {source_row}: порядок должен быть целым числом") from error
        rows.append(
            BankConditionRow(
                bank_name=bank_name,
                action_text=action_text,
                payout_text=payout_text or "Уточняется",
                active=normalized_active == "да",
                display_order=display_order,
                source_row=source_row,
            )
        )
    if not rows:
        raise ValueError("В листе условий банков нет строк с данными")
    return rows


class BankConditionsGateway:
    def __init__(self, spreadsheet_id: str, worksheet_title: str, credentials_file: str) -> None:
        client = gspread.service_account(filename=credentials_file)
        self.worksheet = client.open_by_key(spreadsheet_id).worksheet(worksheet_title)

    def fetch(self) -> list[BankConditionRow]:
        return parse_bank_condition_rows(self.worksheet.get_all_values())
