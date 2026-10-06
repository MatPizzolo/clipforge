"""Who made a change (ADR-42, S2 spec §2). One pattern for every writer: `posting/actions.py`,
the autopilot service, and the check constraints of migration 0002."""

from __future__ import annotations

import re

# telegram:<id>, web:<login>, session:<name>, the CLI's cli:<os user>, and system:<component>
# for changes nobody tapped (system:autopilot, system:demotion, system:upload-post,
# system:daily, system:migration)
ACTOR = re.compile(
    r"telegram:[0-9]{1,20}|web:[A-Za-z0-9-]{1,39}|session:[a-z0-9][a-z0-9-]{0,39}"
    r"|cli:[A-Za-z0-9._-]{1,32}|system:[a-z](?:[a-z-]{0,38}[a-z])?"
)


def checked(actor: str) -> str:
    """`actor` if it is one; ValueError otherwise, so a write is never anonymous."""
    if not ACTOR.fullmatch(actor):
        raise ValueError(f"not an actor: {actor!r}")
    return actor


def is_system(actor: str) -> bool:
    return actor.startswith("system:")
