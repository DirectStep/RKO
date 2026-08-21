import pytest

from app.integrations.bank_conditions import BankConditionRow, parse_bank_condition_rows
from app.services.bank_conditions import normalize_bank_name


def test_bank_condition_rows_are_parsed() -> None:
    values = [
        ["Название банка", "Целевое действие для клиента"],
        ["Демо Банк", "Сделать первый платёж"],
        ["Другой Банк", "Пополнить счёт"],
    ]

    assert parse_bank_condition_rows(values) == [
        BankConditionRow("Демо Банк", "Сделать первый платёж", 2),
        BankConditionRow("Другой Банк", "Пополнить счёт", 3),
    ]


def test_header_only_sheet_is_a_valid_empty_bank_list() -> None:
    values = [["Название банка", "Целевое действие для клиента"]]

    assert parse_bank_condition_rows(values) == []


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ([], "пуст"),
        ([["Банк", "Действие"]], "Заголовки"),
        (
            [["Название банка", "Целевое действие для клиента"], ["Банк", ""]],
            "заполните",
        ),
    ],
)
def test_invalid_bank_condition_rows_are_rejected(
    values: list[list[str]], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        parse_bank_condition_rows(values)


def test_bank_names_are_normalized_for_matching() -> None:
    assert normalize_bank_name("  Ё-Банк   Бизнес ") == "е-банк бизнес"
