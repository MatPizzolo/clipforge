"""Hook rotation (ADR-50, hooks spec §4.2): resolve the live library or a freeze into a rotation,
and a seeded weighted pick. Pure: no database, no clock."""

from __future__ import annotations

import hashlib

from clipforge.models import (
    HookFit,
    HookPattern,
    HookPatternVersion,
    HookPick,
    HookResult,
    HookRotation,
    HookStamp,
    RotationEntry,
)


def resolve(
    account_id: str,
    producer: HookFit,
    patterns: list[tuple[HookPattern, HookPatternVersion]],
    weights: dict[str, float],
    open_freeze: HookRotation | None,
) -> HookRotation:
    """An open freeze's snapshot wins; otherwise the approved patterns that fit the producer,
    with weight > 0, at their current versions."""
    if open_freeze is not None:
        return open_freeze
    entries = [
        RotationEntry(
            pattern_id=p.id, version=v.n, weight=weights[p.id], control=p.control, data=v.data
        )
        for p, v in patterns
        if p.status == "approved"
        and producer in v.data.fits
        and v.n == p.current_version
        and weights.get(p.id, 0.0) > 0
    ]
    return HookRotation(account_id=account_id, entries=_ordered(entries))


def seed_for(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def clip_seed(source_hash: str, start: float, end: float, rotation: HookRotation) -> str:
    return seed_for(source_hash, f"{start:.3f}", f"{end:.3f}", rotation.id)


def pick(rotation: HookRotation | None, seed: str) -> HookPick | None:
    """A weighted draw from `int(seed, 16) / 2**256` over the entries in (pattern_id, version)
    order. None for an empty rotation: the producer behaves as the control."""
    if rotation is None or not rotation.entries:
        return None
    entries = _ordered(rotation.entries)
    point = int(seed, 16) / 2**256 * sum(e.weight for e in entries)
    chosen = entries[-1]
    for e in entries:
        point -= e.weight
        if point < 0:
            chosen = e
            break
    return HookPick(
        pattern_id=chosen.pattern_id,
        version=chosen.version,
        control=chosen.control,
        data=chosen.data,
    )


def control_entry(rotation: HookRotation | None) -> RotationEntry | None:
    if rotation is None:
        return None
    return next((e for e in rotation.entries if e.control), None)


def weights_of(rotation: HookRotation) -> dict[str, float]:
    return {f"{e.pattern_id}@{e.version}": e.weight for e in rotation.entries}


def control_stamp(rotation: HookRotation | None, title: str) -> HookStamp | None:
    """The flag-off stamp (spec §2.5): today's title under the control pattern, not drawn, with
    the rotation's weights. None without a rotation or a control."""
    control = control_entry(rotation)
    if rotation is None or control is None:
        return None
    result = HookResult(pattern_id=control.pattern_id, version=control.version, text=title)
    return HookStamp(
        result=result,
        rotation_id=rotation.id,
        weights=weights_of(rotation),
        frozen_by=rotation.frozen_by,
    )


def stamp_for(
    rotation: HookRotation | None, title: str, hook: HookResult | None, *, flag_on: bool
) -> tuple[HookStamp | None, str]:
    """The item's stamp and title, shared by package (metadata.json) and enqueue, so the two
    agree. Flag on with a drawn result: that result, and its line as written; otherwise the
    control stamp and the highlights title (spec §2.1, §2.5)."""
    if flag_on and hook is not None:
        stamp = HookStamp(
            result=hook,
            rotation_id=None if rotation is None else rotation.id,
            weights={} if rotation is None else weights_of(rotation),
            frozen_by=None if rotation is None else rotation.frozen_by,
        )
        return stamp, hook.text
    return control_stamp(rotation, title), title


def rotation_note(rotation: HookRotation | None, note: str | None) -> str:
    """`Versions.hook_rotation`: the rotation's id, else why there is none."""
    return rotation.id if rotation is not None else (note or "none")


def _ordered(entries: list[RotationEntry]) -> list[RotationEntry]:
    return sorted(entries, key=lambda e: (e.pattern_id, e.version))
