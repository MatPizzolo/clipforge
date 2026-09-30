"""One behavior for every PostingRepo (spec §9.1): Dict, Sql and both Dual directions."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

import pytest

from clipforge.models import LEGACY_PLATFORMS, Platform, PostVerdict, RejectReason
from clipforge.pipeline.deps import MemoryKV
from clipforge.posting.repo import DictPostingRepo, PostingRepo
from tests.posting.builders import ACCOUNT, T0, item, send

PLATFORMS = list(LEGACY_PLATFORMS)
Factory = Callable[[pytest.FixtureRequest], PostingRepo]
FACTORIES: dict[str, Factory] = {"dict": lambda request: DictPostingRepo(MemoryKV(), ACCOUNT)}


def _sql(request: pytest.FixtureRequest) -> PostingRepo:
    from clipforge.db.posting import SqlPostingRepo
    from tests.dbhelpers import BILLY_SOURCE, make_account, seed

    db = request.getfixturevalue("db")
    seed(db, make_account(ACCOUNT), make_account("other-account"), sources=[BILLY_SOURCE])
    return SqlPostingRepo(db)


FACTORIES["sql"] = _sql


def _dual(primary: str) -> Factory:
    def build(request: pytest.FixtureRequest) -> PostingRepo:
        from clipforge.posting.repo import DualPostingRepo

        sql, dict_ = _sql(request), DictPostingRepo(MemoryKV(), ACCOUNT)
        return DualPostingRepo(sql, dict_) if primary == "sql" else DualPostingRepo(dict_, sql)

    return build


FACTORIES["dual-sql"] = _dual("sql")
FACTORIES["dual-dict"] = _dual("dict")


@pytest.fixture(params=sorted(FACTORIES))
def repo(request: pytest.FixtureRequest) -> PostingRepo:
    return FACTORIES[request.param](request)


def test_add_is_set_once_and_get_round_trips(repo: PostingRepo) -> None:
    it = item()
    assert repo.add(it, PLATFORMS) is True
    assert repo.add(it.model_copy(update={"score": 0.1}), PLATFORMS) is False  # first write wins
    assert repo.add_send(it.id, send(1), chat_id=7) is True
    assert repo.toggle_posted(it.id, Platform.TIKTOK, T0) is True
    rec = repo.get(it.id)
    assert rec is not None and rec.item == it and rec.platforms == PLATFORMS
    assert [s.n for s in rec.sends] == [1] and set(rec.posted) == {Platform.TIKTOK}
    assert repo.records(ACCOUNT) == [rec] and repo.records("other-account") == []
    assert repo.records_for_source(it.clip.source_hash) == [rec]  # type: ignore[union-attr]
    assert repo.records_for_source("b" * 64) == []
    assert repo.get(f"{it.clip.job_id}:clip_99") is None  # type: ignore[union-attr]


def test_toggle_and_set_posted(repo: PostingRepo) -> None:
    it = item()
    repo.add(it, PLATFORMS)
    assert repo.toggle_posted(it.id, Platform.YOUTUBE, T0) is True
    assert repo.toggle_posted(it.id, Platform.YOUTUBE, T0) is False
    repo.set_posted(it.id, Platform.INSTAGRAM, True, T0)
    repo.set_posted(it.id, Platform.INSTAGRAM, True, T0)  # idempotent
    rec = repo.get(it.id)
    assert rec is not None and set(rec.posted) == {Platform.INSTAGRAM}
    repo.set_posted(it.id, Platform.INSTAGRAM, False, T0)
    assert repo.get(it.id).posted == {}  # type: ignore[union-attr]


def test_sends_are_ordered_and_set_once(repo: PostingRepo) -> None:
    it = item()
    repo.add(it, PLATFORMS)
    assert repo.add_send(it.id, send(2, T0 + timedelta(days=1), message_id=200)) is True
    assert repo.add_send(it.id, send(1)) is True
    assert repo.add_send(it.id, send(1)) is False
    assert [s.n for s in repo.get(it.id).sends] == [1, 2]  # type: ignore[union-attr]


def test_verdict_reason_unavailable(repo: PostingRepo) -> None:
    it = item()
    repo.add(it, PLATFORMS)
    assert repo.set_reason(it.id, RejectReason.BORING) is False  # no rejection yet
    repo.set_verdict(it.id, PostVerdict(kind="skipped", at=T0))
    assert repo.set_reason(it.id, RejectReason.BORING) is False  # only rejections have reasons
    repo.set_verdict(it.id, PostVerdict(kind="rejected", at=T0))
    assert repo.set_reason(it.id, RejectReason.BAD_CUT) is True
    repo.mark_unavailable(it.id, T0)
    rec = repo.get(it.id)
    assert rec is not None and rec.unavailable
    assert rec.verdict == PostVerdict(kind="rejected", at=T0, reason=RejectReason.BAD_CUT)


def test_pause_is_per_account(repo: PostingRepo) -> None:
    assert repo.paused(ACCOUNT) is False
    repo.set_paused(ACCOUNT, True, T0)
    assert repo.paused(ACCOUNT) is True
    repo.set_paused(ACCOUNT, False, T0)
    assert repo.paused(ACCOUNT) is False
