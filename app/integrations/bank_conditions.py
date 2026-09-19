from collections.abc import Mapping
from dataclasses import dataclass

import gspread

WORKSHEET_HEADERS = {
    "Оборот": ("Название банка", "Сумма оборота, ₽", "Количество платежей"),
    "Открытие": ("Название банка",),
    "Холд": ("Название банка", "Сумма холда, ₽", "Количество дней"),
    "Тариф": ("Название банка", "Тариф, ₽"),
}

BANK_ALIASES = {
    "ак барс банк": ("Акбарс",),
    "альфа-банк": (
        "Альфа (ИП+РКО) +5к лиду бонусами сама альфа платит",
        "Альфа счёт (без открытия ИП в Альфе)",
    ),
    "банк санкт-петербург": ("БСПБ (гео маленькое)",),
    "ozon банк": ("Озон (можно онлайн даже без КЭП)",),
}


@dataclass(frozen=True)
class BankConditionRow:
    bank_name: str
    action_text: str
    source_row: int


def _normalize(value: str) -> str:
    return " ".join(value.casefold().replace("ё", "е").split())


def _clean(value: str) -> str:
    return " ".join(value.split())


def _positive_int(value: str, sheet: str, row: int, column: str) -> int:
    try:
        result = int(_clean(value))
    except ValueError as error:
        raise ValueError(
            f"Лист «{sheet}», строка {row}: «{column}» должно быть целым числом"
        ) from error
    if result <= 0:
        raise ValueError(
            f"Лист «{sheet}», строка {row}: «{column}» должно быть больше нуля"
        )
    return result


def _plural(number: int, one: str, few: str, many: str) -> str:
    if number % 10 == 1 and number % 100 != 11:
        return one
    if number % 10 in {2, 3, 4} and number % 100 not in {12, 13, 14}:
        return few
    return many


def _condition_text(sheet: str, cells: list[str], row: int) -> str:
    if sheet == "Оборот":
        count = _positive_int(cells[2], sheet, row, "Количество платежей")
        return (
            f"Сделать оборот {_clean(cells[1])} — минимум {count} "
            f"{_plural(count, 'платёж', 'платежа', 'платежей')}"
        )
    if sheet == "Открытие":
        return "Открыть расчётный счёт"
    if sheet == "Холд":
        count = _positive_int(cells[2], sheet, row, "Количество дней")
        return (
            f"Пополнить счёт на {_clean(cells[1])} и удерживать сумму {count} "
            f"{_plural(count, 'день', 'дня', 'дней')}"
        )
    return f"Оплатить тариф стоимостью {_clean(cells[1])}"


def parse_bank_condition_sheets(
    sheets: Mapping[str, list[list[str]]],
) -> list[BankConditionRow]:
    conditions: dict[str, list[str]] = {}
    display_names: dict[str, str] = {}
    source_rows: dict[str, int] = {}

    for sheet, expected_headers in WORKSHEET_HEADERS.items():
        values = sheets.get(sheet)
        if not values:
            raise ValueError(f"Лист «{sheet}» пуст или не найден")
        headers = tuple(cell.strip() for cell in values[0][: len(expected_headers)])
        if headers != expected_headers:
            raise ValueError(f"Заголовки листа «{sheet}» не совпадают с шаблоном")
        seen_in_sheet: set[str] = set()
        for row_number, values_row in enumerate(values[1:], start=2):
            cells = [*values_row, *("" for _ in expected_headers)][: len(expected_headers)]
            if not any(cell.strip() for cell in cells):
                continue
            if any(not cell.strip() for cell in cells):
                raise ValueError(f"Лист «{sheet}», строка {row_number}: заполните все поля")
            source_name = _clean(cells[0])
            source_key = _normalize(source_name)
            if source_key in seen_in_sheet:
                raise ValueError(
                    f"Лист «{sheet}», строка {row_number}: банк указан дважды"
                )
            seen_in_sheet.add(source_key)
            text = _condition_text(sheet, cells, row_number)
            for target_name in BANK_ALIASES.get(source_key, (source_name,)):
                target_key = _normalize(target_name)
                conditions.setdefault(target_key, []).append(text)
                display_names[target_key] = target_name
                source_rows.setdefault(target_key, row_number)

    return [
        BankConditionRow(
            bank_name=display_names[key],
            action_text=(texts[0] if len(texts) == 1 else "\n".join(f"• {text}" for text in texts)),
            source_row=source_rows[key],
        )
        for key, texts in conditions.items()
    ]


class BankConditionsGateway:
    def __init__(self, spreadsheet_id: str, credentials_file: str) -> None:
        client = gspread.service_account(filename=credentials_file)
        self.spreadsheet = client.open_by_key(spreadsheet_id)

    def fetch(self) -> list[BankConditionRow]:
        values = {
            title: self.spreadsheet.worksheet(title).get_all_values()
            for title in WORKSHEET_HEADERS
        }
        return parse_bank_condition_sheets(values)
