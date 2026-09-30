"""Posting slots: wall-clock times in the audience's time zone (spec §6)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from clipforge.models import PostingSchedule

SLOT_WINDOW = timedelta(minutes=30)  # a slot missed by longer than this is dropped


def day_slots(schedule: PostingSchedule, day: date) -> list[datetime]:
    zone = ZoneInfo(schedule.timezone)
    slots = []
    for text in schedule.slots:
        hour, minute = (int(part) for part in text.split(":"))
        slots.append(datetime.combine(day, time(hour, minute), tzinfo=zone))
    return slots


def current_slot(schedule: PostingSchedule, now: datetime) -> datetime | None:
    """The latest slot at or before `now`, if it's at most SLOT_WINDOW old."""
    local = now.astimezone(ZoneInfo(schedule.timezone))
    for day in (local.date(), local.date() - timedelta(days=1)):
        past = [slot for slot in day_slots(schedule, day) if slot <= now]
        if past:
            latest = past[-1]
            return latest if now - latest <= SLOT_WINDOW else None
    return None


def next_slot(schedule: PostingSchedule, now: datetime) -> datetime | None:
    if not schedule.slots:
        return None
    local = now.astimezone(ZoneInfo(schedule.timezone))
    for offset in range(2):
        for slot in day_slots(schedule, local.date() + timedelta(days=offset)):
            if slot > now:
                return slot
    raise AssertionError("unreachable: there is at least one slot per day")
