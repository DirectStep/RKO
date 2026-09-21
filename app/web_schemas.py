from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.enums import (
    BankInternalStatus,
    DuplicateResolution,
    PaymentStatus,
    UserRole,
)


class StaffCreate(BaseModel):
    telegram_username: str
    role: UserRole = UserRole.MANAGER


class PartnerAccessUpdate(BaseModel):
    telegram_id: str
    telegram_username: str | None = None


class PartnerUpdate(BaseModel):
    commission_percent: Decimal | None = Field(default=None, ge=0, le=100)
    telegram_username: str | None = None
    assigned_admin_id: UUID | None = None
    update_assigned_admin: bool = False


class PartnerCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    commission_percent: Decimal = Field(ge=0, le=100)
    telegram_username: str | None = None


class ChannelCreate(BaseModel):
    name: str
    partner_id: UUID | None = None


class LeadUpdate(BaseModel):
    manager_id: UUID | None = None
    update_manager: bool = False
    internal_comment: str | None = None
    update_comment: bool = False


class LeadSourceUpdate(BaseModel):
    partner_id: UUID
    channel_id: UUID


class DuplicateReviewResolve(BaseModel):
    resolution: DuplicateResolution


class BankCreate(BaseModel):
    offer_code: str = Field(min_length=2, max_length=64)
    name: str
    online_text: str = Field(default="Нет", max_length=120)
    base_payout: Decimal = Field(ge=0)
    lead_payout: Decimal = Field(ge=0)
    lead_payout_paid_separately: bool = False
    active: bool = True
    display_order: int = Field(default=0, ge=0, le=10_000)


class BankUpdate(BankCreate):
    pass


class LeadBankCreate(BaseModel):
    bank_ids: list[UUID] = Field(min_length=1)


class LeadBankSelection(BaseModel):
    bank_ids: list[UUID] = Field(min_length=1)


class LeadBankUpdate(BaseModel):
    status: BankInternalStatus | None = None
    close_reason: str | None = None
    income_estimate: Decimal | None = None
    income_fact: Decimal | None = None


class LeadRewardPaymentConfirm(BaseModel):
    amount: Decimal = Field(ge=0)


class PaymentConfirm(BaseModel):
    payment_period: str | None = None
    registry_number: str | None = None


class PaymentStatusUpdate(BaseModel):
    status: PaymentStatus
    paid_at: date | None = None
    internal_comment: str | None = None
    registry_number: str | None = None
