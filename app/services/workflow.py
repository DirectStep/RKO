import hashlib
import re
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Database
from app.domain.enums import (
    AccessStatus,
    BankInternalStatus,
    LeadInternalStatus,
    LeadWorkflowStage,
    PaymentStatus,
    UserRole,
)
from app.domain.operations import DomainError, confirm_payment, validate_payment_transition
from app.domain.statuses import external_bank_status, external_lead_status
from app.models import Bank, Lead, LeadBank, Partner, Payment, User


class WorkflowService:
    def __init__(self, database: Database) -> None:
        self.database = database

    async def list_staff(self) -> list[User]:
        async with self.database.session() as session:
            result = await session.scalars(
                select(User)
                .where(User.role.in_({UserRole.ADMIN, UserRole.MANAGER}))
                .order_by(User.role, User.telegram_username, User.telegram_id)
            )
            return list(result)

    async def create_staff(
        self,
        *,
        actor_role: UserRole,
        telegram_id: str | None = None,
        telegram_username: str | None,
        role: UserRole,
    ) -> User:
        self._require_admin(actor_role)
        if role not in {UserRole.MANAGER, UserRole.ADMIN}:
            raise DomainError("Можно создать только менеджера или администратора")
        username = self._clean_username(telegram_username)
        if username is None or not re.fullmatch(r"[A-Za-z0-9_]{5,32}", username):
            raise DomainError(
                "Username должен содержать 5–32 латинских символа, цифры или _"
            )
        if telegram_id is not None:
            self._validate_telegram_id(telegram_id)
        async with self.database.session() as session, session.begin():
            existing = await session.scalar(
                select(User).where(
                    (User.telegram_id == telegram_id)
                    if telegram_id is not None
                    else func.lower(User.telegram_username) == username.lower()
                )
            )
            if existing is not None:
                linked_partner = await session.scalar(
                    select(Partner.id).where(Partner.telegram_user_id == existing.id)
                )
                if linked_partner is not None:
                    raise DomainError("Этот пользователь уже привязан как партнёр")
                existing.telegram_username = username
                existing.role = role
                existing.access_status = AccessStatus.ACTIVE
                return existing
            partner_username = await session.scalar(
                select(Partner.id).where(
                    func.lower(Partner.telegram_username) == username.lower()
                )
            )
            if partner_username is not None:
                raise DomainError("Этот username уже указан у партнёра")
            user = User(
                telegram_id=telegram_id,
                telegram_username=username,
                role=role,
                access_status=AccessStatus.ACTIVE,
            )
            session.add(user)
            await session.flush()
            return user

    async def toggle_user(self, *, actor_role: UserRole, user_id: UUID) -> User:
        self._require_admin(actor_role)
        async with self.database.session() as session, session.begin():
            user = await session.scalar(select(User).where(User.id == user_id).with_for_update())
            if user is None:
                raise DomainError("Пользователь не найден")
            user.access_status = (
                AccessStatus.BLOCKED
                if user.access_status is AccessStatus.ACTIVE
                else AccessStatus.ACTIVE
            )
            return user

    async def bind_partner_access(
        self,
        *,
        actor_role: UserRole,
        partner_id: UUID,
        telegram_id: str,
        telegram_username: str | None,
    ) -> Partner:
        self._require_admin(actor_role)
        self._validate_telegram_id(telegram_id)
        async with self.database.session() as session, session.begin():
            partner = await session.scalar(
                select(Partner).where(Partner.id == partner_id).with_for_update()
            )
            if partner is None:
                raise DomainError("Партнёр не найден")
            user = await session.scalar(
                select(User).where(User.telegram_id == telegram_id).with_for_update()
            )
            if user is not None and user.role not in {UserRole.LEAD, UserRole.PARTNER}:
                raise DomainError("Этот Telegram ID уже используется сотрудником")
            if user is None:
                user = User(
                    telegram_id=telegram_id,
                    telegram_username=self._clean_username(telegram_username),
                    role=UserRole.PARTNER,
                    access_status=AccessStatus.ACTIVE,
                )
                session.add(user)
                await session.flush()
            else:
                linked = await session.scalar(
                    select(Partner).where(
                        Partner.telegram_user_id == user.id,
                        Partner.id != partner.id,
                    )
                )
                if linked is not None:
                    raise DomainError("Этот Telegram ID уже связан с другим партнёром")
                user.telegram_username = self._clean_username(telegram_username)
                user.role = UserRole.PARTNER
                user.access_status = AccessStatus.ACTIVE
            partner.telegram_user_id = user.id
            partner.telegram_username = user.telegram_username
            return partner

    async def activate_partner_with_token(
        self,
        *,
        telegram_id: str,
        telegram_username: str | None,
        token: str,
    ) -> Partner:
        self._validate_telegram_id(telegram_id)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        async with self.database.session() as session, session.begin():
            partner = await session.scalar(
                select(Partner)
                .where(
                    Partner.activation_token_hash == token_hash,
                    Partner.active.is_(True),
                )
                .with_for_update()
            )
            if partner is None:
                raise DomainError("Ссылка активации недействительна или уже использована")
            user = await session.scalar(
                select(User).where(User.telegram_id == telegram_id).with_for_update()
            )
            if partner.telegram_user_id is not None:
                linked_user = await session.get(User, partner.telegram_user_id)
                if linked_user is None or linked_user.telegram_id != telegram_id:
                    raise DomainError("Партнёрский кабинет уже активирован")
                partner.activation_token_hash = None
                partner.activation_created_at = None
                return partner
            if user is not None and user.role in {UserRole.ADMIN, UserRole.MANAGER}:
                raise DomainError("Сотрудника нельзя активировать как партнёра")
            if user is not None:
                other_partner = await session.scalar(
                    select(Partner.id).where(
                        Partner.telegram_user_id == user.id,
                        Partner.id != partner.id,
                    )
                )
                if other_partner is not None:
                    raise DomainError("Этот Telegram уже связан с другим партнёром")
            if user is None:
                user = User(
                    telegram_id=telegram_id,
                    telegram_username=self._clean_username(telegram_username),
                    role=UserRole.PARTNER,
                    access_status=AccessStatus.ACTIVE,
                )
                session.add(user)
                await session.flush()
            else:
                user.telegram_username = self._clean_username(telegram_username)
                user.role = UserRole.PARTNER
                user.access_status = AccessStatus.ACTIVE
            partner.telegram_user_id = user.id
            if user.telegram_username:
                partner.telegram_username = user.telegram_username
            partner.activation_token_hash = None
            partner.activation_created_at = None
            return partner

    async def update_lead(
        self,
        *,
        actor_role: UserRole,
        lead_id: UUID,
        internal_status: LeadInternalStatus | None = None,
        manager_id: UUID | None = None,
        update_manager: bool = False,
        internal_comment: str | None = None,
        update_comment: bool = False,
    ) -> Lead:
        if actor_role not in {UserRole.ADMIN, UserRole.MANAGER}:
            raise DomainError("Изменять заявку может только сотрудник")
        async with self.database.session() as session, session.begin():
            lead = await session.scalar(select(Lead).where(Lead.id == lead_id).with_for_update())
            if lead is None:
                raise DomainError("Заявка не найдена")
            if update_manager:
                self._require_admin(actor_role)
                if manager_id is not None:
                    manager = await session.get(User, manager_id)
                    if (
                        manager is None
                        or manager.role is not UserRole.MANAGER
                        or manager.access_status is not AccessStatus.ACTIVE
                    ):
                        raise DomainError("Активный менеджер не найден")
                lead.manager_id = manager_id
                if manager_id is not None and lead.internal_status is LeadInternalStatus.NEW:
                    lead.internal_status = LeadInternalStatus.MANAGER_ASSIGNED
                    lead.external_status = external_lead_status(lead.internal_status)
            if internal_status is not None:
                lead.internal_status = internal_status
                lead.external_status = external_lead_status(internal_status)
            if update_comment:
                lead.internal_comment = (internal_comment or "").strip() or None
            lead.last_updated_at = datetime.now(UTC)
            return lead

    async def list_banks(self, *, include_inactive: bool = True) -> list[Bank]:
        async with self.database.session() as session:
            query = select(Bank)
            if not include_inactive:
                query = query.where(Bank.active.is_(True))
            result = await session.scalars(query.order_by(Bank.display_order, Bank.name))
            return list(result)

    async def create_bank(self, *, actor_role: UserRole, name: str, display_order: int = 0) -> Bank:
        self._require_admin(actor_role)
        clean_name = name.strip()
        if len(clean_name) < 2 or len(clean_name) > 120:
            raise DomainError("Название банка должно быть от 2 до 120 символов")
        async with self.database.session() as session, session.begin():
            existing = await session.scalar(
                select(Bank).where(func.lower(Bank.name) == clean_name.lower())
            )
            if existing is not None:
                raise DomainError("Такой банк уже есть")
            bank = Bank(name=clean_name, display_order=display_order)
            session.add(bank)
            await session.flush()
            return bank

    async def toggle_bank(self, *, actor_role: UserRole, bank_id: UUID) -> Bank:
        self._require_admin(actor_role)
        async with self.database.session() as session, session.begin():
            bank = await session.scalar(select(Bank).where(Bank.id == bank_id).with_for_update())
            if bank is None:
                raise DomainError("Банк не найден")
            bank.active = not bank.active
            return bank

    async def add_bank_to_lead(
        self,
        *,
        actor_role: UserRole,
        lead_id: UUID,
        bank_id: UUID,
        actor_user_id: UUID | None = None,
    ) -> LeadBank:
        self._require_employee(actor_role)
        async with self.database.session() as session, session.begin():
            lead = await session.get(Lead, lead_id)
            bank = await session.get(Bank, bank_id)
            if lead is None:
                raise DomainError("Заявка не найдена")
            if bank is None or not bank.active:
                raise DomainError("Активный банк не найден")
            if actor_user_id is not None:
                if (
                    actor_role is UserRole.ADMIN
                    and lead.primary_admin_id != actor_user_id
                ):
                    raise DomainError("Сначала возьми заявку в работу")
                if actor_role is UserRole.MANAGER and (
                    lead.manager_id != actor_user_id
                    or lead.workflow_stage is not LeadWorkflowStage.MANAGER_PROCESSING
                ):
                    raise DomainError("Этот лид не находится у тебя в работе")
            existing = await session.scalar(
                select(LeadBank).where(LeadBank.lead_id == lead_id, LeadBank.bank_id == bank_id)
            )
            if existing is not None:
                raise DomainError("Этот банк уже добавлен к заявке")
            percent = None
            if lead.partner_id is not None:
                partner = await session.get(Partner, lead.partner_id)
                percent = partner.commission_percent if partner else None
            lead_bank = LeadBank(
                lead_id=lead_id,
                bank_id=bank_id,
                internal_status=BankInternalStatus.PLANNED,
                external_status=external_bank_status(BankInternalStatus.PLANNED),
                planned_at=datetime.now(UTC),
                offered_to_lead=actor_role is UserRole.MANAGER,
                selected_by_lead=True if actor_role is UserRole.MANAGER else None,
                partner_percent_snapshot=percent,
            )
            session.add(lead_bank)
            await session.flush()
            return lead_bank

    async def update_lead_bank(
        self,
        *,
        actor_role: UserRole,
        lead_bank_id: UUID,
        status: BankInternalStatus | None = None,
        close_reason: str | None = None,
        income_estimate: Decimal | None = None,
        income_fact: Decimal | None = None,
    ) -> LeadBank:
        self._require_employee(actor_role)
        self._validate_money(income_estimate)
        self._validate_money(income_fact)
        async with self.database.session() as session, session.begin():
            lead_bank = await session.scalar(
                select(LeadBank).where(LeadBank.id == lead_bank_id).with_for_update()
            )
            if lead_bank is None:
                raise DomainError("Банк заявки не найден")
            if status is not None:
                self._apply_bank_status(lead_bank, status, close_reason)
            if income_estimate is not None:
                lead_bank.bank_income_estimate = income_estimate
                lead_bank.partner_reward_estimate = self._reward(
                    income_estimate, lead_bank.partner_percent_snapshot
                )
            if income_fact is not None:
                lead_bank.bank_income_fact = income_fact
                lead_bank.partner_reward_fact = self._reward(
                    income_fact, lead_bank.partner_percent_snapshot
                )
                payment = await session.scalar(
                    select(Payment).where(Payment.lead_bank_id == lead_bank.id).with_for_update()
                )
                if payment is not None and payment.status in {
                    PaymentStatus.CONFIRMED,
                    PaymentStatus.IN_REGISTRY,
                    PaymentStatus.PAID,
                }:
                    raise DomainError("Подтверждённую сумму нельзя изменить")
                if payment is None:
                    payment = Payment(lead_bank_id=lead_bank.id)
                    session.add(payment)
                payment.partner_reward_fact = lead_bank.partner_reward_fact
                payment.status = PaymentStatus.AWAITING_CONFIRMATION
            lead_bank.last_updated_at = datetime.now(UTC)
            return lead_bank

    async def confirm_lead_bank_payment(
        self,
        *,
        actor_role: UserRole,
        actor_user_id: UUID,
        lead_bank_id: UUID,
        payment_period: str | None = None,
        registry_number: str | None = None,
    ) -> Payment:
        self._require_admin(actor_role)
        async with self.database.session() as session, session.begin():
            lead_bank = await session.get(LeadBank, lead_bank_id)
            payment = await session.scalar(
                select(Payment).where(Payment.lead_bank_id == lead_bank_id).with_for_update()
            )
            if lead_bank is None or payment is None or lead_bank.partner_reward_fact is None:
                raise DomainError("Сначала укажи фактический доход банка")
            confirmation = confirm_payment(
                actor_role=actor_role,
                current_status=payment.status,
                amount=lead_bank.partner_reward_fact,
                confirmed_at=datetime.now(UTC),
                confirmed_by_user_id=actor_user_id,
            )
            payment.partner_reward_fact = confirmation.amount
            payment.confirmed_at = confirmation.confirmed_at
            payment.confirmed_by_user_id = confirmation.confirmed_by_user_id
            payment.payment_period = (payment_period or "").strip() or None
            payment.registry_number = (registry_number or "").strip() or None
            payment.status = PaymentStatus.CONFIRMED
            await self._update_lead_payment_status(session, lead_bank.lead_id, payment.status)
            return payment

    async def change_payment_status(
        self,
        *,
        actor_role: UserRole,
        payment_id: UUID,
        new_status: PaymentStatus,
        paid_at: date | None = None,
        internal_comment: str | None = None,
        registry_number: str | None = None,
    ) -> Payment:
        self._require_admin(actor_role)
        async with self.database.session() as session, session.begin():
            payment = await session.scalar(
                select(Payment).where(Payment.id == payment_id).with_for_update()
            )
            if payment is None:
                raise DomainError("Выплата не найдена")
            validate_payment_transition(
                actor_role=actor_role,
                current_status=payment.status,
                new_status=new_status,
                paid_at=paid_at,
                internal_comment=internal_comment,
            )
            payment.status = new_status
            if paid_at is not None:
                payment.paid_at = paid_at
            if internal_comment is not None:
                payment.internal_comment = internal_comment.strip() or None
            if registry_number is not None:
                payment.registry_number = registry_number.strip() or None
            lead_bank = await session.get(LeadBank, payment.lead_bank_id)
            if lead_bank is not None:
                await self._update_lead_payment_status(session, lead_bank.lead_id, new_status)
            return payment

    async def delete_lead(self, *, actor_role: UserRole, lead_id: UUID) -> None:
        self._require_employee(actor_role)
        async with self.database.session() as session, session.begin():
            lead = await session.scalar(select(Lead).where(Lead.id == lead_id).with_for_update())
            if lead is None:
                raise DomainError("Заявка не найдена")
            protected_payment = await session.scalar(
                select(Payment.id)
                .join(LeadBank, LeadBank.id == Payment.lead_bank_id)
                .where(
                    LeadBank.lead_id == lead_id,
                    Payment.status.in_(
                        {PaymentStatus.CONFIRMED, PaymentStatus.IN_REGISTRY, PaymentStatus.PAID}
                    ),
                )
                .limit(1)
            )
            if protected_payment is not None:
                raise DomainError("Лида с подтверждённой выплатой удалить нельзя")
            lead_bank_ids = select(LeadBank.id).where(LeadBank.lead_id == lead_id)
            await session.execute(delete(Payment).where(Payment.lead_bank_id.in_(lead_bank_ids)))
            await session.execute(delete(LeadBank).where(LeadBank.lead_id == lead_id))
            await session.delete(lead)

    @staticmethod
    def _apply_bank_status(
        lead_bank: LeadBank, status: BankInternalStatus, close_reason: str | None
    ) -> None:
        closing = {
            BankInternalStatus.BANK_REJECTED,
            BankInternalStatus.CLIENT_REFUSED,
            BankInternalStatus.EXCLUDED,
        }
        if status in closing and not (close_reason or "").strip():
            raise DomainError("Для закрывающего статуса укажи причину")
        now = datetime.now(UTC)
        lead_bank.internal_status = status
        lead_bank.external_status = external_bank_status(status)
        lead_bank.close_reason = (close_reason or "").strip() or None
        date_fields = {
            BankInternalStatus.AWAITING_DATA: "data_requested_at",
            BankInternalStatus.PREPARING_APPLICATION: "preparation_started_at",
            BankInternalStatus.APPLICATION_SENT: "application_sent_at",
            BankInternalStatus.UNDER_REVIEW: "review_started_at",
            BankInternalStatus.REVISION_REQUIRED: "revision_requested_at",
            BankInternalStatus.ACCOUNT_OPENED: "opened_at",
        }
        if status in closing:
            lead_bank.closed_without_open_at = now
        elif status in date_fields:
            setattr(lead_bank, date_fields[status], now)

    @staticmethod
    async def _update_lead_payment_status(
        session: AsyncSession, lead_id: UUID, status: PaymentStatus
    ) -> None:
        lead = await session.get(Lead, lead_id)
        if lead is not None:
            lead.payment_status = status

    @staticmethod
    def _reward(income: Decimal, percent: Decimal | None) -> Decimal | None:
        if percent is None:
            return None
        return (income * percent / Decimal("100")).quantize(Decimal("0.01"))

    @staticmethod
    def _validate_money(value: Decimal | None) -> None:
        if value is not None and (not value.is_finite() or value < 0):
            raise DomainError("Сумма должна быть неотрицательным числом")

    @staticmethod
    def _validate_telegram_id(value: str) -> None:
        if not value.isdigit() or len(value) > 20:
            raise DomainError("Telegram ID должен состоять из цифр")

    @staticmethod
    def _clean_username(value: str | None) -> str | None:
        return (value or "").strip().lstrip("@") or None

    @staticmethod
    def _require_admin(role: UserRole) -> None:
        if role is not UserRole.ADMIN:
            raise DomainError("Действие доступно только администратору")

    @staticmethod
    def _require_employee(role: UserRole) -> None:
        if role not in {UserRole.ADMIN, UserRole.MANAGER}:
            raise DomainError("Действие доступно только сотруднику")
