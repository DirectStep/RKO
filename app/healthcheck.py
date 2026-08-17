import asyncio

from app.config import get_settings
from app.database import Database


async def check() -> None:
    database = Database(get_settings())
    try:
        await database.ping()
    finally:
        await database.close()


if __name__ == "__main__":
    asyncio.run(check())
