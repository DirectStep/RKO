from decimal import Decimal

from app.domain.operations import DomainError

PARTNER_PERCENT = Decimal("20.00")


def partner_reward(income: Decimal | None, lead_reward: Decimal | None) -> Decimal | None:
    if income is None:
        return None
    net = income - (lead_reward or Decimal("0"))
    if net < 0:
        raise DomainError("Выплата лиду не может превышать общую ставку банка")
    return (net * PARTNER_PERCENT / Decimal("100")).quantize(Decimal("0.01"))
