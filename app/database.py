from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings


class Database:
    def __init__(self, settings: Settings) -> None:
        self.engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.sessions() as session:
            yield session

    async def ping(self) -> None:
        async with self.session() as session:
            await session.execute(text("SELECT 1"))

    async def close(self) -> None:
        await self.engine.dispose()
