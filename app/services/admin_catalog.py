import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy import delete, func, or_, select

from app.database import Database
from app.domain.enums import AccessStatus, UserRole
from app.domain.operations import DomainError
from app.models import Channel, Lead, LeadDraft, Partner, User


@dataclass(frozen=True)
class ChannelSummary:
    channel: Channel
    partner_name: str


@dataclass(frozen=True)
class PartnerAccessSummary:
    partner: Partner
    telegram_id: str | None
    telegram_username: str | None


class AdminCatalogService:
    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def parse_commission(value: str) -> Decimal:
        try:
            commission = Decimal(value.strip().replace(",", "."))
        except InvalidOperation as error:
            raise DomainError("Напиши процент числом, например 15 или 12,5") from error
        if not commission.is_finite() or commission < 0 or commission > 100:
            raise DomainError("Процент должен быть от 0 до 100")
        return commission.quantize(Decimal("0.01"))

    @staticmethod
    def parse_telegram_username(value: str) -> str | None:
        username = value.strip().removeprefix("@").strip()
        if username.lower() in {"нет", "пропустить", "-"}:
            return None
        if not re.fullmatch(r"[A-Za-z0-9_]{5,32}", username):
            raise DomainError(
                "Username должен содержать 5–32 латинских символа, цифры или _. Например: gerasimov"
            )
        return username

    async def list_partners(self) -> list[Partner]:
        async with self.database.session() as session:
            result = await session.scalars(select(Partner).order_by(Partner.name))
            return list(result)

    async def get_partner(self, partner_id: UUID) -> Partner | None:
        async with self.database.session() as session:
            return await session.get(Partner, partner_id)

    async def get_partner_access(self, partner_id: UUID) -> PartnerAccessSummary | None:
        async with self.database.session() as session:
            row = (
                await session.execute(
                    select(Partner, User.telegram_id, User.telegram_username)
                    .outerjoin(User, User.id == Partner.telegram_user_id)
                    .where(Partner.id == partner_id)
                )
            ).one_or_none()
            if row is None:
                return None
            partner = row[0]
            return PartnerAccessSummary(
                partner,
                row[1],
                row[2] or partner.telegram_username,
            )

    async def create_partner(
        self,
        *,
        actor_role: UserRole,
        name: str,
        commission_percent: Decimal,
        telegram_username: str | None = None,
    ) -> Partner:
        self._require_admin(actor_role)
        clean_name = name.strip()
        if len(clean_name) < 2 or len(clean_name) > 160:
            raise DomainError("Название партнёра должно быть от 2 до 160 символов")
        if commission_percent < 0 or commission_percent > 100:
            raise DomainError("Процент должен быть от 0 до 100")
        async with self.database.session() as session, session.begin():
            existing = await session.scalar(select(Partner).where(Partner.name == clean_name))
            if existing is not None:
                raise DomainError("Партнёр с таким названием уже существует")
            if telegram_username is not None:
                username_owner = await session.scalar(
                    select(Partner).where(
                        func.lower(Partner.telegram_username) == telegram_username.lower()
                    )
                )
                if username_owner is not None:
                    raise DomainError("Этот Telegram username уже указан у другого партнёра")
            partner = Partner(
                name=clean_name,
                telegram_username=telegram_username,
                partner_type="other",
                commission_percent=commission_percent,
            )
            session.add(partner)
            await session.flush()
            return partner

    async def toggle_partner(self, *, actor_role: UserRole, partner_id: UUID) -> Partner:
        self._require_admin(actor_role)
        async with self.database.session() as session, session.begin():
            partner = await session.scalar(
                select(Partner).where(Partner.id == partner_id).with_for_update()
            )
            if partner is None:
                raise DomainError("Партнёр не найден")
            partner.active = not partner.active
            return partner

    async def update_partner_commission(
        self,
        *,
        actor_role: UserRole,
        partner_id: UUID,
        commission_percent: Decimal,
    ) -> Partner:
        self._require_admin(actor_role)
        commission = self.parse_commission(str(commission_percent))
        async with self.database.session() as session, session.begin():
            partner = await session.scalar(
                select(Partner).where(Partner.id == partner_id).with_for_update()
            )
            if partner is None:
                raise DomainError("Партнёр не найден")
            partner.commission_percent = commission
            return partner

    async def update_partner_username(
        self,
        *,
        actor_role: UserRole,
        partner_id: UUID,
        telegram_username: str,
    ) -> Partner:
        self._require_admin(actor_role)
        username = self.parse_telegram_username(telegram_username)
        async with self.database.session() as session, session.begin():
            partner = await session.scalar(
                select(Partner).where(Partner.id == partner_id).with_for_update()
            )
            if partner is None:
                raise DomainError("Партнёр не найден")
            if username is not None:
                username_owner = await session.scalar(
                    select(Partner).where(
                        func.lower(Partner.telegram_username) == username.lower(),
                        Partner.id != partner_id,
                    )
                )
                if username_owner is not None:
                    raise DomainError("Этот Telegram username уже указан у другого партнёра")
            partner.telegram_username = username
            return partner

    async def create_partner_activation_link(
        self,
        *,
        actor_role: UserRole,
        partner_id: UUID,
        bot_username: str,
    ) -> str:
        self._require_admin(actor_role)
        token = secrets.token_urlsafe(18)
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        async with self.database.session() as session, session.begin():
            partner = await session.scalar(
                select(Partner).where(Partner.id == partner_id).with_for_update()
            )
            if partner is None:
                raise DomainError("Партнёр не найден")
            if partner.telegram_user_id is not None:
                raise DomainError("Партнёрский кабинет уже активирован")
            partner.activation_token_hash = token_hash
            partner.activation_created_at = datetime.now(UTC)
        return f"https://t.me/{bot_username.lstrip('@')}?start=partner_{token}"

    async def delete_partner(self, *, actor_role: UserRole, partner_id: UUID) -> None:
        self._require_admin(actor_role)
        async with self.database.session() as session, session.begin():
            partner = await session.scalar(
                select(Partner).where(Partner.id == partner_id).with_for_update()
            )
            if partner is None:
                raise DomainError("Партнёр не найден")
            has_leads = await session.scalar(
                select(Lead.id)
                .where(
                    or_(
                        Lead.partner_id == partner_id,
                        Lead.proposed_partner_id == partner_id,
                    )
                )
                .limit(1)
            )
            has_drafts = await session.scalar(
                select(LeadDraft.id)
                .where(LeadDraft.proposed_partner_id == partner_id)
                .limit(1)
            )
            if has_leads is not None or has_drafts is not None:
                raise DomainError(
                    "Партнёра с заявками удалить нельзя. Выключи его, чтобы сохранить историю"
                )
            linked_user = (
                await session.get(User, partner.telegram_user_id)
                if partner.telegram_user_id
                else None
            )
            await session.execute(delete(Channel).where(Channel.partner_id == partner_id))
            await session.delete(partner)
            if linked_user is not None:
                linked_user.role = UserRole.LEAD
                linked_user.access_status = AccessStatus.ACTIVE

    async def list_channels(self) -> list[ChannelSummary]:
        async with self.database.session() as session:
            rows = await session.execute(
                select(Channel, Partner.name)
                .join(Partner, Partner.id == Channel.partner_id)
                .order_by(Partner.name, Channel.name)
            )
            return [ChannelSummary(channel=row[0], partner_name=row[1]) for row in rows]

    async def list_partner_channels(self, partner_id: UUID) -> list[ChannelSummary]:
        async with self.database.session() as session:
            rows = await session.execute(
                select(Channel, Partner.name)
                .join(Partner, Partner.id == Channel.partner_id)
                .where(Channel.partner_id == partner_id)
                .order_by(Channel.name)
            )
            return [ChannelSummary(channel=row[0], partner_name=row[1]) for row in rows]

    async def get_channel(self, channel_id: UUID) -> ChannelSummary | None:
        async with self.database.session() as session:
            row = (
                await session.execute(
                    select(Channel, Partner.name)
                    .join(Partner, Partner.id == Channel.partner_id)
                    .where(Channel.id == channel_id)
                )
            ).one_or_none()
            return ChannelSummary(channel=row[0], partner_name=row[1]) if row else None

    async def create_channel(
        self,
        *,
        actor_role: UserRole,
        partner_id: UUID,
        name: str,
        bot_username: str,
        actor_partner_id: UUID | None = None,
    ) -> Channel:
        if actor_role is not UserRole.ADMIN and not (
            actor_role is UserRole.PARTNER and actor_partner_id == partner_id
        ):
            raise DomainError("Можно добавлять каналы только своему партнёрскому кабинету")
        clean_name = name.strip()
        if len(clean_name) < 2 or len(clean_name) > 160:
            raise DomainError("Название канала должно быть от 2 до 160 символов")
        async with self.database.session() as session, session.begin():
            partner = await session.get(Partner, partner_id)
            if partner is None:
                raise DomainError("Партнёр не найден")
            if not partner.active:
                raise DomainError("Сначала включи партнёра")
            duplicate = await session.scalar(
                select(Channel).where(
                    Channel.partner_id == partner_id,
                    Channel.name == clean_name,
                )
            )
            if duplicate is not None:
                raise DomainError("У этого партнёра уже есть канал с таким названием")
            code = secrets.token_urlsafe(12)
            channel = Channel(
                partner_id=partner_id,
                name=clean_name,
                channel_type="telegram",
                referral_code=code,
                referral_link=f"https://t.me/{bot_username.lstrip('@')}?start={code}",
            )
            session.add(channel)
            await session.flush()
            return channel

    async def toggle_channel(self, *, actor_role: UserRole, channel_id: UUID) -> Channel:
        self._require_admin(actor_role)
        async with self.database.session() as session, session.begin():
            channel = await session.scalar(
                select(Channel).where(Channel.id == channel_id).with_for_update()
            )
            if channel is None:
                raise DomainError("Канал не найден")
            channel.active = not channel.active
            return channel

    @staticmethod
    def _require_admin(actor_role: UserRole) -> None:
        if actor_role is not UserRole.ADMIN:
            raise DomainError("Действие доступно только администратору")
