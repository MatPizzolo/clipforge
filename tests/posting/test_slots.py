"""Slot times: wall-clock times in the posting time zone."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from clipforge.models import PostingSchedule
from clipforge.posting.slots import current_slot, day_slots, next_slot

NY = ZoneInfo("America/New_York")


def _settings() -> PostingSchedule:
    return PostingSchedule(timezone="America/New_York", slots=["08:00", "12:00", "18:00"])


def test_day_slots() -> None:
    slots = day_slots(_settings(), date(2026, 9, 29))
    assert [s.strftime("%H:%M") for s in slots] == ["08:00", "12:00", "18:00"]
    assert all(s.tzinfo == NY for s in slots)


def test_current_slot_only_inside_the_window() -> None:
    s = _settings()
    assert current_slot(s, datetime(2026, 9, 29, 12, 29, tzinfo=NY)) == datetime(
        2026, 9, 29, 12, 0, tzinfo=NY
    )
    assert current_slot(s, datetime(2026, 9, 29, 12, 31, tzinfo=NY)) is None  # missed: dropped
    assert current_slot(s, datetime(2026, 9, 29, 7, 59, tzinfo=NY)) is None


def test_next_slot_rolls_to_tomorrow() -> None:
    s = _settings()
    assert next_slot(s, datetime(2026, 9, 29, 18, 0, tzinfo=NY)) == datetime(
        2026, 9, 30, 8, 0, tzinfo=NY
    )


def test_slots_follow_wall_clock_across_dst() -> None:
    s = _settings()
    before, after = day_slots(s, date(2026, 10, 31)), day_slots(s, date(2026, 11, 1))
    assert before[0].utcoffset() != after[0].utcoffset()  # EDT -> EST
    assert after[0].strftime("%H:%M") == "08:00"


def test_no_slots_means_no_next_slot() -> None:
    assert next_slot(PostingSchedule(), datetime(2026, 9, 29, 9, 0, tzinfo=NY)) is None
    assert current_slot(PostingSchedule(), datetime(2026, 9, 29, 9, 0, tzinfo=NY)) is None


def test_another_timezone() -> None:
    mx = PostingSchedule(timezone="America/Mexico_City", slots=["09:00"])
    now = datetime(2026, 9, 29, 9, 5, tzinfo=ZoneInfo("America/Mexico_City"))
    assert current_slot(mx, now) == datetime(
        2026, 9, 29, 9, 0, tzinfo=ZoneInfo("America/Mexico_City")
    )
