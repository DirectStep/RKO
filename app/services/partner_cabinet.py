from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TypedDict
from uuid import UUID

from sqlalchemy import and_, or_, select

from app.database import Database
from app.domain.enums import (
    AssignmentStatus,
    BankExternalStatus,
    BankInternalStatus,
    LeadExternalStatus,
    LeadWorkflowStage,
    PaymentStatus,
)
from app.domain.statuses import bank_display_status
from app.models import (
    Bank,
    BankActivationCondition,
    BankRate,
    Channel,
    Lead,
    LeadBank,
    Partner,
    Payment,
    User,
)
from app.services.application_progress import NO_PAYOUT_STATUSES, application_progress
from app.services.bank_conditions import normalize_bank_name

ACTIVE_APPLICATION_STATUSES = {"banks_selected", "opening_accounts", "activating_accounts"}
class PartnerBankData(TypedDict):
    id: str
    bank: str
    status: str
    display_status: str
    reward_estimate: str
    reward_fact: str
    lead_reward_estimate: str
    payment_status: str
    paid_at: str | None
    online_text: str
    online_available: bool
    online_help: str
    action_text: str


class PartnerLeadData(TypedDict):
    id: str
    short_id: str
    name: str
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
    application_status: str
    bank_progress: dict[str, object]


class PartnerMetrics(TypedDict):
    total: int
    new: int
    active: int
    completed: int
    cancelled: int
    opened_banks: int
    planned_banks: int
    estimated_payout: str
    last_payout: str
    paid: str


class PartnerCabinetData(TypedDict):
    metrics: PartnerMetrics
    leads: list[PartnerLeadData]
    commission_percent: str


@dataclass
class _LeadAccumulator:
    lead: PartnerLeadData
    bank_counts: defaultdict[str, int] = field(default_factory=lambda: defaultdict(int))
    reward_estimate: Decimal = Decimal("0")
    reward_fact: Decimal = Decimal("0")
    progress_banks: list[LeadBank] = field(default_factory=list)
    not_eligible: bool = False


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
    lead_status: str | None = None,
    payment_status: PaymentStatus | None = None,
    search: str = "",
) -> PartnerCabinetData:
    async with database.session() as session:
        partner = await session.get(Partner, partner_id)
        rows = list(
            await session.execute(
                select(Lead, Channel, LeadBank, Bank, Payment)
                .join(Channel, Channel.id == Lead.channel_id)
                .outerjoin(
                    LeadBank,
                    and_(
                        LeadBank.lead_id == Lead.id,
                        or_(
                            LeadBank.selected_by_lead.is_(True),
                            LeadBank.internal_status == BankInternalStatus.NOT_OPENED,
                        ),
                    ),
                )
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
        rates = list(await session.scalars(select(BankRate)))
        conditions = list(await session.scalars(select(BankActivationCondition)))
    rates_by_bank = {rate.bank_id: rate for rate in rates}
    conditions_by_name = {condition.normalized_bank_name: condition for condition in conditions}

    grouped: dict[UUID, _LeadAccumulator] = {}
    normalized_search = search.strip().lower()
    for lead, channel, lead_bank, bank, payment in rows:
        if not _in_period(lead.application_at, date_from, date_to):
            continue
        if channel_id is not None and channel.id != channel_id:
            continue
        searchable = f"{lead.short_id} {lead.display_name}".lower()
        if normalized_search and normalized_search not in searchable:
            continue
        item = grouped.setdefault(
            lead.id,
            _LeadAccumulator(
                not_eligible=lead.workflow_stage is LeadWorkflowStage.NOT_ELIGIBLE,
                lead={
                    "id": str(lead.id),
                    "short_id": lead.short_id,
                    "name": lead.display_name,
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
                    "application_status": "questionnaire_completed",
                    "bank_progress": {},
                }
            ),
        )
        if lead_bank is None or bank is None:
            continue
        if lead_bank.selected_by_lead is True:
            item.progress_banks.append(lead_bank)
        effective_payment_status = payment.status if payment else PaymentStatus.NOT_CALCULATED
        if payment_status is not None and effective_payment_status is not payment_status:
            continue
        estimate = _money(lead_bank.partner_reward_estimate)
        lead_estimate = _money(lead_bank.lead_reward_estimate)
        actual = _money(
            payment.partner_reward_fact
            if payment and payment.partner_reward_fact is not None
            else lead_bank.partner_reward_fact
        )
        projected = actual if lead_bank.partner_reward_fact is not None else estimate
        eligible = (
            lead_bank.selected_by_lead is True
            and lead_bank.internal_status not in NO_PAYOUT_STATUSES
        )
        settled = (
            effective_payment_status is PaymentStatus.PAID
            and (payment.partner_notification_sent_at is not None if payment else False)
        )
        pending = (
            projected if eligible and not settled
            else Decimal("0")
        )
        confirmed = (
            actual if eligible and settled
            else Decimal("0")
        )
        online_text = (
            rates_by_bank[bank.id].online_text if bank.id in rates_by_bank else "Уточняется"
        )
        online_available = online_text.strip().casefold().startswith("да")
        is_ozon = any(name in bank.name.casefold() for name in {"озон", "ozon"})
        online_help = ""
        if online_available:
            online_help = (
                "Можно оформить онлайн даже без электронной подписи"
                if is_ozon
                else "Можно открыть онлайн, если есть КЭП (электронная подпись). "
                "Оформить КЭП можно бесплатно в офисе Сбера или ВТБ после открытия счёта"
            )
        item.lead["banks"].append(
            {
                "id": str(lead_bank.id),
                "bank": bank.name,
                "status": lead_bank.external_status.value,
                "display_status": bank_display_status(
                    lead_bank.internal_status, lead_bank.lead_reward_paid_at is not None
                ),
                "reward_estimate": str(pending),
                "reward_fact": str(confirmed),
                "lead_reward_estimate": str(lead_estimate),
                "payment_status": effective_payment_status.value,
                "paid_at": payment.paid_at.isoformat() if payment and payment.paid_at else None,
                "online_text": online_text,
                "online_available": online_available,
                "online_help": online_help,
                "action_text": (
                    conditions_by_name[normalize_bank_name(bank.name)].action_text
                    if normalize_bank_name(bank.name) in conditions_by_name
                    else ""
                ),
            }
        )
        item.bank_counts[lead_bank.external_status.value] += 1
        item.reward_estimate += pending
        item.reward_fact += confirmed

    if payment_status is not None:
        grouped = {lead_id: item for lead_id, item in grouped.items() if item.lead["banks"]}

    leads: list[PartnerLeadData] = []
    for item in grouped.values():
        item.lead.update(application_progress(item.progress_banks, not_eligible=item.not_eligible))
        item.lead["bank_progress"]["expected_payout"] = str(item.reward_estimate)
        item.lead["bank_progress"]["confirmed_payout"] = str(item.reward_fact)
        item.lead["bank_counts"] = {
            status.value: item.bank_counts[status.value] for status in BankExternalStatus
        }
        item.lead["reward_estimate"] = str(item.reward_estimate)
        item.lead["reward_fact"] = str(item.reward_fact)
        leads.append(item.lead)
    if lead_status is not None:
        leads = [lead for lead in leads if lead["application_status"] == lead_status]

    opened_banks = 0
    planned_banks = 0
    paid = Decimal("0")
    paid_by_date: defaultdict[date, Decimal] = defaultdict(lambda: Decimal("0"))
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
            if status is PaymentStatus.PAID:
                paid += actual
                if bank["paid_at"]:
                    paid_by_date[date.fromisoformat(bank["paid_at"])] += actual
    last_payout = paid_by_date[max(paid_by_date)] if paid_by_date else Decimal("0")
    metrics: PartnerMetrics = {
        "total": len(leads),
        "new": sum(
            lead_item["application_status"] == "questionnaire_completed" for lead_item in leads
        ),
        "active": sum(
            lead_item["application_status"] in ACTIVE_APPLICATION_STATUSES
            for lead_item in leads
        ),
        "completed": sum(
            lead_item["application_status"] == "completed" for lead_item in leads
        ),
        "cancelled": sum(
            lead_item["status"] == LeadExternalStatus.CLOSED_WITHOUT_RESULT.value
            for lead_item in leads
        ),
        "opened_banks": opened_banks,
        "planned_banks": planned_banks,
        "estimated_payout": str(
            sum((Decimal(lead_item["reward_estimate"]) for lead_item in leads), Decimal("0"))
        ),
        "last_payout": str(last_payout),
        "paid": str(paid),
    }
    return {
        "metrics": metrics,
        "leads": leads,
        "commission_percent": (
            format(partner.commission_percent.normalize(), "f") if partner else ""
        ),
    }
