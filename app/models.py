from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PostgreSQLUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.domain.enums import (
    AccessStatus,
    AssignmentStatus,
    BankExternalStatus,
    BankInternalStatus,
    LeadExternalStatus,
    LeadInternalStatus,
    PaymentStatus,
    UserRole,
)


def enum_column(enum_type: type[StrEnum], length: int = 32) -> Enum:
    return Enum(
        enum_type,
        native_enum=False,
        length=length,
        create_constraint=True,
        validate_strings=True,
        name=f"{enum_type.__name__.lower()}_values",
        values_callable=lambda values: [item.value for item in values],
    )


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    telegram_id: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    telegram_username: Mapped[str | None] = mapped_column(String(64))
    role: Mapped[UserRole] = mapped_column(
        enum_column(UserRole),
        nullable=False,
        default=UserRole.LEAD,
        server_default=UserRole.LEAD.value,
    )
    access_status: Mapped[AccessStatus] = mapped_column(
        enum_column(AccessStatus, 16),
        nullable=False,
        default=AccessStatus.ACTIVE,
        server_default=AccessStatus.ACTIVE.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Partner(Base):
    __tablename__ = "partners"
    __table_args__ = (
        CheckConstraint(
            "commission_percent >= 0 AND commission_percent <= 100",
            name="ck_partner_commission_percent",
        ),
    )
    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    partner_type: Mapped[str] = mapped_column(String(32), nullable=False, default="other")
    commission_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    telegram_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), unique=True
    )
    assigned_manager_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Channel(Base):
    __tablename__ = "channels"
    __table_args__ = (UniqueConstraint("id", "partner_id", name="uq_channel_partner"),)
    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    partner_id: Mapped[UUID] = mapped_column(ForeignKey("partners.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    channel_type: Mapped[str] = mapped_column(String(32), nullable=False, default="telegram")
    referral_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    referral_link: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Lead(Base):
    __tablename__ = "leads"
    __table_args__ = (
        ForeignKeyConstraint(
            ["proposed_channel_id", "proposed_partner_id"],
            ["channels.id", "channels.partner_id"],
            name="fk_lead_proposed_channel_partner",
        ),
        ForeignKeyConstraint(
            ["channel_id", "partner_id"],
            ["channels.id", "channels.partner_id"],
            name="fk_lead_channel_partner",
        ),
        CheckConstraint(
            "assignment_status != 'confirmed' OR "
            "(partner_id IS NOT NULL AND channel_id IS NOT NULL "
            "AND assignment_confirmed_at IS NOT NULL)",
            name="ck_lead_confirmed_assignment",
        ),
        CheckConstraint(
            "assignment_status != 'direct' OR (partner_id IS NULL AND channel_id IS NULL)",
            name="ck_lead_direct_without_source",
        ),
        CheckConstraint(
            "(proposed_partner_id IS NULL AND proposed_channel_id IS NULL) OR "
            "(proposed_partner_id IS NOT NULL AND proposed_channel_id IS NOT NULL)",
            name="ck_lead_proposed_source_pair",
        ),
        CheckConstraint(
            "assignment_confirmed_at IS NULL OR assignment_status = 'confirmed'",
            name="ck_lead_confirmation_date_status",
        ),
    )
    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    module_code: Mapped[str] = mapped_column(String(16), default="rko", server_default="rko")
    short_id: Mapped[str] = mapped_column(String(24), nullable=False, unique=True)
    telegram_id: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    telegram_username: Mapped[str | None] = mapped_column(String(64))
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    consent_status: Mapped[bool] = mapped_column(Boolean, nullable=False)
    consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    first_referral_code: Mapped[str | None] = mapped_column(String(64))
    proposed_partner_id: Mapped[UUID | None] = mapped_column(ForeignKey("partners.id"))
    proposed_channel_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))
    partner_id: Mapped[UUID | None] = mapped_column(ForeignKey("partners.id"))
    channel_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))
    assignment_status: Mapped[AssignmentStatus] = mapped_column(
        enum_column(AssignmentStatus), default=AssignmentStatus.UNRESOLVED, nullable=False
    )
    assignment_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    manager_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    internal_status: Mapped[LeadInternalStatus] = mapped_column(
        enum_column(LeadInternalStatus), default=LeadInternalStatus.NEW, nullable=False
    )
    external_status: Mapped[LeadExternalStatus] = mapped_column(
        enum_column(LeadExternalStatus), default=LeadExternalStatus.NEW, nullable=False
    )
    payment_status: Mapped[PaymentStatus] = mapped_column(
        enum_column(PaymentStatus), default=PaymentStatus.NOT_CALCULATED, nullable=False
    )
    internal_comment: Mapped[str | None] = mapped_column(Text)
    questionnaire_answers: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    first_click_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    application_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class LeadDraft(Base):
    __tablename__ = "lead_drafts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["proposed_channel_id", "proposed_partner_id"],
            ["channels.id", "channels.partner_id"],
            name="fk_draft_channel_partner",
        ),
        CheckConstraint(
            "(proposed_partner_id IS NULL AND proposed_channel_id IS NULL) OR "
            "(proposed_partner_id IS NOT NULL AND proposed_channel_id IS NOT NULL)",
            name="ck_draft_proposed_source_pair",
        ),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    telegram_id: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    referral_code: Mapped[str | None] = mapped_column(String(64))
    proposed_partner_id: Mapped[UUID | None] = mapped_column(ForeignKey("partners.id"))
    proposed_channel_id: Mapped[UUID | None] = mapped_column(PostgreSQLUUID(as_uuid=True))
    first_click_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DuplicateLeadReview(Base):
    __tablename__ = "duplicate_lead_reviews"

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    telegram_id: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    telegram_username: Mapped[str | None] = mapped_column(String(64))
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    referral_code: Mapped[str | None] = mapped_column(String(64))
    questionnaire_answers: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False)
    consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    first_click_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    review_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Bank(Base):
    __tablename__ = "banks"
    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    display_order: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )


class LeadBank(Base):
    __tablename__ = "lead_banks"
    __table_args__ = (
        UniqueConstraint("lead_id", "bank_id", name="uq_lead_bank"),
        CheckConstraint(
            "partner_percent_snapshot IS NULL OR "
            "(partner_percent_snapshot >= 0 AND partner_percent_snapshot <= 100)",
            name="ck_lead_bank_partner_percent",
        ),
        CheckConstraint(
            "(bank_income_estimate IS NULL OR bank_income_estimate >= 0) AND "
            "(bank_income_fact IS NULL OR bank_income_fact >= 0) AND "
            "(partner_reward_estimate IS NULL OR partner_reward_estimate >= 0) AND "
            "(partner_reward_fact IS NULL OR partner_reward_fact >= 0)",
            name="ck_lead_bank_nonnegative_money",
        ),
    )
    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    lead_id: Mapped[UUID] = mapped_column(ForeignKey("leads.id"), nullable=False)
    bank_id: Mapped[UUID] = mapped_column(ForeignKey("banks.id"), nullable=False)
    internal_status: Mapped[BankInternalStatus] = mapped_column(
        enum_column(BankInternalStatus), default=BankInternalStatus.PLANNED, nullable=False
    )
    external_status: Mapped[BankExternalStatus] = mapped_column(
        enum_column(BankExternalStatus), default=BankExternalStatus.PLANNED, nullable=False
    )
    planned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    preparation_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    application_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revision_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_without_open_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    close_reason: Mapped[str | None] = mapped_column(Text)
    bank_income_estimate: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    bank_income_fact: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    partner_percent_snapshot: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    partner_reward_estimate: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    partner_reward_fact: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint(
            "partner_reward_fact IS NULL OR partner_reward_fact >= 0",
            name="ck_payment_nonnegative_reward",
        ),
        CheckConstraint(
            "status NOT IN ('confirmed', 'in_registry', 'paid') OR "
            "(partner_reward_fact IS NOT NULL AND confirmed_at IS NOT NULL "
            "AND confirmed_by_user_id IS NOT NULL)",
            name="ck_payment_confirmation_fields",
        ),
        CheckConstraint("status != 'paid' OR paid_at IS NOT NULL", name="ck_payment_paid_date"),
        CheckConstraint(
            "status != 'cancelled' OR "
            "(internal_comment IS NOT NULL AND length(trim(internal_comment)) > 0)",
            name="ck_payment_cancel_comment",
        ),
    )
    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    lead_bank_id: Mapped[UUID] = mapped_column(
        ForeignKey("lead_banks.id"), nullable=False, unique=True
    )
    status: Mapped[PaymentStatus] = mapped_column(
        enum_column(PaymentStatus), default=PaymentStatus.NOT_CALCULATED, nullable=False
    )
    partner_reward_fact: Mapped[Decimal | None] = mapped_column(Numeric(14, 2))
    payment_period: Mapped[str | None] = mapped_column(String(20))
    expected_payment_at: Mapped[date | None] = mapped_column(Date)
    registry_number: Mapped[str | None] = mapped_column(String(80))
    paid_at: Mapped[date | None] = mapped_column(Date)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    confirmed_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    internal_comment: Mapped[str | None] = mapped_column(Text)
