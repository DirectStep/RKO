import secrets
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from uuid import UUID

from sqlalchemy import select

from app.database import Database
from app.domain.enums import UserRole
from app.domain.operations import DomainError
from app.models import Channel, Partner


@dataclass(frozen=True)
class ChannelSummary:
    channel: Channel
    partner_name: str


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

    async def list_partners(self) -> list[Partner]:
        async with self.database.session() as session:
            result = await session.scalars(select(Partner).order_by(Partner.name))
            return list(result)

    async def get_partner(self, partner_id: UUID) -> Partner | None:
        async with self.database.session() as session:
            return await session.get(Partner, partner_id)

    async def create_partner(
        self, *, actor_role: UserRole, name: str, commission_percent: Decimal
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
            partner = Partner(
                name=clean_name,
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
    ) -> Channel:
        self._require_admin(actor_role)
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
