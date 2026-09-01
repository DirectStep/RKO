import pytest

from app.integrations.bank_conditions import (
    BankConditionRow,
    BankConditionsGateway,
    parse_bank_condition_rows,
)
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
def test_invalid_bank_condition_rows_are_rejected(values: list[list[str]], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_bank_condition_rows(values)


def test_bank_names_are_normalized_for_matching() -> None:
    assert normalize_bank_name("  Ё-Банк   Бизнес ") == "е-банк бизнес"


def test_duplicate_condition_bank_names_are_rejected() -> None:
    values = [
        ["Название банка", "Целевое действие для клиента"],
        ["Ё-Банк", "Первое условие"],
        ["е-банк", "Второе условие"],
    ]

    with pytest.raises(ValueError, match="банк указан дважды"):
        parse_bank_condition_rows(values)


class FakeWorksheet:
    def __init__(self, values: list[list[str]]) -> None:
        self.values = values
        self.updated_ranges: list[str] = []

    def get_all_values(self) -> list[list[str]]:
        return self.values

    def update(self, values: list[list[str]], range_name: str, *, raw: bool) -> None:
        assert raw is True
        self.updated_ranges.append(range_name)
        start = range_name.split(":", maxsplit=1)[0]
        row_number = int("".join(character for character in start if character.isdigit()))
        while len(self.values) < row_number:
            self.values.append([])
        self.values[row_number - 1] = values[0]


def gateway_with(values: list[list[str]]) -> BankConditionsGateway:
    gateway = object.__new__(BankConditionsGateway)
    gateway.worksheet = FakeWorksheet(values)
    return gateway


def test_condition_gateway_adds_and_updates_condition() -> None:
    values = [
        ["Название банка", "Целевое действие для клиента"],
        ["Старый банк", "Старое условие"],
    ]
    gateway = gateway_with(values)

    rows = gateway.upsert(
        BankConditionRow("Новый банк", "Новое условие", 0),
        original_bank_name="Старый банк",
    )

    assert rows == [BankConditionRow("Новый банк", "Новое условие", 2)]
    assert values[1] == ["Новый банк", "Новое условие"]


def test_condition_gateway_appends_new_condition() -> None:
    values = [
        ["Название банка", "Целевое действие для клиента"],
        ["Существующий банк", "Существующее условие"],
    ]

    rows = gateway_with(values).upsert(BankConditionRow("Новый банк", "Новое условие", 0))

    assert rows[-1] == BankConditionRow("Новый банк", "Новое условие", 3)
    assert values[2] == ["Новый банк", "Новое условие"]


def test_condition_gateway_clears_removed_condition() -> None:
    values = [
        ["Название банка", "Целевое действие для клиента"],
        ["Банк", "Условие"],
    ]

    rows = gateway_with(values).upsert(BankConditionRow("Банк", "", 0))

    assert rows == []
    assert values[1] == ["", ""]


def test_condition_gateway_rolls_back_appended_condition() -> None:
    values = [["Название банка", "Целевое действие для клиента"]]
    gateway = gateway_with(values)
    write = gateway.plan_upsert(BankConditionRow("Новый банк", "Новое условие", 0))

    gateway.apply(write)
    rows = gateway.rollback(write)

    assert rows == []
    assert values[1] == ["", ""]
