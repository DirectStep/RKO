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


def parse_bank_condition_rows(values: list[list[str]]) -> list[BankConditionRow]:
    if not values:
        raise ValueError("Лист условий банков пуст")
    headers = tuple(cell.strip() for cell in values[0][: len(EXPECTED_HEADERS)])
    if headers != EXPECTED_HEADERS:
        raise ValueError("Заголовки листа условий банков не совпадают с шаблоном")

    rows: list[BankConditionRow] = []
    for source_row, values_row in enumerate(values[1:], start=2):
        cells = [*values_row, "", ""][:2]
        if not any(cell.strip() for cell in cells):
            continue
        bank_name, action_text = (cell.strip() for cell in cells)
        if not bank_name or not action_text:
            raise ValueError(f"Строка {source_row}: заполните банк и целевое действие")
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
