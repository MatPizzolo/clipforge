"""The brake (S2 spec §6.7): Dict keys `brake:all` and `brake:<account>`, each a `Brake` JSON.

The key is written first by `posting/actions.pause` (its one writer), so a /pause survives a
Neon outage; `posting_state` follows. An account is braked when `brake:all` or its own key is
on. /go writes `on=false` and never deletes a key, so the time of every /go survives too. The
dispatcher reads every key each tick (`touch_all`), which keeps them alive against the Dict's
7-day expiry (ADR-24). Modal-free.
"""

from __future__ import annotations

import logging

from pydantic import ValidationError

from clipforge.models import Brake
from clipforge.pipeline.deps import KV

log = logging.getLogger(__name__)

PREFIX = "brake:"
ALL = "all"


def key(scope: str) -> str:
    return f"{PREFIX}{scope}"


def read(kv: KV, scope: str) -> Brake | None:
    raw = kv.get(key(scope))
    if raw is None:
        return None
    try:
        return Brake.model_validate_json(raw)
    except ValidationError:
        # a broken key must never read as "go": treat it as on, and say so
        log.warning("brake key %s is invalid; treating it as on", key(scope))
        return Brake.model_validate({"scope": scope, "on": True, "at": "1970-01-01T00:00:00Z",
                                     "actor": "system:brake"})  # fmt: skip


def braked(kv: KV, account_id: str) -> bool:
    """True while `brake:all` or `brake:<account>` is on."""
    return any(b is not None and b.on for b in (read(kv, ALL), read(kv, account_id)))


def braked_by_fleet(kv: KV) -> bool:
    b = read(kv, ALL)
    return b is not None and b.on


def latest(kv: KV, account_id: str) -> Brake | None:
    """The newest of the account's key and the fleet key (for the daily repair)."""
    found = [b for b in (read(kv, ALL), read(kv, account_id)) if b is not None]
    return max(found, key=lambda b: b.at) if found else None


def write(kv: KV, b: Brake) -> None:
    """Only `posting/actions.py` calls this (one writer, ADR-14)."""
    kv.put(key(b.scope), b.model_dump_json())


def touch_all(kv: KV) -> list[Brake]:
    """Every brake key, read one by one with `get` (activity, ADR-24); the dispatcher calls it
    every tick."""
    found = []
    for name in kv.keys():  # noqa: SIM118 (a KV, not a dict)
        if name.startswith(PREFIX) and (b := read(kv, name[len(PREFIX) :])) is not None:
            found.append(b)
    return found
