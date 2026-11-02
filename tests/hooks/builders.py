"""Small hook builders for tests."""

from __future__ import annotations

from datetime import UTC, datetime

from clipforge.models import (
    HookFit,
    HookPattern,
    HookPatternData,
    HookPatternVersion,
    HookRotation,
    HookStatus,
    RotationEntry,
)

ACCOUNT = "realtalk-clips-en"


def data(name: str = "Open question", fits: list[HookFit] | None = None) -> HookPatternData:
    return HookPatternData(
        name=name,
        structure="A question the clip answers",
        examples={"en": "WHY DID HE WALK AWAY?"},
        fits=fits or ["clips"],
        max_words=8,
    )


def entry(pid: str, weight: float, control: bool = False, version: int = 1) -> RotationEntry:
    return RotationEntry(
        pattern_id=pid, version=version, weight=weight, control=control, data=data()
    )


def rotation(*entries: RotationEntry) -> HookRotation:
    return HookRotation(account_id=ACCOUNT, entries=list(entries))


def pattern_pair(
    pid: str,
    status: HookStatus,
    fits: list[HookFit],
    version: int = 1,
    control: bool = False,
    current: int | None = None,
) -> tuple[HookPattern, HookPatternVersion]:
    pattern = HookPattern(
        id=pid,
        account_id=ACCOUNT,
        blueprint_name=None,
        status=status,
        current_version=current or version,
        control=control,
    )
    v = HookPatternVersion(
        pattern_id=pid,
        n=version,
        data=data(fits=fits),
        author="system:migration",
        created_at=datetime(2026, 10, 3, tzinfo=UTC),
    )
    return pattern, v
