from dataclasses import dataclass
from typing import Any

import gspread

LEAD_REGISTRY_TITLE = "РКО — база лидов"
LEAD_REGISTRY_HEADERS = (
    "ID заявки",
    "Дата активации",
    "Лид",
    "Менеджер",
    "Банк",
    "Статус заявки",
    "Ожидаемая дата выплаты",
    "Дата фактической выплаты",
    "Сумма выплаты",
    "Статус выплаты",
    "Комментарий",
)


@dataclass(frozen=True)
class SheetData:
    title: str
    headers: tuple[str, ...]
    rows: list[list[str | int | float | bool]]


@dataclass(frozen=True)
class LeadRegistryRow:
    application_id: str
    activated_at: str
    lead: str
    manager: str
    bank: str
    application_status: str
    expected_payment_at: str
    paid_at: str = ""
    amount: float | str = ""
    payment_status: str = "Ожидается"
    comment: str = ""

    def values(self) -> list[str | float]:
        return [
            self.application_id,
            self.activated_at,
            self.lead,
            self.manager,
            self.bank,
            self.application_status,
            self.expected_payment_at,
            self.paid_at,
            self.amount,
            self.payment_status,
            self.comment,
        ]


class LeadRegistryRowNotFound(RuntimeError):
    pass


class GoogleSheetsGateway:
    def __init__(self, spreadsheet_id: str, credentials_file: str) -> None:
        client = gspread.service_account(filename=credentials_file)
        self.spreadsheet = client.open_by_key(spreadsheet_id)

    def replace_all(self, sheets: list[SheetData]) -> None:
        existing = {worksheet.title: worksheet for worksheet in self.spreadsheet.worksheets()}
        for sheet in sheets:
            worksheet = existing.get(sheet.title)
            if worksheet is None:
                worksheet = self.spreadsheet.add_worksheet(
                    title=sheet.title,
                    rows=max(len(sheet.rows) + 10, 100),
                    cols=max(len(sheet.headers), 1),
                )
            values: list[list[Any]] = [list(sheet.headers), *sheet.rows]
            worksheet.clear()
            worksheet.update(values, "A1", raw=True)
            worksheet.freeze(rows=1)

    def ensure_lead_registry(self) -> gspread.Worksheet:
        created = False
        try:
            worksheet = self.spreadsheet.worksheet(LEAD_REGISTRY_TITLE)
        except gspread.WorksheetNotFound:
            worksheet = self.spreadsheet.add_worksheet(
                title=LEAD_REGISTRY_TITLE, rows=1000, cols=len(LEAD_REGISTRY_HEADERS)
            )
            created = True
        current_headers = worksheet.row_values(1)
        headers_changed = current_headers != list(LEAD_REGISTRY_HEADERS)
        if headers_changed:
            worksheet.update([list(LEAD_REGISTRY_HEADERS)], "A1:K1", raw=True)
        if created or headers_changed:
            worksheet.freeze(rows=1)
            worksheet.set_basic_filter("A1:K")
            worksheet.format(
                "A1:K1",
                {
                    "backgroundColor": {"red": 0.88, "green": 0.93, "blue": 1.0},
                    "textFormat": {"bold": True},
                    "horizontalAlignment": "CENTER",
                },
            )
            worksheet.format(
                "I2:I",
                {"numberFormat": {"type": "NUMBER", "pattern": '#,##0.00 "₽"'}},
            )
            worksheet.columns_auto_resize(0, len(LEAD_REGISTRY_HEADERS))
        return worksheet

    def upsert_lead_activation(self, row: LeadRegistryRow) -> None:
        worksheet = self.ensure_lead_registry()
        row_number, existing = self._find_registry_row(worksheet, row.application_id, row.bank)
        values = row.values()
        if row_number is None:
            worksheet.append_row(values, value_input_option="RAW")
            return
        values[7:11] = existing[7:11]
        worksheet.update([values], f"A{row_number}:K{row_number}", raw=True)

    def update_lead_payment(
        self, application_id: str, bank: str, paid_at: str, amount: float,
        status: str = "Выплачено"
    ) -> None:
        worksheet = self.ensure_lead_registry()
        row_number, _ = self._find_registry_row(worksheet, application_id, bank)
        if row_number is None:
            raise LeadRegistryRowNotFound(
                f"Банк {bank} заявки {application_id} не найден в листе {LEAD_REGISTRY_TITLE}"
            )
        worksheet.update([[paid_at, amount, status]], f"H{row_number}:J{row_number}", raw=True)

    @staticmethod
    def _find_registry_row(
        worksheet: gspread.Worksheet, application_id: str, bank: str
    ) -> tuple[int | None, list[str]]:
        matches = [
            (index, values)
            for index, values in enumerate(worksheet.get_all_values()[1:], start=2)
            if len(values) > 4 and values[0] == application_id and values[4] == bank
        ]
        if len(matches) > 1:
            raise RuntimeError(f"Найдены дубли банка {bank} заявки {application_id} в Google Sheets")
        if not matches:
            return None, []
        row_number, values = matches[0]
        return row_number, [*values, *([""] * (len(LEAD_REGISTRY_HEADERS) - len(values)))]
