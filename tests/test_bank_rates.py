from decimal import Decimal

import pytest

from app.domain.operations import DomainError
from app.integrations.bank_rates import BankRateRow, parse_bank_rate_rows
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
        ],
        ["alpha-ip", "Альфа ИП", "Нет", "10 000,00 ₽", "5 000", "Да", "Да", "10"],
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
    [(3, "не число"), (5, "может быть"), (6, "включено"), (7, "1.5")],
)
def test_invalid_bank_rate_rows_are_rejected(column: int, value: str) -> None:
    row = ["code", "Банк", "Да", "1000", "200", "Нет", "Да", "1"]
    row[column] = value
    with pytest.raises(ValueError):
        parse_bank_rate_rows([list(parse_bank_rate_rows.__globals__["EXPECTED_HEADERS"]), row])


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
