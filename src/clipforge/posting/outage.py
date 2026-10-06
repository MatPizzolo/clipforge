"""The outage flag (#217, card 040): `posting_daily` sets it when its newest table snapshot
(`db-<date>.json`) is more than 2 days old, so a gap in the daily reconcile is noticed before
anything is sent again. While it is set, rebuild is skipped and the dispatcher sends nothing;
`/go` is the only way to clear it. Value: the date of the last good snapshot. Writers:
`set_outage` (daily), `clear_outage` (/go). A Dict claim like the slot claims; the dispatcher's
read every tick keeps it from expiring. Modal-free."""

from __future__ import annotations

from clipforge.pipeline.deps import KV

OUTAGE_KEY = "posting:outage"


def outage_since(kv: KV) -> str | None:
    return kv.get(OUTAGE_KEY)


def set_outage(kv: KV, since: str) -> bool:
    """True when this call set it (the first day of the outage)."""
    return kv.put(OUTAGE_KEY, since, skip_if_exists=True)


def clear_outage(kv: KV) -> bool:
    """True when a flag was cleared."""
    if kv.get(OUTAGE_KEY) is None:
        return False
    kv.delete(OUTAGE_KEY)
    return True
