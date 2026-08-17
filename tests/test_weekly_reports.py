from datetime import UTC, datetime

from app.workers.weekly_reports import next_report_at


def test_next_report_is_same_friday_before_eight() -> None:
    now = datetime(2026, 8, 21, 19, 30, tzinfo=UTC)
    assert next_report_at(now) == datetime(2026, 8, 21, 20, 0, tzinfo=UTC)


def test_next_report_is_next_friday_after_eight() -> None:
    now = datetime(2026, 8, 21, 20, 1, tzinfo=UTC)
    assert next_report_at(now) == datetime(2026, 8, 28, 20, 0, tzinfo=UTC)


def test_next_report_from_monday() -> None:
    now = datetime(2026, 8, 17, 9, 0, tzinfo=UTC)
    assert next_report_at(now) == datetime(2026, 8, 21, 20, 0, tzinfo=UTC)
