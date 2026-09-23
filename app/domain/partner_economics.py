from decimal import Decimal

PARTNER_PERCENT = Decimal("20.00")


def partner_reward(income: Decimal | None, lead_reward: Decimal | None) -> Decimal | None:
    if income is None:
        return None
    if lead_reward is None:
        return None
    net = max(income - lead_reward, Decimal("0"))
    return (net * PARTNER_PERCENT / Decimal("100")).quantize(Decimal("0.01"))
