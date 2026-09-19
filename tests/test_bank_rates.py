from decimal import Decimal
from uuid import uuid4

import pytest

from app.domain.enums import UserRole
from app.domain.operations import DomainError
from app.integrations.bank_rates import BankRateRow, BankRatesGateway, parse_bank_rate_rows
from app.services.workflow import WorkflowService


def test_bank_rate_rows_are_parsed() -> None:
    values = [
        [
            "Код предложения",
            "Название предложения",
            "Можно открыть онлайн",
            "База выплаты",
            "Выплата лиду",
            "Выплата лиду без округления",
            "Выплату лиду платит банк отдельно",
            "Активно",
            "Порядок",
        ],
        [
            "alpha-ip",
            "Альфа ИП",
            "Нет",
            "10 000,00 ₽",
            "5 000",
            "5 123,45",
            "Да",
            "Да",
            "10",
        ],
    ]

    assert parse_bank_rate_rows(values) == [
        BankRateRow(
            offer_code="alpha-ip",
            bank_name="Альфа ИП",
            online_text="Нет",
            base_payout=Decimal("10000.00"),
            lead_payout=Decimal("5000.00"),
            lead_payout_paid_separately=True,
            active=True,
            display_order=10,
            source_row=2,
        )
    ]


@pytest.mark.parametrize(
    ("column", "value"),
    [(3, "не число"), (6, "может быть"), (7, "включено"), (8, "1.5")],
)
def test_invalid_bank_rate_rows_are_rejected(column: int, value: str) -> None:
    row = ["code", "Банк", "Да", "1000", "200", "205", "Нет", "Да", "1"]
    row[column] = value
    with pytest.raises(ValueError):
        parse_bank_rate_rows([list(parse_bank_rate_rows.__globals__["EXPECTED_HEADERS"]), row])


def test_formula_errors_in_rate_columns_are_rejected_without_replacing_snapshot() -> None:
    row = ["code", "Банк", "Да", "#REF!", "200", "205", "Нет", "Да", "1"]

    with pytest.raises(ValueError, match="ошибка формулы"):
        parse_bank_rate_rows([list(parse_bank_rate_rows.__globals__["EXPECTED_HEADERS"]), row])


def test_unrounded_lead_payout_and_condition_errors_are_ignored() -> None:
    row = ["code", "Банк", "Да", "1000", "200", "#REF!", "Нет", "Да", "1", "#REF!"]

    parsed = parse_bank_rate_rows([list(parse_bank_rate_rows.__globals__["EXPECTED_HEADERS"]), row])

    assert parsed[0].offer_code == "code"


@pytest.mark.parametrize("duplicate_column", [0, 1])
def test_duplicate_bank_codes_and_names_are_rejected(duplicate_column: int) -> None:
    first = ["code-a", "Банк А", "Да", "1000", "200", "205", "Нет", "Да", "1"]
    second = ["code-b", "Банк Б", "Нет", "900", "100", "110", "Нет", "Да", "2"]
    second[duplicate_column] = first[duplicate_column]

    with pytest.raises(ValueError, match="дважды"):
        parse_bank_rate_rows(
            [list(parse_bank_rate_rows.__globals__["EXPECTED_HEADERS"]), first, second]
        )


def test_team_profit_subtracts_partner_and_lead_rewards() -> None:
    assert WorkflowService._team_profit(
        income=Decimal("4610"),
        partner_reward=Decimal("922"),
        lead_reward=Decimal("1705.70"),
        lead_reward_paid_separately=False,
    ) == Decimal("1982.30")


def test_team_profit_does_not_subtract_external_lead_bonus() -> None:
    assert WorkflowService._team_profit(
        income=Decimal("10000"),
        partner_reward=Decimal("2000"),
        lead_reward=Decimal("5000"),
        lead_reward_paid_separately=True,
    ) == Decimal("8000.00")


def test_negative_team_profit_is_rejected() -> None:
    with pytest.raises(DomainError, match="отрицательную"):
        WorkflowService._team_profit(
            income=Decimal("1000"),
            partner_reward=Decimal("700"),
            lead_reward=Decimal("500"),
            lead_reward_paid_separately=False,
        )


@pytest.mark.asyncio
async def test_manager_cannot_change_bank_financial_fields() -> None:
    service = object.__new__(WorkflowService)
    with pytest.raises(DomainError, match="финансовые"):
        await service.update_lead_bank(
            actor_role=UserRole.MANAGER,
            actor_user_id=uuid4(),
            lead_bank_id=uuid4(),
            income_estimate=Decimal("1000"),
        )


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
        row = [*self.values[row_number - 1], *("" for _ in range(10))][:10]
        if range_name.startswith("A"):
            row[:5] = values[0]
        elif range_name.startswith("G"):
            row[6:9] = values[0]
        elif range_name.startswith("H"):
            row[7] = values[0][0]
        else:
            raise AssertionError(f"Неожиданный диапазон: {range_name}")
        self.values[row_number - 1] = row


def gateway_with(values: list[list[str]]) -> BankRatesGateway:
    gateway = object.__new__(BankRatesGateway)
    gateway.worksheet = FakeWorksheet(values)
    return gateway


def test_bank_rate_gateway_updates_existing_sheet_row() -> None:
    values = [
        list(parse_bank_rate_rows.__globals__["EXPECTED_HEADERS"]),
        ["old-code", "Старое имя", "Нет", "1000", "200", "205", "Нет", "Да", "1", "Условие"],
    ]
    gateway = gateway_with(values)
    changed = BankRateRow(
        offer_code="new-code",
        bank_name="Новое имя",
        online_text="Да",
        base_payout=Decimal("2500"),
        lead_payout=Decimal("500"),
        lead_payout_paid_separately=False,
        active=True,
        display_order=3,
        source_row=2,
    )

    rows = gateway.upsert(changed, original_offer_code="old-code")

    assert rows == [
        BankRateRow(
            offer_code="new-code",
            bank_name="Новое имя",
            online_text="Да",
            base_payout=Decimal("2500.00"),
            lead_payout=Decimal("500.00"),
            lead_payout_paid_separately=False,
            active=True,
            display_order=3,
            source_row=2,
        )
    ]
    assert values[1][0] == "new-code"
    assert values[1][5] == "205"
    assert values[1][9] == "Условие"
    assert gateway.worksheet.updated_ranges == ["A2:E2", "G2:I2"]


def test_bank_rate_gateway_appends_without_writing_formula_column() -> None:
    values = [
        list(parse_bank_rate_rows.__globals__["EXPECTED_HEADERS"]),
        ["old-code", "Старый банк", "Нет", "1000", "200", "205", "Нет", "Да", "1", ""],
    ]
    created = BankRateRow(
        offer_code="new-code",
        bank_name="Новый банк",
        online_text="Нет",
        base_payout=Decimal("3000"),
        lead_payout=Decimal("700"),
        lead_payout_paid_separately=False,
        active=True,
        display_order=2,
        source_row=0,
    )

    rows = gateway_with(values).upsert(created)

    assert rows[-1].offer_code == "new-code"
    assert values[2] == [
        "new-code",
        "Новый банк",
        "Нет",
        "3000",
        "700",
        "",
        "Нет",
        "Да",
        "2",
        "",
    ]


def test_bank_rate_gateway_rolls_back_appended_bank() -> None:
    values = [list(parse_bank_rate_rows.__globals__["EXPECTED_HEADERS"])]
    gateway = gateway_with(values)
    created = BankRateRow(
        offer_code="new-code",
        bank_name="Новый банк",
        online_text="Нет",
        base_payout=Decimal("3000"),
        lead_payout=Decimal("700"),
        lead_payout_paid_separately=False,
        active=True,
        display_order=2,
        source_row=0,
    )
    write = gateway.plan_upsert(created)

    gateway.apply(write)
    rows = gateway.rollback(write)

    assert rows == []
    assert [values[1][index] for index in (0, 1, 2, 3, 4, 6, 7, 8)] == [""] * 8


def test_bank_rate_gateway_deactivates_without_removing_row() -> None:
    values = [
        list(parse_bank_rate_rows.__globals__["EXPECTED_HEADERS"]),
        ["bank", "Банк", "Нет", "1000", "200", "205", "Нет", "Да", "1", "Условие"],
    ]
    rows = gateway_with(values).set_active("bank", False)

    assert rows[0].active is False
    assert values[1][7] == "Нет"
