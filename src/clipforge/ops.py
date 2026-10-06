"""Ops alerts to the owner's chat (ADR-45): failures that would otherwise be silent.

`alert` is deduped by a Dict claim per (kind, subject, UTC hour), sends at most
`MAX_PER_HOUR` messages an hour, and holds everything that isn't urgent during quiet hours
(23:00 to 08:00 in the owner's time zone). Held alerts are folded into one "N more" message by
`flush`, which the posting tick calls every 5 minutes. An alert never raises: a failure here is
logged and never fails the step that raised the alert. Modal-free.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from clipforge.bot.telegram import TelegramSender
from clipforge.config import Settings
from clipforge.jobs import utcnow
from clipforge.pipeline.deps import KV

log = logging.getLogger(__name__)

QUIET_FROM, QUIET_UNTIL = 23, 8  # local hours: quiet from 23:00 until 08:00
MAX_PER_HOUR = 20
TEXT_LIMIT = 500
FOLD_LINES = 5
HELD_PREFIX = "notify:held:"
PENDING_KEY = "notify:pending"  # set while anything is held, so flush is one `get` otherwise


@dataclass
class OpsAlerts:
    kv: KV
    sender: TelegramSender
    chat_id: int
    timezone: str
    dashboard_url: str | None = None
    clock: Callable[[], datetime] = utcnow  # when a caller passes no `now` (tests pin it)

    def quiet(self, now: datetime) -> bool:
        hour = now.astimezone(ZoneInfo(self.timezone)).hour
        return hour >= QUIET_FROM or hour < QUIET_UNTIL

    def alert(
        self, text: str, kind: str, subject: str = "", *, urgent: bool = False,
        path: str | None = None, now: datetime | None = None,
    ) -> str:  # fmt: skip
        """Send, hold or drop one alert; returns "sent", "held", "duplicate" or "error".
        `urgent` (brake-worthy: publishing broken across accounts, spend over 2x budget) breaks
        through quiet hours. `path` is a dashboard page for a "Open ↗" button."""
        try:
            return self._alert(text, kind, subject, urgent, path, now or self.clock())
        except Exception:
            log.warning("ops alert %s:%s failed", kind, subject, exc_info=True)
            return "error"

    def _alert(
        self, text: str, kind: str, subject: str, urgent: bool, path: str | None, now: datetime
    ) -> str:
        hour = f"{now.astimezone(UTC):%Y%m%d%H}"
        # Claimed set-if-absent so two containers can't both send it, and released if the send
        # fails: the key survives only for an alert that was sent or held (coordinator's A6
        # review), so a Telegram outage never swallows the hour's alert.
        claim = f"notify:{kind}:{subject}:{hour}"
        if not self.kv.put(claim, "1", skip_if_exists=True):
            return "duplicate"
        text = _cap(text)
        slot = None if (self.quiet(now) and not urgent) else self._take_slot(hour)
        if slot is None:
            self.kv.put(f"{HELD_PREFIX}{now.astimezone(UTC).isoformat()}:{kind}:{subject}", text)
            self.kv.put(PENDING_KEY, "1")
            return "held"
        buttons = None
        if path is not None and self.dashboard_url is not None:
            buttons = [[("Open ↗", f"{self.dashboard_url}{path}")]]
        try:
            self.sender.send_message(self.chat_id, f"⚠️ {text}", buttons=buttons)
        except Exception:
            self.kv.delete(slot)
            self.kv.delete(claim)
            raise
        return "sent"

    def _take_slot(self, hour: str) -> str | None:
        """One of MAX_PER_HOUR set-if-absent slots for this hour (the KV has no counter);
        returns its key, or None when the hour is full."""
        for n in range(1, MAX_PER_HOUR + 1):
            key = f"notify:sent:{hour}:{n}"
            if self.kv.put(key, "1", skip_if_exists=True):
                return key
        return None

    def flush(self, now: datetime | None = None) -> int:
        """Outside quiet hours, send the held alerts as one message; returns how many."""
        try:
            return self._flush(now or self.clock())
        except Exception:
            log.warning("flushing held ops alerts failed", exc_info=True)
            return 0

    def _flush(self, now: datetime) -> int:
        if self.kv.get(PENDING_KEY) is None or self.quiet(now):
            return 0
        # one flush per 5-minute window, so an overlapping tick can't send the same alerts
        utc = now.astimezone(UTC)
        claim = f"notify:flush:{utc:%Y%m%d%H}{utc.minute // 5:02d}"
        if not self.kv.put(claim, "1", skip_if_exists=True):
            return 0
        keys = sorted(k for k in self.kv.keys() if k.startswith(HELD_PREFIX))  # noqa: SIM118
        texts = [text for key in keys if (text := self.kv.get(key)) is not None]
        if texts:
            lines = [f"⚠️ {len(texts)} alerts held (quiet hours or over {MAX_PER_HOUR} an hour):"]
            lines += [f"• {text.splitlines()[0][:200]}" for text in texts[:FOLD_LINES]]
            if len(texts) > FOLD_LINES:
                lines.append(f"{len(texts) - FOLD_LINES} more → dashboard")
            try:
                self.sender.send_message(self.chat_id, "\n".join(lines))
            except Exception:
                self.kv.delete(claim)  # nothing was deleted: the next tick tries again
                raise
            for key in keys:
                self.kv.delete(key)
        # Clear the flag only now, then look again: an alert held while this ran (its key is
        # written before the flag) puts the flag back, so it is never stranded.
        self.kv.delete(PENDING_KEY)
        if any(k.startswith(HELD_PREFIX) for k in self.kv.keys()):  # noqa: SIM118
            self.kv.put(PENDING_KEY, "1")
        return len(texts)


def _cap(text: str) -> str:
    text = text.strip()
    return text if len(text) <= TEXT_LIMIT else text[: TEXT_LIMIT - 1] + "…"


def owner_chat(settings: Settings) -> int | None:
    """The posting chat, else the first allowed Telegram user (one owner, 08 §2b)."""
    if settings.posting_chat_id is not None:
        return settings.posting_chat_id
    return settings.telegram_allowed_user_ids[0] if settings.telegram_allowed_user_ids else None


def ops_alerts(kv: KV, sender: TelegramSender | None, settings: Settings) -> OpsAlerts | None:
    chat = owner_chat(settings)
    if sender is None or chat is None:
        return None
    return OpsAlerts(kv, sender, chat, settings.owner_zone(), settings.dashboard_url)
