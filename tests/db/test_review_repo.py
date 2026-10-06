"""db/review.py (card 014 Task 6): what counts toward the windows (R2, R6), spot-check state,
the routing stamp."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from clipforge.db.engine import Database
from clipforge.db.posting import SqlPostingRepo, _event
from clipforge.db.review import ReviewRepo
from clipforge.db.tables import content_items, post_events
from clipforge.models import LEGACY_PLATFORMS, GateResult, Platform, Routing, Violation
from tests.dbhelpers import BILLY_SOURCE, make_account, seed
from tests.posting.builders import item

T = datetime(2026, 10, 2, 9, tzinfo=UTC)
RT = "realtalk-clips-en"


def _items(db: Database, n: int, version: str = "clips:v1") -> list[str]:
    seed(db, make_account(), sources=[BILLY_SOURCE])
    repo = SqlPostingRepo(db)
    refs = []
    for k in range(1, n + 1):
        it = item(f"clip_{k:02d}", start=k * 40, end=k * 40 + 30).model_copy(
            update={"producer_version": version})  # fmt: skip
        repo.add(it, list(LEGACY_PLATFORMS))
        refs.append(it.id)
    return refs


def _decide(db: Database, ref: str, kind: str, actor: str, at: datetime = T) -> None:
    with db.begin() as conn:
        _event(conn, ref, kind, at, actor=actor)


class FakeFormat:
    def format_window(self, account_id: str) -> tuple[int, int] | None:
        return (3, 9)


def test_counts_only_review_decisions_by_people(db: Database) -> None:
    refs = _items(db, 7)
    _decide(db, refs[0], "approved", "web:mat")  # a review decision: counts
    _decide(db, refs[0], "approved", "web:mat")  # the same item twice: counted once
    _decide(db, refs[1], "approved", "system:autopilot")  # the system: no
    repo = SqlPostingRepo(db)
    repo.toggle_posted(refs[2], Platform.TIKTOK, T, actor="telegram:42")  # assisted ✅: no
    from clipforge.models import PostVerdict

    repo.set_verdict(refs[3], PostVerdict(kind="skipped", at=T), actor="telegram:42")  # ⏭: no
    repo.set_verdict(refs[4], PostVerdict(kind="rejected", at=T), actor="telegram:42")  # 🗑: no
    _decide(db, refs[5], "reviewed", "web:mat")  # a review reject: counts
    _decide(db, refs[6], "approved", "cli:mat")
    counts = ReviewRepo(db).counts(RT, item())
    assert counts.producer == {"clips:v1": 3}
    assert (counts.format_version, counts.format_count, counts.dubs_in_pair) == (None, 0, 0)


def test_the_format_window_comes_from_the_injected_source(db: Database) -> None:
    _items(db, 1)
    counts = ReviewRepo(db, FakeFormat()).counts(RT, item())
    assert (counts.format_version, counts.format_count) == (3, 9)


def test_stamp_and_spot_state(db: Database) -> None:
    refs = _items(db, 4)
    repo = ReviewRepo(db)
    gate = GateResult(violations=[Violation(code="missing_ad", message="x")])
    check = Routing(lane="review", reasons=["spot_check"], dial="sample", gate=GateResult())
    auto = Routing(lane="auto", reasons=[], dial="sample", gate=GateResult())
    held = Routing(lane="review", reasons=["gate"], dial="sample", gate=gate)
    repo.stamp(refs[0], check, T)
    repo.stamp(refs[1], auto, T + timedelta(hours=1))
    repo.stamp(refs[2], held, T + timedelta(hours=2))
    repo.stamp(refs[3], auto, T + timedelta(hours=3))
    state = repo.spot_state(RT, T + timedelta(days=1))
    assert (state.auto_since_last, state.checks_last_7d, state.last_check_at) == (2, 1, T)
    assert repo.spot_state(RT, T + timedelta(days=8)).checks_last_7d == 0
    with db.begin() as conn:
        row = conn.execute(select(content_items).where(content_items.c.id == refs[2])).one()
        kinds = conn.execute(select(post_events.c.kind, post_events.c.actor)
                             .where(post_events.c.item_id == refs[2])).all()  # fmt: skip
    assert (row.review_lane, row.review_reasons, row.review_dial) == ("review", ["gate"], "sample")
    assert row.gate["violations"][0]["code"] == "missing_ad"
    assert ("routed", None) in [tuple(k) for k in kinds]


def test_first_post_at(db: Database) -> None:
    refs = _items(db, 2)
    repo = ReviewRepo(db)
    assert repo.first_post_at(RT) is None
    SqlPostingRepo(db).set_posted(refs[1], Platform.TIKTOK, True, T, actor="telegram:1")
    assert repo.first_post_at(RT) == T
