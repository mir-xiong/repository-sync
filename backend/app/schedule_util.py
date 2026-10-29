from __future__ import annotations

import calendar
import re
from datetime import datetime, timedelta

from croniter import croniter

from app.timeutil import SHANGHAI, as_utc, shanghai_now, to_shanghai

TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


class ScheduleError(ValueError):
    pass


def validate_schedule(
    schedule_type: str,
    schedule_time: str | None,
    weekday: int | None,
    monthday: int | None,
    cron_expr: str | None,
) -> None:
    if schedule_type not in {"daily", "weekly", "monthly", "cron"}:
        raise ScheduleError("调度类型不正确")
    if schedule_type == "cron":
        expr = (cron_expr or "").strip()
        fields = expr.split()
        if len(fields) != 5:
            raise ScheduleError("Cron 需要 5 段：分 时 日 月 周")
        if not croniter.is_valid(expr):
            raise ScheduleError("Cron 表达式不合法")
        return
    if not schedule_time or not TIME_RE.match(schedule_time):
        raise ScheduleError("时间格式需要是 HH:mm")
    if schedule_type == "weekly":
        if weekday is None or not 1 <= weekday <= 7:
            raise ScheduleError("每周调度需要选择星期一到星期日")
    if schedule_type == "monthly":
        if monthday is None or not 1 <= monthday <= 31:
            raise ScheduleError("每月调度的日期需要在 1 到 31 之间")


def _clock(schedule_time: str) -> tuple[int, int]:
    hour, minute = schedule_time.split(":")
    return int(hour), int(minute)


def is_due(
    *,
    schedule_type: str,
    schedule_time: str,
    weekday: int | None,
    monthday: int | None,
    cron_expr: str,
    moment: datetime,
) -> bool:
    current = to_shanghai(moment).replace(second=0, microsecond=0)
    if schedule_type == "cron":
        cursor = croniter(cron_expr, current - timedelta(seconds=1))
        nxt = cursor.get_next(datetime)
        if nxt.tzinfo is None:
            nxt = nxt.replace(tzinfo=SHANGHAI)
        return nxt.replace(second=0, microsecond=0) == current
    hour, minute = _clock(schedule_time)
    if current.hour != hour or current.minute != minute:
        return False
    if schedule_type == "daily":
        return True
    if schedule_type == "weekly":
        return current.isoweekday() == weekday
    last_day = calendar.monthrange(current.year, current.month)[1]
    target = monthday or 1
    effective = last_day if target > last_day else target
    return current.day == effective


def next_run(
    *,
    schedule_type: str,
    schedule_time: str,
    weekday: int | None,
    monthday: int | None,
    cron_expr: str,
    paused: bool,
    after: datetime | None = None,
) -> datetime | None:
    if paused:
        return None
    start = to_shanghai(after or shanghai_now()).replace(second=0, microsecond=0)
    if schedule_type == "cron":
        cursor = croniter(cron_expr, start)
        nxt = cursor.get_next(datetime)
        if nxt.tzinfo is None:
            nxt = nxt.replace(tzinfo=SHANGHAI)
        return as_utc(nxt.replace(second=0, microsecond=0))
    hour, minute = _clock(schedule_time)
    if schedule_type == "daily":
        candidate = start.replace(hour=hour, minute=minute)
        if candidate <= start:
            candidate += timedelta(days=1)
        return as_utc(candidate)
    if schedule_type == "weekly" and weekday is not None:
        candidate = start.replace(hour=hour, minute=minute)
        days_ahead = (weekday - candidate.isoweekday()) % 7
        candidate += timedelta(days=days_ahead)
        if candidate <= start:
            candidate += timedelta(days=7)
        return as_utc(candidate)
    if schedule_type == "monthly" and monthday is not None:
        year, month = start.year, start.month
        for _ in range(24):
            last_day = calendar.monthrange(year, month)[1]
            day = last_day if monthday > last_day else monthday
            candidate = datetime(year, month, day, hour, minute, tzinfo=SHANGHAI)
            if candidate > start:
                return as_utc(candidate)
            month += 1
            if month == 13:
                month = 1
                year += 1
    return None


def slot_key(moment: datetime | None = None) -> str:
    current = to_shanghai(moment or shanghai_now()).replace(second=0, microsecond=0)
    return current.strftime("%Y-%m-%d %H:%M")
