from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo("Asia/Shanghai")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def to_shanghai(value: datetime) -> datetime:
    return as_utc(value).astimezone(SHANGHAI)


def shanghai_now() -> datetime:
    return datetime.now(SHANGHAI)
