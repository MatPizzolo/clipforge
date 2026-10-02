"""Posting schedule rules shared by the POSTING_* settings and account schedules (spec §6.2)."""

from __future__ import annotations

import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_SLOTS = ["08:00", "10:30", "13:00", "16:00", "19:00", "21:30"]
SLOT = re.compile(r"([01]\d|2[0-3]):[0-5]\d")
HASHTAG = re.compile(r"\w+")


def normalize_slots(slots: list[str]) -> list[str]:
    """ "8:00" means 08:00."""
    return [f"0{slot}" if re.fullmatch(r"\d:\d\d", slot) else slot for slot in slots]


def normalize_hashtags(tags: list[str]) -> list[str]:
    return [tag.lstrip("#") for tag in tags]


def schedule_problem(
    timezone: str, slots: list[str], hashtags: list[str]
) -> tuple[str, str] | None:
    try:
        ZoneInfo(timezone)
    except (ZoneInfoNotFoundError, ValueError, OSError):  # a tzdata folder: IsADirectoryError
        return "timezone", f"unknown time zone {timezone!r}"
    if not 1 <= len(slots) <= 12:
        return "slots", "between 1 and 12 posting slots"
    if any(not SLOT.fullmatch(slot) for slot in slots):
        return "slots", "slots must be HH:MM, e.g. 08:00"
    if sorted(set(slots)) != slots:
        return "slots", "slots must be unique and in order"
    if any(not HASHTAG.fullmatch(tag) for tag in hashtags):
        return "hashtags", "hashtags use letters, digits and _ only"
    return None
