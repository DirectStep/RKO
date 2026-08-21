import pytest

from app.integrations.bank_conditions import BankConditionRow, parse_bank_condition_rows
from app.services.bank_conditions import normalize_bank_name


def test_bank_condition_rows_are_parsed() -> None:
    values = [
        [
            "Название банка",
            "Целевое действие для клиента",
            "Выплата клиенту",
            "Активно",
            "Порядок",
        ],
        ["Демо Банк", "Сделать первый платёж", "5 000 ₽", "Да", "10"],
        ["Скрытый Банк", "Пополнить счёт", "", "Нет", "20"],
    ]

    assert parse_bank_condition_rows(values) == [
        BankConditionRow("Демо Банк", "Сделать первый платёж", "5 000 ₽", True, 10, 2),
        BankConditionRow("Скрытый Банк", "Пополнить счёт", "Уточняется", False, 20, 3),
    ]


@pytest.mark.parametrize(
    ("values", "message"),
    [
        ([], "пуст"),
        ([["Банк", "Действие"]], "Заголовки"),
        (
            [
                [
                    "Название банка",
                    "Целевое действие для клиента",
                    "Выплата клиенту",
                    "Активно",
                    "Порядок",
                ],
                ["Банк", "", "1 000 ₽", "Да", "1"],
            ],
            "заполните",
        ),
        (
            [
                [
                    "Название банка",
                    "Целевое действие для клиента",
                    "Выплата клиенту",
                    "Активно",
                    "Порядок",
                ],
                ["Банк", "Действие", "1 000 ₽", "Возможно", "1"],
            ],
            "Да или Нет",
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
