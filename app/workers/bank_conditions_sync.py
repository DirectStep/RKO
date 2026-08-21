import asyncio
import logging

from app.config import Settings
from app.database import Database
from app.integrations.bank_conditions import BankConditionRow, BankConditionsGateway
from app.services.bank_conditions import BankConditionsService

logger = logging.getLogger(__name__)


async def run_bank_conditions_sync(database: Database, settings: Settings) -> None:
    if not settings.bank_conditions_enabled:
        logger.info("Bank conditions sync is disabled")
        return

    service = BankConditionsService(database)
    gateway: BankConditionsGateway | None = None
    previous_rows: list[BankConditionRow] | None = None
    while True:
        try:
            if gateway is None:
                gateway = await asyncio.to_thread(
                    BankConditionsGateway,
                    settings.bank_conditions_sheet_id,
                    settings.bank_conditions_worksheet,
                    settings.google_service_account_file,
                )
            rows = await asyncio.to_thread(gateway.fetch)
            if rows != previous_rows:
                count = await service.replace_all(rows)
                previous_rows = rows
                logger.info("Bank activation conditions updated: %s", count)
        except asyncio.CancelledError:
            raise
        except Exception:
            gateway = None
            logger.exception("Bank conditions sync failed; using last valid snapshot")
        await asyncio.sleep(settings.bank_conditions_sync_interval_seconds)
