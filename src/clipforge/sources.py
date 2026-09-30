"""When a source's clips may be queued and sent (spec §6.3). Pure: enqueue, the tick and the S2
policy gate all ask the same questions."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from clipforge.models import Platform, Source

_PERMISSION_FIELDS = ("granted_at", "granted_by", "evidence_url", "monetization_allowed",
                      "translation_allowed")  # fmt: skip


def source_problem(source: Source, now: datetime) -> str | None:
    """Why nothing from this source may be queued or sent right now, or None."""
    if source.status != "active":
        return f"source {source.status}"
    expires = source.permission.expires_at
    if expires is not None and now >= expires:
        return f"permission expired {expires:%Y-%m-%d}"
    deadline = source.campaign.deadline if source.campaign else None
    if deadline is not None and now > deadline:
        return f"campaign ended {deadline:%Y-%m-%d}"
    return None


def uncovered(source: Source, platforms: Iterable[Platform]) -> list[Platform]:
    covered = set(source.permission.platforms)
    return [p for p in platforms if p not in covered]


def hold_reason(source: Source | None, platforms: Iterable[Platform], now: datetime) -> str | None:
    """Why an item due on `platforms` is held, or None. No source row (dict mode) holds nothing."""
    if source is None:
        return None
    problem = source_problem(source, now)
    if problem is not None:
        return problem
    missing = uncovered(source, platforms)
    return f"permission doesn't cover {', '.join(missing)}" if missing else None


def missing_permission_fields(source: Source) -> list[str]:
    """Permission facts not recorded yet (import-toml leaves them empty; `source edit` fills)."""
    return [name for name in _PERMISSION_FIELDS if getattr(source.permission, name) is None]
