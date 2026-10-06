"""The policy gate v1 (S2 spec §5.1; card 014 Task 5): golden cases, EN and ES."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from clipforge.models import AssetSource, GateResult, Platform, PostCopy
from clipforge.policy.gate import codes, gate
from tests.posting.builders import item
from tests.sources_builders import account, source

NOW = datetime(2026, 10, 2, 12, tzinfo=UTC)
P = [Platform.TIKTOK, Platform.INSTAGRAM, Platform.YOUTUBE, Platform.FACEBOOK]


def copy(text: str = "Great clip — Billy Garton Jr. #podcast",
         tags: tuple[str, ...] = ("podcast",)) -> dict[Platform, PostCopy]:  # fmt: skip
    return {p: PostCopy(title="T", text=text, hashtags=list(tags)) for p in P}


def found(result: GateResult) -> list[tuple[str, str | None]]:
    return sorted((v.code, v.platform.value if v.platform else None) for v in result.violations)


CASES: list[tuple[str, dict[str, Any], dict[str, Any], list[tuple[str, str | None]]]] = [
    ("clean clip", {}, {}, []),
    ("ai asset without the flag",
     {"assets": [AssetSource(kind="generated", license="own", model="z-image")]}, {},
     [("missing_ai_label", None)]),
    ("ai asset with the flag",
     {"assets": [AssetSource(kind="generated", license="own")], "ai_disclosure": True}, {}, []),
    ("music generated without the flag",
     {"assets": [AssetSource(kind="music_generated", license="own")]}, {},
     [("missing_ai_label", None)]),
    ("sponsored without #ad on youtube", {"sponsored": True},
     {"copy": {**copy(tags=("ad", "podcast")),
               Platform.YOUTUBE: PostCopy(title="T", text="x Billy Garton Jr.",
                                          hashtags=["podcast"])}},
     [("missing_ad", "youtube")]),
    ("sponsored with #ad in the text", {"sponsored": True},
     {"copy": copy("Great clip — Billy Garton Jr. #ad")}, []),
    ("missing credit on instagram", {},
     {"copy": {**copy(), Platform.INSTAGRAM: PostCopy(text="no credit here")}},
     [("missing_credit", "instagram")]),
    ("credit not required for an own source", {},
     {"source": source(kind="own"), "copy": copy("own clip")}, []),
    ("credit required by the blueprint for an own source", {},
     {"source": source(kind="own"), "copy": copy("own clip"), "require_credit": True},
     [("missing_credit", p.value) for p in P]),
    ("unrecorded dict item, source with a permission",
     {"assets": [AssetSource(kind="source_video", license="unrecorded")]}, {}, []),
    ("unrecorded dict item, no source",
     {"assets": [AssetSource(kind="source_video", license="unrecorded")]}, {"source": None},
     [("license_unrecorded", None)]),
    ("stock asset without a license",
     {"assets": [AssetSource(kind="stock", license="")]}, {}, [("license_unrecorded", None)]),
    ("cross-account duplicate at iou 0.6", {},
     {"others": [item("clip_09", start=6.0, end=36.0, account="founder-tapes-en")]},
     [("cross_account_duplicate", None)]),
    ("cross-account overlap at iou 0.4 is fine", {},
     {"others": [item("clip_09", start=15.0, end=45.0, account="founder-tapes-en")]}, []),
    ("same-account overlap is not a duplicate", {},
     {"others": [item("clip_09", start=6.0, end=36.0)]}, []),
    ("another video at the same times is not a duplicate", {},
     {"others": [item("clip_09", source_hash="c" * 64, account="founder-tapes-en")]}, []),
    ("expired permission", {}, {"source": source(expires_at=NOW - timedelta(days=1))},
     [("source_held", None)]),
    ("narrowed permission", {}, {"source": source(platforms=[Platform.TIKTOK])},
     [("source_held", None)]),
    ("es clip clean", {"language": "es"}, {"copy": copy("Gran clip — Billy Garton Jr.")}, []),
    ("es sponsored with #ad", {"language": "es", "sponsored": True},
     {"copy": copy("Gran clip — Billy Garton Jr.", tags=("ad",))}, []),
    ("es sponsored without #ad", {"language": "es", "sponsored": True},
     {"copy": copy("Gran clip — Billy Garton Jr. #publicidad", tags=("publicidad",))},
     [("missing_ad", p.value) for p in P]),
]  # fmt: skip


@pytest.mark.parametrize(("name", "changes", "kwargs", "expected"), CASES,
                         ids=[c[0] for c in CASES])  # fmt: skip
def test_gate_golden(
    name: str, changes: dict[str, Any], kwargs: dict[str, Any],
    expected: list[tuple[str, str | None]],
) -> None:  # fmt: skip
    it = item().model_copy(update=changes)
    result = gate(it, account(), kwargs.get("source", source()), kwargs.get("copy", copy()),
                  kwargs.get("others", []), require_credit=kwargs.get("require_credit", False),
                  platforms=P, now=NOW)  # fmt: skip
    assert found(result) == sorted(expected)


def test_codes_are_listed_once() -> None:
    result = gate(item().model_copy(update={"sponsored": True}), account(), source(), copy(), [],
                  require_credit=False, platforms=P, now=NOW)  # fmt: skip
    assert codes(result) == ["missing_ad"]


def test_the_gate_is_pure() -> None:
    it, src, c = item(), source(), copy()
    gate(it, account(), src, c, [], require_credit=True, platforms=P, now=NOW)
    assert (it, src, c) == (item(), source(), copy())
