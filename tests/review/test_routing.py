"""review/routing.py (S2 spec §5.2; card 014 Task 6): one case per reason, several at once, and
the deterministic spot-check floor."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from clipforge.models import ContentItem, GateResult, ReviewDial, Routing, Violation
from clipforge.review.routing import SpotState, WindowCounts, route
from tests.posting.builders import item
from tests.review.builders import autopilot

NOW = datetime(2026, 10, 2, 9, tzinfo=UTC)
OLD = NOW - timedelta(days=60)
CLEAN = GateResult()
DONE = WindowCounts(producer={"clips:v1": 5}, dubs_in_pair=10)
QUIET = SpotState(auto_since_last=0, checks_last_7d=3, last_check_at=NOW - timedelta(hours=1))
AD = GateResult(violations=[Violation(code="missing_ad", message="x")])


def v1(**changes: Any) -> ContentItem:
    return item().model_copy(update={"producer_version": "clips:v1", **changes})


def r(dial: ReviewDial = "auto", gate: GateResult = CLEAN, counts: WindowCounts = DONE,
      spot: SpotState = QUIET, it: ContentItem | None = None, first: datetime | None = OLD,
      pair: str | None = None, parent: str | None = None) -> Routing:  # fmt: skip
    return route(it or v1(), autopilot(dial), gate, counts, spot, first_post_at=first,
                 paired_account_id=pair, parent_account_id=parent, now=NOW)  # fmt: skip


def test_auto_and_clean_is_auto() -> None:
    out = r()
    assert out.lane == "auto" and out.reasons == [] and out.window is None


def test_the_review_dial_sends_everything() -> None:
    out = r("review")
    assert (out.lane, out.reasons, out.dial) == ("review", ["dial"], "review")


def test_a_gate_violation() -> None:
    out = r(gate=AD)
    assert out.reasons == ["gate"] and out.lane == "review" and out.gate == AD


def test_sponsored_in_the_first_30_days() -> None:
    it = v1(sponsored=True)
    assert "sponsored" in r(it=it, first=NOW - timedelta(days=10)).reasons
    assert "sponsored" in r(it=it, first=None).reasons  # not posted yet
    assert "sponsored" not in r(it=it, first=OLD).reasons


def test_the_producer_window() -> None:
    out = r(counts=WindowCounts(producer={"clips:v1": 4}, dubs_in_pair=10))
    assert out.reasons == ["producer_window"] and out.window == "producer:clips:v1:4/5"
    assert r(it=v1(producer_version="clips:v2")).window == "producer:clips:v2:0/5"


def test_the_format_window_is_closed_without_versions() -> None:
    assert "format_window" not in r().reasons


def test_the_format_window_open() -> None:
    counts = WindowCounts(producer={"clips:v1": 5}, format_version=3, format_count=9)
    out = r(counts=counts)
    assert out.reasons == ["format_window"] and out.window == "format:v3:9/10"
    assert r(counts=WindowCounts(producer={"clips:v1": 5}, format_version=3,
                                 format_count=10)).lane == "auto"  # fmt: skip


def test_the_dub_window() -> None:
    counts = WindowCounts(producer={"clips:v1": 5}, dubs_in_pair=9)
    dub = v1(parent_item_id="x")
    pair = "historias-ocultas-es"
    assert r(counts=counts, it=dub, pair=pair, parent=pair).reasons == ["dub_window"]
    assert r(counts=counts, it=dub, pair=pair, parent="someone-else").reasons == []
    assert r(counts=counts, it=v1(), pair=pair, parent=pair).reasons == []


def test_several_reasons_at_once() -> None:
    counts = WindowCounts(producer={"clips:v1": 1}, dubs_in_pair=10)
    out = r("review", gate=AD, counts=counts, it=v1(sponsored=True), first=None)
    assert out.reasons == ["gate", "sponsored", "producer_window", "dial"]


def test_spot_checks_on_sample() -> None:
    assert r("sample", spot=SpotState(9, 3, NOW - timedelta(hours=1))).reasons == ["spot_check"]
    assert r("sample", spot=SpotState(8, 3, NOW - timedelta(hours=1))).reasons == []
    assert r("sample", spot=SpotState(0, 2, NOW - timedelta(hours=25))).reasons == ["spot_check"]
    assert r("sample", spot=SpotState(0, 2, NOW - timedelta(hours=23))).reasons == []
    assert r("auto", spot=SpotState(20, 0, None)).reasons == []  # auto: no spot checks


def test_the_spot_check_floor_over_30_items_is_deterministic() -> None:
    def run() -> list[bool]:
        picks: list[bool] = []
        log: list[datetime] = []
        since = 0
        for n in range(30):
            t = NOW + timedelta(hours=8 * n)  # 3 items a day for 10 days
            recent = [x for x in log if t - x <= timedelta(days=7)]
            spot = SpotState(since, len(recent), log[-1] if log else None)
            out = route(v1(), autopilot("sample"), CLEAN, DONE, spot, first_post_at=OLD,
                        paired_account_id=None, parent_account_id=None, now=t)  # fmt: skip
            check = "spot_check" in out.reasons
            picks.append(check)
            if check:
                log.append(t)
                since = 0
            else:
                since += 1
        return picks

    first = run()
    assert first == run()  # the same picks on every run
    assert sum(first) >= 3  # at least 1 in 10
    assert sum(first[:21]) >= 3  # the first week
    # any 7 days (21 items) hold at least 2: the rule counts the 7 days before each item, so a
    # rolling window can hold 2 once the first week's checks age out (the plan's own bound)
    for start in range(0, 30 - 21 + 1):
        assert sum(first[start : start + 21]) >= 2
