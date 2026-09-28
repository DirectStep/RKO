from io import BytesIO
from uuid import uuid4

import pytest
from openpyxl import load_workbook

from app.reports.partner_report import build_partner_report


@pytest.mark.asyncio
async def test_partner_report_rows_have_dark_text_on_white_background(monkeypatch) -> None:
    async def cabinet_data(*args, **kwargs):
        return {
            "leads": [{
                "short_id": "RKO-0001",
                "name": "Тестовый клиент",
                "date": "2026-09-28",
                "channel": "Палки",
                "status": "in_progress",
                "is_repeat": False,
                "banks": [{
                    "bank": "ПСБ",
                    "status": "planned",
                    "reward_estimate": "1250",
                    "reward_fact": "0",
                    "payment_status": "calculated",
                }],
            }],
        }

    monkeypatch.setattr("app.reports.partner_report.partner_cabinet_data", cabinet_data)
    report = await build_partner_report(None, uuid4())
    sheet = load_workbook(BytesIO(report)).active

    assert sheet["A2"].value == "RKO-0001"
    assert sheet["H2"].value == 1250
    for cell in sheet[2]:
        assert cell.font.color.rgb == "FF171717"
        assert cell.fill.patternType == "solid"
        assert cell.fill.fgColor.rgb == "FFFFFFFF"
