from decimal import Decimal


def partner_reward(
    income: Decimal | None,
    lead_reward: Decimal | None,
    percent: Decimal,
    *,
    lead_reward_paid_separately: bool = False,
) -> Decimal | None:
    if income is None:
        return None
    lead_cost = Decimal("0") if lead_reward_paid_separately else lead_reward
    if lead_cost is None:
        return None
    net = max(income - lead_cost, Decimal("0"))
    return (net * percent / Decimal("100")).quantize(Decimal("0.01"))
