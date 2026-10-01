from pathlib import Path

import pytest

from clipforge.accounts.service import (
    AccountCreate,
    AccountEdit,
    AccountError,
    create_account,
    edit_account,
    env_account,
    read_schedules,
    sync_schedules,
)  # fmt: skip
from clipforge.db.accounts import AccountsRepo
from clipforge.db.engine import Database
from clipforge.models import Platform
from clipforge.pipeline.deps import MemoryKV
from tests.bot.fakes import ALLOWED_USER, make_settings
from tests.dbhelpers import NOW, make_account


def test_create_from_blueprint_sets_handles_and_starts_in_review(
    db: Database, tmp_path: Path
) -> None:
    repo = AccountsRepo(db)
    settings = make_settings(tmp_path)
    account = create_account(
        repo,
        settings,
        AccountCreate(
            blueprint="hombre-en-construccion", language="es", handle="hombre.en.construccion"
        ),
        NOW,
    )
    assert account.id == "hombre-en-construccion-es" and account.review_tier == "review"
    assert {p for p, prof in account.platforms.items() if prof.enabled} == set(Platform)
    assert all(prof.handle == "hombre.en.construccion" for prof in account.platforms.values())
    assert account.posting.chat_id is None  # posting off until edited
    with pytest.raises(AccountError, match="language"):
        create_account(repo, settings, AccountCreate(
            blueprint="founder-tapes", language="es", handle="x"), NOW)  # fmt: skip


def test_posting_from_env_seeds_account_one(db: Database, tmp_path: Path) -> None:
    settings = make_settings(tmp_path, posting_chat_id=ALLOWED_USER, posting_slots="8:00,13:00",
                             posting_hashtags="#mindset")  # fmt: skip
    account = create_account(AccountsRepo(db), settings, AccountCreate(
        blueprint="realtalk-clips", language="en", handle="realtalk.clipsdaily",
        posting_from_env=True), NOW)  # fmt: skip
    assert account.posting.chat_id == ALLOWED_USER and account.posting.slots == ["08:00", "13:00"]
    assert account.posting.hashtags == ["mindset"]
    assert env_account(settings).posting == account.posting


def test_edit_renames_and_normalizes(db: Database, tmp_path: Path) -> None:
    repo, settings = AccountsRepo(db), make_settings(tmp_path)
    create_account(repo, settings, AccountCreate(blueprint="founder-tapes", language="en",
                                                 handle="founder.tapes"), NOW)  # fmt: skip
    edited = edit_account(repo, settings, "founder-tapes-en", AccountEdit(
        handles={Platform.TIKTOK: "founder.tapes2"}, chat_id=ALLOWED_USER, slots=["9:00"],
        hashtags=["#biz"]), NOW)  # fmt: skip
    assert edited.platforms[Platform.TIKTOK].handle == "founder.tapes2"
    assert edited.posting.slots == ["09:00"] and edited.posting.hashtags == ["biz"]
    assert repo.get("founder-tapes-en") == edited


def test_edit_rejects_bad_schedule_and_keeps_old(db: Database, tmp_path: Path) -> None:
    repo, settings = AccountsRepo(db), make_settings(tmp_path)
    before = create_account(repo, settings, AccountCreate(blueprint="founder-tapes", language="en",
                                                          handle="founder.tapes"), NOW)  # fmt: skip
    for edit, match in [
        (AccountEdit(chat_id=999), "TELEGRAM_ALLOWED_USER_IDS"),
        (AccountEdit(timezone="Mars/Base"), "time zone"),
        (AccountEdit(slots=["9:5"]), "HH:MM"),
    ]:
        with pytest.raises(AccountError, match=match):
            edit_account(repo, settings, before.id, edit, NOW)
    assert repo.get(before.id) == before
    repo.create(make_account("tiktok-only-en", platforms=[Platform.TIKTOK]), NOW)
    with pytest.raises(AccountError, match="not enabled"):
        edit_account(repo, settings, "tiktok-only-en",
                     AccountEdit(handles={Platform.INSTAGRAM: "x"}), NOW)  # fmt: skip
    with pytest.raises(AccountError, match="no account"):
        edit_account(repo, settings, "nope", AccountEdit(), NOW)


def test_edit_chat_needs_slots(db: Database, tmp_path: Path) -> None:
    repo, settings = AccountsRepo(db), make_settings(tmp_path)
    before = create_account(
        repo,
        settings,
        AccountCreate(blueprint="founder-tapes", language="en", handle="founder.tapes"),
        NOW,
    )
    with pytest.raises(AccountError, match="slots"):
        edit_account(repo, settings, before.id, AccountEdit(chat_id=ALLOWED_USER), NOW)
    assert repo.get(before.id) == before
    edited = edit_account(
        repo, settings, before.id, AccountEdit(chat_id=ALLOWED_USER, slots=["9:00"]), NOW
    )
    assert edited.posting.chat_id == ALLOWED_USER and edited.posting.slots == ["09:00"]


def test_create_and_edit_write_the_schedule_copy(db: Database, tmp_path: Path) -> None:
    # card 002 A3: the tick reads schedules from the Dict; only this service writes them
    repo, settings, kv = AccountsRepo(db), make_settings(tmp_path), MemoryKV()
    create_account(repo, settings, AccountCreate(blueprint="founder-tapes", language="en",
                                                 handle="founder.tapes"), NOW, kv=kv)  # fmt: skip
    assert read_schedules(kv)["founder-tapes-en"].chat_id is None
    edit_account(repo, settings, "founder-tapes-en",
                 AccountEdit(chat_id=ALLOWED_USER, slots=["9:00"]), NOW, kv=kv)  # fmt: skip
    copy = read_schedules(kv)["founder-tapes-en"]
    assert copy.chat_id == ALLOWED_USER and copy.slots == ["09:00"]
    with pytest.raises(AccountError):  # a refused edit leaves the copy alone
        edit_account(repo, settings, "founder-tapes-en", AccountEdit(timezone="Mars/Base"),
                     NOW, kv=kv)  # fmt: skip
    assert read_schedules(kv)["founder-tapes-en"] == copy


def test_sync_rewrites_lost_copies_and_drops_stray_ones(db: Database) -> None:
    repo, kv = AccountsRepo(db), MemoryKV()
    repo.create(make_account(chat_id=ALLOWED_USER), NOW)
    kv.put("posting:schedule:gone-account", make_account().posting.model_dump_json())
    kv.put("posting:schedule:broken", "{not json")
    assert sync_schedules(repo, kv) == 1
    assert set(read_schedules(kv)) == {"realtalk-clips-en"}


def test_schedule_drift_names_posting_accounts_without_a_current_copy(db: Database) -> None:
    from clipforge.accounts.service import publish_schedule, schedule_drift

    repo, kv = AccountsRepo(db), MemoryKV()
    posting = make_account(chat_id=ALLOWED_USER)
    repo.create(posting, NOW)
    repo.create(make_account("founder-tapes-en"), NOW)  # no chat: never drift
    assert schedule_drift(repo, kv) == ["realtalk-clips-en"]
    publish_schedule(kv, posting)
    assert schedule_drift(repo, kv) == []
    repo.update(posting.model_copy(update={"posting": posting.posting.model_copy(
        update={"slots": ["09:00"]})}), NOW)  # fmt: skip
    assert schedule_drift(repo, kv) == ["realtalk-clips-en"]
    sync_schedules(repo, kv)
    assert schedule_drift(repo, kv) == []
