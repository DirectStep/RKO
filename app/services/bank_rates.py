from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select

from app.database import Database
from app.domain.partner_economics import PARTNER_PERCENT
from app.domain.partner_economics import partner_reward as calculate_partner_reward
from app.integrations.bank_rates import BankRateRow
from app.models import Bank, BankRate, Lead, LeadBank
from app.services.bank_conditions import normalize_bank_name


class BankRatesService:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def replace_all(self, rows: list[BankRateRow]) -> int:
        by_code: dict[str, BankRateRow] = {}
        by_name: dict[str, BankRateRow] = {}
        for row in rows:
            code = row.offer_code.casefold()
            name = normalize_bank_name(row.bank_name)
            if code in by_code:
                raise ValueError(
                    f"Строки {by_code[code].source_row} и {row.source_row}: код указан дважды"
                )
            if name in by_name:
                raise ValueError(
                    f"Строки {by_name[name].source_row} и {row.source_row}: название указано дважды"
                )
            by_code[code] = row
            by_name[name] = row

        synced_at = datetime.now(UTC)
        async with self.database.session() as session, session.begin():
            rates = list(await session.scalars(select(BankRate)))
            rates_by_code = {rate.offer_code.casefold(): rate for rate in rates}
            banks = list(await session.scalars(select(Bank)))
            banks_by_name = {normalize_bank_name(bank.name): bank for bank in banks}
            seen_rate_ids = set()
            current_rates_by_bank: dict[object, BankRate] = {}
            for row in rows:
                normalized_name = normalize_bank_name(row.bank_name)
                rate = rates_by_code.get(row.offer_code.casefold())
                bank = await session.get(Bank, rate.bank_id) if rate is not None else None
                if bank is None:
                    bank = banks_by_name.get(normalized_name)
                if bank is None:
                    bank = Bank(
                        name=row.bank_name, active=row.active, display_order=row.display_order
                    )
                    session.add(bank)
                    await session.flush()
                else:
                    bank.name = row.bank_name
                    bank.active = row.active
                    bank.display_order = row.display_order
                banks_by_name[normalized_name] = bank

                if rate is None:
                    rate = BankRate(offer_code=row.offer_code, bank_id=bank.id)
                    session.add(rate)
                rate.offer_code = row.offer_code
                rate.bank_id = bank.id
                rate.online_text = row.online_text
                rate.base_payout = row.base_payout
                rate.lead_payout = row.lead_payout
                rate.lead_payout_paid_separately = row.lead_payout_paid_separately
                rate.active = row.active
                rate.display_order = row.display_order
                rate.source_row = row.source_row
                rate.synced_at = synced_at
                await session.flush()
                seen_rate_ids.add(rate.id)
                current_rates_by_bank[bank.id] = rate

            for rate in rates:
                if rate.id not in seen_rate_ids:
                    rate.active = False
                    bank = await session.get(Bank, rate.bank_id)
                    if bank is not None:
                        bank.active = False

            unsnapshotted = list(
                await session.scalars(select(LeadBank).where(LeadBank.bank_rate_id.is_(None)))
            )
            for lead_bank in unsnapshotted:
                rate = current_rates_by_bank.get(lead_bank.bank_id)
                if rate is None:
                    continue
                lead = await session.get(Lead, lead_bank.lead_id)
                percent = (
                    PARTNER_PERCENT if lead is not None and lead.partner_id is not None else None
                )
                partner_reward = (
                    calculate_partner_reward(rate.base_payout, rate.lead_payout)
                    if percent is not None
                    else None
                )
                profit = rate.base_payout - (partner_reward or Decimal("0"))
                profit -= rate.lead_payout
                if profit < 0:
                    raise ValueError(f"{rate.offer_code}: ставки дают отрицательную прибыль")
                lead_bank.bank_rate_id = rate.id
                lead_bank.bank_income_estimate = rate.base_payout
                lead_bank.partner_percent_snapshot = percent
                lead_bank.partner_reward_estimate = partner_reward
                lead_bank.lead_reward_estimate = rate.lead_payout
                lead_bank.team_profit_estimate = profit.quantize(Decimal("0.01"))
                lead_bank.lead_reward_paid_separately = rate.lead_payout_paid_separately
        return len(rows)
