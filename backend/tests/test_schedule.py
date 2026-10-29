from datetime import datetime

import pytest

from app.schedule_util import ScheduleError, is_due, next_run, validate_schedule
from app.timeutil import SHANGHAI, to_shanghai


def test_reject_invalid_cron() -> None:
    with pytest.raises(ScheduleError):
        validate_schedule("cron", None, None, None, "* * * * * *")
    with pytest.raises(ScheduleError):
        validate_schedule("cron", None, None, None, "60 1 * * *")
    validate_schedule("cron", None, None, None, "30 9 * * 1")


def test_monthly_uses_last_day_when_missing() -> None:
    moment = datetime(2026, 2, 28, 9, 30, tzinfo=SHANGHAI)
    assert is_due(
        schedule_type="monthly",
        schedule_time="09:30",
        weekday=None,
        monthday=31,
        cron_expr="",
        moment=moment,
    )
    earlier = datetime(2026, 2, 27, 9, 30, tzinfo=SHANGHAI)
    assert not is_due(
        schedule_type="monthly",
        schedule_time="09:30",
        weekday=None,
        monthday=31,
        cron_expr="",
        moment=earlier,
    )


def test_leap_day_for_missing_monthday() -> None:
    moment = datetime(2024, 2, 29, 8, 0, tzinfo=SHANGHAI)
    assert is_due(
        schedule_type="monthly",
        schedule_time="08:00",
        weekday=None,
        monthday=31,
        cron_expr="",
        moment=moment,
    )


def test_weekly_and_daily_next_run() -> None:
    after = datetime(2026, 10, 28, 15, 0, tzinfo=SHANGHAI)
    daily = next_run(
        schedule_type="daily",
        schedule_time="09:30",
        weekday=None,
        monthday=None,
        cron_expr="",
        paused=False,
        after=after,
    )
    assert daily is not None
    assert to_shanghai(daily).strftime("%Y-%m-%d %H:%M") == "2026-10-29 09:30"
    weekly = next_run(
        schedule_type="weekly",
        schedule_time="09:30",
        weekday=3,
        monthday=None,
        cron_expr="",
        paused=False,
        after=after,
    )
    assert weekly is not None
    assert to_shanghai(weekly).isoweekday() == 3
    assert next_run(
        schedule_type="daily",
        schedule_time="09:30",
        weekday=None,
        monthday=None,
        cron_expr="",
        paused=True,
        after=after,
    ) is None


def test_cron_matches_minute() -> None:
    moment = datetime(2026, 10, 28, 9, 30, tzinfo=SHANGHAI)
    assert is_due(
        schedule_type="cron",
        schedule_time="",
        weekday=None,
        monthday=None,
        cron_expr="30 9 * * *",
        moment=moment,
    )
    assert not is_due(
        schedule_type="cron",
        schedule_time="",
        weekday=None,
        monthday=None,
        cron_expr="30 9 * * *",
        moment=moment.replace(minute=31),
    )
