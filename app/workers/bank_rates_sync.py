import asyncio
import logging

from app.config import Settings
from app.database import Database
from app.integrations.bank_rates import BankRateRow, BankRatesGateway
from app.services.bank_rates import BankRatesService

logger = logging.getLogger(__name__)


async def run_bank_rates_sync(database: Database, settings: Settings) -> None:
    if not settings.bank_rates_enabled:
        logger.info("Bank rates sync is disabled")
        return

    service = BankRatesService(database)
    gateway: BankRatesGateway | None = None
    previous_rows: list[BankRateRow] | None = None
    while True:
        try:
            if gateway is None:
                gateway = await asyncio.to_thread(
                    BankRatesGateway,
                    settings.bank_rates_sheet_id,
                    settings.bank_rates_worksheet,
                    settings.google_service_account_file,
                )
            rows = await asyncio.to_thread(gateway.fetch)
            if rows != previous_rows:
                count = await service.replace_all(rows)
                previous_rows = rows
                logger.info("Bank rates updated: %s", count)
        except asyncio.CancelledError:
            raise
        except Exception:
            gateway = None
            logger.exception("Bank rates sync failed; using last valid snapshot")
        await asyncio.sleep(settings.bank_rates_sync_interval_seconds)
