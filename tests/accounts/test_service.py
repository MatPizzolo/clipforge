from pathlib import Path

import pytest

from clipforge.accounts.service import (
    AccountCreate,
    AccountEdit,
    AccountError,
    create_account,
    edit_account,
    env_account,
)  # fmt: skip
from clipforge.db.accounts import AccountsRepo
from clipforge.db.engine import Database
from clipforge.models import Platform
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
