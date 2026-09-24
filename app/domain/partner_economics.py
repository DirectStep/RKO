from decimal import Decimal


def partner_reward(
    income: Decimal | None,
    lead_reward: Decimal | None,
    percent: Decimal,
) -> Decimal | None:
    if income is None:
        return None
    if lead_reward is None:
        return None
    net = max(income - lead_reward, Decimal("0"))
    return (net * percent / Decimal("100")).quantize(Decimal("0.01"))
