import pytest

from app.integrations.bank_conditions import BankConditionRow, parse_bank_condition_sheets
from app.services.bank_conditions import normalize_bank_name


def condition_sheets() -> dict[str, list[list[str]]]:
    return {
        "Оборот": [
            ["Название банка", "Сумма оборота, ₽", "Количество платежей"],
            ["Демо Банк", "10 000 ₽", "1"],
        ],
        "Открытие": [
            ["Название банка"],
            ["Ozon Банк"],
            ["Альфа-Банк"],
        ],
        "Холд": [
            ["Название банка", "Сумма холда, ₽", "Количество дней"],
            ["ВТБ", "6 000 ₽", "4"],
        ],
        "Тариф": [
            ["Название банка", "Тариф, ₽"],
            ["ПСБ", "700 ₽"],
        ],
        "Оборот + тариф": [
            ["Название банка", "Сумма оборота, ₽", "Количество платежей", "Тариф, ₽"],
            ["Ак Барс банк", "35 000 ₽", "4", "690 ₽"],
        ],
    }


def test_all_condition_types_and_aliases_are_parsed() -> None:
    rows = parse_bank_condition_sheets(condition_sheets())
    by_name = {row.bank_name: row.action_text for row in rows}

    assert by_name["Акбарс"] == (
        "Сделать оборот 35 000 ₽ — минимум 4 платежа "
        "и оплатить тариф стоимостью 690 ₽"
    )
    assert by_name["Акбарс Банк"] == by_name["Акбарс"]
    assert by_name["Демо Банк"] == "Сделать оборот 10 000 ₽ — минимум 1 платёж"
    assert by_name["Озон (можно онлайн даже без КЭП)"] == "Открыть расчётный счёт"
    assert by_name["Озон"] == by_name["Озон (можно онлайн даже без КЭП)"]
    assert by_name["ВТБ"] == "Пополнить счёт на 6 000 ₽ и удерживать сумму 4 дня"
    assert by_name["ПСБ"] == "Оплатить тариф стоимостью 700 ₽"
    assert by_name["Альфа (ИП+РКО) +5к лиду бонусами сама альфа платит"] == "Открыть расчётный счёт"
    assert by_name["Альфа счёт (без открытия ИП в Альфе)"] == "Открыть расчётный счёт"
    assert by_name["Альфа-Банк (ИП+счёт)"] == "Открыть расчётный счёт"
    assert by_name["Альфа-Банк (без открытия ИП)"] == "Открыть расчётный счёт"


def test_saint_petersburg_condition_matches_current_catalog_name() -> None:
    sheets = condition_sheets()
    sheets["Оборот"].append(["Банк Санкт-Петербург", "10 000 ₽", "3"])

    by_name = {row.bank_name: row.action_text for row in parse_bank_condition_sheets(sheets)}

    assert by_name["Банк Санкт-Петербург"] == "Сделать оборот 10 000 ₽ — минимум 3 платежа"
    assert by_name["БСПБ (гео маленькое)"] == by_name["Банк Санкт-Петербург"]


def test_multiple_conditions_are_combined_as_a_list() -> None:
    sheets = condition_sheets()
    sheets["Тариф"].append(["ВТБ", "500 ₽"])

    rows = parse_bank_condition_sheets(sheets)
    condition = next(row.action_text for row in rows if row.bank_name == "ВТБ")

    assert condition == (
        "• Пополнить счёт на 6 000 ₽ и удерживать сумму 4 дня\n"
        "• Оплатить тариф стоимостью 500 ₽"
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda sheets: sheets.pop("Холд"), "Холд"),
        (lambda sheets: sheets.pop("Оборот + тариф"), "Оборот \\+ тариф"),
        (lambda sheets: sheets["Оборот"].__setitem__(0, ["Банк"]), "Оборот"),
        (lambda sheets: sheets["Тариф"].append(["Банк", ""]), "заполните"),
        (lambda sheets: sheets["Холд"].append(["Банк", "100 ₽", "0"]), "больше нуля"),
        (lambda sheets: sheets["Оборот + тариф"].append(["Банк", "100 ₽", "1", ""]), "заполните"),
    ],
)
def test_invalid_condition_sheets_are_rejected(mutation: object, message: str) -> None:
    sheets = condition_sheets()
    mutation(sheets)  # type: ignore[operator]

    with pytest.raises(ValueError, match=message):
        parse_bank_condition_sheets(sheets)


def test_bank_names_are_normalized_for_matching() -> None:
    assert normalize_bank_name("  Ё-Банк   Бизнес ") == "е-банк бизнес"


def test_duplicate_bank_in_one_sheet_is_rejected() -> None:
    sheets = condition_sheets()
    sheets["Открытие"].append(["ozon банк"])

    with pytest.raises(ValueError, match="дважды"):
        parse_bank_condition_sheets(sheets)


def test_row_shape_is_stable() -> None:
    rows = parse_bank_condition_sheets(condition_sheets())

    assert all(isinstance(row, BankConditionRow) for row in rows)
    assert all(row.source_row >= 2 for row in rows)
