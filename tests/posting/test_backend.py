from pathlib import Path

import pytest

from clipforge.db.engine import Database, DatabaseUnavailable
from clipforge.db.posting import SqlPostingRepo
from clipforge.pipeline.deps import MemoryKV
from clipforge.posting.backend import NO_DATABASE, build_posting
from tests.bot.fakes import ALLOWED_USER, make_settings
from tests.dbhelpers import make_account, seed


def test_without_a_database_posting_is_off(tmp_path: Path) -> None:
    posting = build_posting(make_settings(tmp_path), MemoryKV(), None)
    assert posting.problem == NO_DATABASE
    assert posting.posting_accounts() == []
    with pytest.raises(DatabaseUnavailable):
        posting.repo.records("realtalk-clips-en")


def test_leftover_posting_settings_never_make_an_env_account(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # card 040: the POSTING_* env account is gone; a key left in the secret posts nothing
    monkeypatch.setenv("POSTING_CHAT_ID", str(ALLOWED_USER))
    monkeypatch.setenv("STATE_READS", "dict")
    posting = build_posting(make_settings(tmp_path), MemoryKV(), None)
    assert posting.problem == NO_DATABASE and posting.posting_accounts() == []


def test_with_a_database_it_is_postgres_only(tmp_path: Path, db: Database) -> None:
    seed(
        db,
        make_account(chat_id=ALLOWED_USER),
        make_account("founder-tapes-en", chat_id=ALLOWED_USER),
    )
    posting = build_posting(make_settings(tmp_path), MemoryKV(), db)
    assert isinstance(posting.repo, SqlPostingRepo) and posting.problem is None
    assert [a.id for a in posting.posting_accounts()] == ["founder-tapes-en", "realtalk-clips-en"]
    assert posting.requires_source is True and posting.schedules is not None
