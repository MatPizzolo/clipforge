from pathlib import Path

import pytest

from clipforge.db.engine import Database, DatabaseUnavailable
from clipforge.db.posting import SqlPostingRepo
from clipforge.pipeline.deps import MemoryKV
from clipforge.posting.backend import build_posting
from clipforge.posting.repo import DictPostingRepo, DualPostingRepo
from tests.bot.fakes import ALLOWED_USER, make_settings
from tests.dbhelpers import make_account, seed


def test_dict_mode_without_database_is_todays_single_account(tmp_path: Path) -> None:
    posting = build_posting(make_settings(tmp_path, posting_chat_id=ALLOWED_USER), MemoryKV(), None)
    assert isinstance(posting.repo, DictPostingRepo)
    [account] = posting.posting_accounts()
    assert account.id == "realtalk-clips-en" and account.posting.chat_id == ALLOWED_USER


def test_postgres_mode_without_database(tmp_path: Path) -> None:
    posting = build_posting(make_settings(tmp_path, state_reads="postgres"), MemoryKV(), None)
    assert posting.problem == "DATABASE_URL is not configured"
    assert posting.posting_accounts() == []
    with pytest.raises(DatabaseUnavailable):
        posting.repo.records("realtalk-clips-en")


def test_a_bad_state_reads_reads_the_dict_and_reports_the_problem(tmp_path: Path) -> None:
    settings = make_settings(tmp_path, posting_chat_id=ALLOWED_USER, state_reads="postgress")
    posting = build_posting(settings, MemoryKV(), None)
    assert isinstance(posting.repo, DictPostingRepo)
    assert posting.problem is not None and posting.problem.startswith("STATE_READS must be")
    assert posting.posting_accounts() == []  # nothing sends


def test_modes_with_database(tmp_path: Path, db: Database) -> None:
    seed(
        db,
        make_account(chat_id=ALLOWED_USER),
        make_account("founder-tapes-en", chat_id=ALLOWED_USER),
    )
    dict_mode = build_posting(make_settings(tmp_path), MemoryKV(), db)
    assert isinstance(dict_mode.repo, DualPostingRepo)
    assert isinstance(dict_mode.repo.primary, DictPostingRepo)
    assert [a.id for a in dict_mode.accounts()] == ["realtalk-clips-en"]  # env account only
    pg = build_posting(make_settings(tmp_path, state_reads="postgres"), MemoryKV(), db)
    assert isinstance(pg.repo, DualPostingRepo) and isinstance(pg.repo.primary, SqlPostingRepo)
    assert [a.id for a in pg.posting_accounts()] == ["founder-tapes-en", "realtalk-clips-en"]
    assert pg.requires_source is True
    bad = build_posting(make_settings(tmp_path, state_reads="postgress"), MemoryKV(), db)
    assert isinstance(bad.repo, DualPostingRepo) and isinstance(bad.repo.primary, DictPostingRepo)
    assert bad.problem is not None and bad.problem.startswith("STATE_READS must be")
