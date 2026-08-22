from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.domain.enums import (
    BankInternalStatus,
    DuplicateResolution,
    LeadInternalStatus,
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


class ChannelCreate(BaseModel):
    name: str
    partner_id: UUID | None = None


class LeadUpdate(BaseModel):
    internal_status: LeadInternalStatus | None = None
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
    name: str
    display_order: int = Field(default=0, ge=0, le=10_000)


class LeadBankCreate(BaseModel):
    bank_id: UUID


class LeadBankSelection(BaseModel):
    bank_ids: list[UUID] = Field(min_length=1)


class LeadBankUpdate(BaseModel):
    status: BankInternalStatus | None = None
    close_reason: str | None = None
    income_estimate: Decimal | None = None
    income_fact: Decimal | None = None


class PaymentConfirm(BaseModel):
    payment_period: str | None = None
    registry_number: str | None = None


class PaymentStatusUpdate(BaseModel):
    status: PaymentStatus
    paid_at: date | None = None
    internal_comment: str | None = None
    registry_number: str | None = None
