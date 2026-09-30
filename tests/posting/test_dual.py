"""DualPostingRepo: write to both, read from one (ADR-41)."""

from __future__ import annotations

from clipforge.db.engine import Database
from clipforge.db.posting import SqlPostingRepo
from clipforge.models import LEGACY_PLATFORMS, Platform, PostVerdict
from clipforge.pipeline.deps import MemoryKV
from clipforge.posting.repo import DictPostingRepo, DualPostingRepo
from tests.dbhelpers import BILLY_SOURCE, make_account, seed
from tests.posting.builders import ACCOUNT, T0, item, send

P = list(LEGACY_PLATFORMS)


class Broken(DictPostingRepo):
    def add_send(self, ref: str, s: object, chat_id: int | None = None) -> bool:  # type: ignore[override]
        raise RuntimeError("mirror down")


def _both(db: Database) -> tuple[SqlPostingRepo, DictPostingRepo, DualPostingRepo]:
    seed(db, make_account(ACCOUNT), sources=[BILLY_SOURCE])
    sql, dict_ = SqlPostingRepo(db), DictPostingRepo(MemoryKV(), ACCOUNT)
    return sql, dict_, DualPostingRepo(sql, dict_)


def test_both_stores_end_in_the_same_state(db: Database) -> None:
    sql, dict_, dual = _both(db)
    it = item()
    dual.add(it, P)
    dual.add_send(it.id, send(1), chat_id=7)
    assert dual.toggle_posted(it.id, Platform.TIKTOK, T0) is True
    assert dual.toggle_posted(it.id, Platform.TIKTOK, T0) is False
    dual.toggle_posted(it.id, Platform.YOUTUBE, T0)
    dual.set_verdict(it.id, PostVerdict(kind="skipped", at=T0))
    assert sql.get(it.id) == dict_.get(it.id)


def test_mirror_failure_is_logged_not_raised(db: Database) -> None:
    seed(db, make_account(ACCOUNT), sources=[BILLY_SOURCE])
    dual = DualPostingRepo(SqlPostingRepo(db), Broken(MemoryKV(), ACCOUNT))
    it = item()
    dual.add(it, P)
    assert dual.add_send(it.id, send(1)) is True and dual.mirror_failures == 1


def test_primary_duplicate_is_not_mirrored(db: Database) -> None:
    _sql, dict_, dual = _both(db)
    it = item()
    dual.add(it, P)
    dual.add_send(it.id, send(1, message_id=100))
    assert dual.add_send(it.id, send(1, message_id=555)) is False
    assert [s.message_id for s in dict_.get(it.id).sends] == [100]  # type: ignore[union-attr]


def test_other_accounts_skip_the_dict_mirror(db: Database) -> None:
    seed(db, make_account(ACCOUNT), make_account("founder-tapes-en"), sources=[BILLY_SOURCE])
    sql, dict_ = SqlPostingRepo(db), DictPostingRepo(MemoryKV(), ACCOUNT)
    dual = DualPostingRepo(sql, dict_)
    it = item(account="founder-tapes-en")
    assert dual.add(it, P) is True and dual.mirror_failures == 0
    assert dict_.get(it.id) is None and sql.get(it.id) is not None


def test_unknown_ref_fk_error_on_sql_mirror_is_counted_not_raised(db: Database) -> None:
    seed(db, make_account(ACCOUNT), sources=[BILLY_SOURCE])
    dict_, sql = DictPostingRepo(MemoryKV(), ACCOUNT), SqlPostingRepo(db)
    dual = DualPostingRepo(dict_, sql)
    it = item()
    dict_.add(it, P)  # in the primary only, so the mirror has no such post
    dual.set_posted(it.id, Platform.TIKTOK, True, T0)
    assert dual.mirror_failures == 1
