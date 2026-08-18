import asyncio
import logging

from app.config import Settings
from app.database import Database
from app.integrations.google_sheets import GoogleSheetsGateway, SheetData
from app.services.sheets_snapshot import SheetsSnapshotService

logger = logging.getLogger(__name__)


async def run_sheets_sync(database: Database, settings: Settings) -> None:
    if not settings.sheets_enabled:
        logger.info("Google Sheets sync is disabled")
        return

    snapshot_service = SheetsSnapshotService(database)
    gateway: GoogleSheetsGateway | None = None
    previous_sheets: dict[str, SheetData] = {}
    while True:
        try:
            if gateway is None:
                gateway = await asyncio.to_thread(
                    GoogleSheetsGateway,
                    settings.google_sheet_id,
                    settings.google_service_account_file,
                )
            sheets = await snapshot_service.build()
            changed_sheets = [
                sheet for sheet in sheets if previous_sheets.get(sheet.title) != sheet
            ]
            if changed_sheets:
                await asyncio.to_thread(gateway.replace_all, changed_sheets)
                previous_sheets.update({sheet.title: sheet for sheet in changed_sheets})
                logger.info("Google Sheets updated: %s", len(changed_sheets))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Google Sheets sync failed")
        await asyncio.sleep(settings.sheets_sync_interval_seconds)
