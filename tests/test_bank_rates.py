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
            "Выплату лиду платит банк отдельно",
            "Активно",
            "Порядок",
            "Условие активации",
        ],
        [
            "alpha-ip",
            "Альфа ИП",
            "Нет",
            "10 000,00 ₽",
            "5 000",
            "Да",
            "Да",
            "10",
            "Совершить первую оплату",
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
            activation_condition="Совершить первую оплату",
            source_row=2,
        )
    ]


@pytest.mark.parametrize(
    ("column", "value"),
    [(3, "не число"), (5, "может быть"), (6, "включено"), (7, "1.5")],
)
def test_invalid_bank_rate_rows_are_rejected(column: int, value: str) -> None:
    row = ["code", "Банк", "Да", "1000", "200", "Нет", "Да", "1", "Условие"]
    row[column] = value
    with pytest.raises(ValueError):
        parse_bank_rate_rows([list(parse_bank_rate_rows.__globals__["EXPECTED_HEADERS"]), row])


def test_formula_errors_are_rejected_without_replacing_snapshot() -> None:
    row = ["code", "Банк", "Да", "1000", "200", "Нет", "Да", "1", "#REF!"]

    with pytest.raises(ValueError, match="ошибка формулы"):
        parse_bank_rate_rows([list(parse_bank_rate_rows.__globals__["EXPECTED_HEADERS"]), row])


@pytest.mark.parametrize("duplicate_column", [0, 1])
def test_duplicate_bank_codes_and_names_are_rejected(duplicate_column: int) -> None:
    first = ["code-a", "Банк А", "Да", "1000", "200", "Нет", "Да", "1", "Условие"]
    second = ["code-b", "Банк Б", "Нет", "900", "100", "Нет", "Да", "2", "Условие"]
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

    def get_all_values(self) -> list[list[str]]:
        return self.values

    def update(self, values: list[list[str]], range_name: str, *, raw: bool) -> None:
        assert raw is True
        start = range_name.split(":", maxsplit=1)[0]
        row_number = int("".join(character for character in start if character.isdigit()))
        while len(self.values) < row_number:
            self.values.append([])
        if range_name.startswith("G"):
            row = [*self.values[row_number - 1], *("" for _ in range(9))][:9]
            row[6] = values[0][0]
            self.values[row_number - 1] = row
        else:
            self.values[row_number - 1] = values[0]


def gateway_with(values: list[list[str]]) -> BankRatesGateway:
    gateway = object.__new__(BankRatesGateway)
    gateway.worksheet = FakeWorksheet(values)
    return gateway


def test_bank_rate_gateway_updates_existing_sheet_row() -> None:
    values = [
        list(parse_bank_rate_rows.__globals__["EXPECTED_HEADERS"]),
        ["old-code", "Старое имя", "Нет", "1000", "200", "Нет", "Да", "1", "Условие"],
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
        activation_condition="Новое условие",
        source_row=2,
    )

    rows = gateway.upsert(changed, original_offer_code="old-code")

    assert rows == [changed]
    assert values[1][0] == "new-code"
    assert values[1][8] == "Новое условие"


def test_bank_rate_gateway_deactivates_without_removing_row() -> None:
    values = [
        list(parse_bank_rate_rows.__globals__["EXPECTED_HEADERS"]),
        ["bank", "Банк", "Нет", "1000", "200", "Нет", "Да", "1", "Условие"],
    ]
    rows = gateway_with(values).set_active("bank", False)

    assert rows[0].active is False
    assert values[1][6] == "Нет"
