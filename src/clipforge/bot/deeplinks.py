"""Dashboard deep links on bot messages (ADR-44; link formats in docs/studio/08 §2b).

Each helper returns one keyboard row of URL buttons, or an empty row when DASHBOARD_URL is
unset, so callers add it unconditionally. The dashboard keeps the target through login
(`callbackUrl`, decision log #99)."""

from __future__ import annotations

from urllib.parse import quote

from clipforge.bot.telegram import Button
from clipforge.models import ContentItem


def _url(base: str, *parts: str) -> str:
    return base + "".join(f"/{quote(part, safe='')}" for part in parts)


def job_row(base: str | None, job_id: str) -> list[Button]:
    return [] if base is None else [("Job ↗", _url(base, "jobs", job_id))]


def account_row(base: str | None, account_id: str) -> list[Button]:
    return [] if base is None else [("Account ↗", _url(base, "accounts", account_id))]


def item_row(base: str | None, item: ContentItem) -> list[Button]:
    """A posting clip: its job and its source."""
    if base is None:
        return []
    row = job_row(base, item.clip.job_id) if item.clip is not None else []
    if item.source_id is not None:
        row.append(("Source ↗", _url(base, "sources", item.source_id)))
    return row
