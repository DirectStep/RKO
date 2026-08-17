from dataclasses import dataclass
from typing import Any

import gspread


@dataclass(frozen=True)
class SheetData:
    title: str
    headers: tuple[str, ...]
    rows: list[list[str | int | float | bool]]


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
