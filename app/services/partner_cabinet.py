from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TypedDict
from uuid import UUID

from sqlalchemy import select

from app.database import Database
from app.domain.enums import AssignmentStatus, BankExternalStatus, LeadExternalStatus, PaymentStatus
from app.models import Bank, Channel, Lead, LeadBank, Partner, Payment, User

ACTIVE_LEAD_STATUSES = {
    LeadExternalStatus.NEW,
    LeadExternalStatus.IN_PROGRESS,
    LeadExternalStatus.OPENING_ACCOUNTS,
    LeadExternalStatus.PARTIALLY_COMPLETED,
    LeadExternalStatus.PAUSED,
}
CONFIRMED_PAYMENT_STATUSES = {
    PaymentStatus.CONFIRMED,
    PaymentStatus.IN_REGISTRY,
    PaymentStatus.PAID,
}


class PartnerBankData(TypedDict):
    id: str
    bank: str
    status: str
    reward_estimate: str
    reward_fact: str
    payment_status: str
    paid_at: str | None


class PartnerLeadData(TypedDict):
    id: str
    short_id: str
    name: str
    username: str
    date: str
    updated: str
    channel_id: str
    channel: str
    status: str
    payment_status: str
    is_repeat: bool
    banks: list[PartnerBankData]
    bank_counts: dict[str, int]
    reward_estimate: str
    reward_fact: str


class PartnerMetrics(TypedDict):
    total: int
    accepted: int
    active: int
    completed: int
    closed: int
    opened_banks: int
    planned_banks: int
    estimated_payout: str
    confirmed_payout: str
    paid: str


class PartnerCabinetData(TypedDict):
    metrics: PartnerMetrics
    leads: list[PartnerLeadData]


@dataclass
class _LeadAccumulator:
    lead: PartnerLeadData
    bank_counts: defaultdict[str, int] = field(default_factory=lambda: defaultdict(int))
    reward_estimate: Decimal = Decimal("0")
    reward_fact: Decimal = Decimal("0")


def _money(value: Decimal | None) -> Decimal:
    return value or Decimal("0")


def _in_period(moment: datetime, date_from: date | None, date_to: date | None) -> bool:
    local_date = moment.astimezone(UTC).date()
    return (date_from is None or local_date >= date_from) and (
        date_to is None or local_date <= date_to
    )


async def partner_contact(database: Database, partner_id: UUID) -> dict[str, str]:
    async with database.session() as session:
        row = (
            await session.execute(
                select(Partner, User)
                .outerjoin(User, User.id == Partner.assigned_manager_id)
                .where(Partner.id == partner_id)
            )
        ).one_or_none()
    if row is None or row[1] is None:
        return {"name": "Не назначен", "username": "", "url": ""}
    user = row[1]
    username = user.telegram_username or ""
    return {
        "name": f"@{username}" if username else (user.telegram_id or "Не назначен"),
        "username": username,
        "url": f"https://t.me/{username}" if username else "",
    }


async def partner_cabinet_data(
    database: Database,
    partner_id: UUID,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    channel_id: UUID | None = None,
    lead_status: LeadExternalStatus | None = None,
    payment_status: PaymentStatus | None = None,
    search: str = "",
) -> PartnerCabinetData:
    async with database.session() as session:
        rows = list(
            await session.execute(
                select(Lead, Channel, LeadBank, Bank, Payment)
                .join(Channel, Channel.id == Lead.channel_id)
                .outerjoin(LeadBank, LeadBank.lead_id == Lead.id)
                .outerjoin(Bank, Bank.id == LeadBank.bank_id)
                .outerjoin(Payment, Payment.lead_bank_id == LeadBank.id)
                .where(
                    Lead.partner_id == partner_id,
                    Lead.assignment_status == AssignmentStatus.CONFIRMED,
                    Lead.archived_at.is_(None),
                )
                .order_by(Lead.application_at.desc(), Bank.name)
            )
        )

    grouped: dict[UUID, _LeadAccumulator] = {}
    normalized_search = search.strip().lower()
    for lead, channel, lead_bank, bank, payment in rows:
        if not _in_period(lead.application_at, date_from, date_to):
            continue
        if channel_id is not None and channel.id != channel_id:
            continue
        if lead_status is not None and lead.external_status is not lead_status:
            continue
        searchable = f"{lead.short_id} {lead.display_name} {lead.telegram_username or ''}".lower()
        if normalized_search and normalized_search not in searchable:
            continue
        item = grouped.setdefault(
            lead.id,
            _LeadAccumulator(
                lead={
                    "id": str(lead.id),
                    "short_id": lead.short_id,
                    "name": lead.display_name,
                    "username": f"@{lead.telegram_username}" if lead.telegram_username else "",
                    "date": lead.application_at.isoformat(),
                    "updated": lead.last_updated_at.isoformat(),
                    "channel_id": str(channel.id),
                    "channel": channel.name,
                    "status": lead.external_status.value,
                    "payment_status": lead.payment_status.value,
                    "is_repeat": lead.is_repeat,
                    "banks": [],
                    "bank_counts": {},
                    "reward_estimate": "0",
                    "reward_fact": "0",
                }
            ),
        )
        if lead_bank is None or bank is None:
            continue
        effective_payment_status = payment.status if payment else PaymentStatus.NOT_CALCULATED
        if payment_status is not None and effective_payment_status is not payment_status:
            continue
        estimate = _money(lead_bank.partner_reward_estimate)
        actual = _money(
            payment.partner_reward_fact
            if payment and payment.partner_reward_fact is not None
            else lead_bank.partner_reward_fact
        )
        item.lead["banks"].append(
            {
                "id": str(lead_bank.id),
                "bank": bank.name,
                "status": lead_bank.external_status.value,
                "reward_estimate": str(estimate),
                "reward_fact": str(actual),
                "payment_status": effective_payment_status.value,
                "paid_at": payment.paid_at.isoformat() if payment and payment.paid_at else None,
            }
        )
        item.bank_counts[lead_bank.external_status.value] += 1
        item.reward_estimate += estimate
        if effective_payment_status in CONFIRMED_PAYMENT_STATUSES:
            item.reward_fact += actual

    if payment_status is not None:
        grouped = {lead_id: item for lead_id, item in grouped.items() if item.lead["banks"]}

    leads: list[PartnerLeadData] = []
    for item in grouped.values():
        item.lead["bank_counts"] = {
            status.value: item.bank_counts[status.value] for status in BankExternalStatus
        }
        item.lead["reward_estimate"] = str(item.reward_estimate)
        item.lead["reward_fact"] = str(item.reward_fact)
        leads.append(item.lead)

    opened_banks = 0
    planned_banks = 0
    estimated_payout = Decimal("0")
    confirmed_payout = Decimal("0")
    paid = Decimal("0")
    for lead_item in leads:
        for bank in lead_item["banks"]:
            if bank["status"] == BankExternalStatus.OPENED.value:
                opened_banks += 1
            if bank["status"] in {
                BankExternalStatus.PLANNED.value,
                BankExternalStatus.IN_PROGRESS.value,
            }:
                planned_banks += 1
            status = PaymentStatus(bank["payment_status"])
            estimate = Decimal(bank["reward_estimate"])
            actual = Decimal(bank["reward_fact"])
            if status not in CONFIRMED_PAYMENT_STATUSES and status is not PaymentStatus.CANCELLED:
                estimated_payout += estimate
            if status in CONFIRMED_PAYMENT_STATUSES:
                confirmed_payout += actual
            if status is PaymentStatus.PAID:
                paid += actual
    metrics: PartnerMetrics = {
        "total": len(leads),
        "accepted": sum(lead_item["status"] != LeadExternalStatus.NEW.value for lead_item in leads),
        "active": sum(
            lead_item["status"] in {status.value for status in ACTIVE_LEAD_STATUSES}
            for lead_item in leads
        ),
        "completed": sum(
            lead_item["status"] == LeadExternalStatus.COMPLETED.value for lead_item in leads
        ),
        "closed": sum(
            lead_item["status"] == LeadExternalStatus.CLOSED_WITHOUT_RESULT.value
            for lead_item in leads
        ),
        "opened_banks": opened_banks,
        "planned_banks": planned_banks,
        "estimated_payout": str(estimated_payout),
        "confirmed_payout": str(confirmed_payout),
        "paid": str(paid),
    }
    return {"metrics": metrics, "leads": leads}
