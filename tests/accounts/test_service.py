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


# ---- S2 (card 014 Task 3): autopilot on create, the publisher, the publish path


def test_create_inserts_a_hands_on_row_with_the_creating_actor(
    db: Database, tmp_path: Path
) -> None:
    from clipforge.accounts.autopilot import AutopilotService

    kv = MemoryKV()
    create_account(AccountsRepo(db), make_settings(tmp_path), AccountCreate(
        blueprint="founder-tapes", language="en", handle="founder.tapes"), NOW, kv=kv,
        actor="cli:mat")  # fmt: skip
    svc = AutopilotService(db, AccountsRepo(db), kv)
    [first] = svc.history("founder-tapes-en")
    assert (first.field, first.to_value, first.actor) == ("preset", "hands_on", "cli:mat")
    assert svc.get("founder-tapes-en").updated_by == "cli:mat"
    assert read_schedules(kv)["founder-tapes-en"].publish_via == "assisted"


def test_create_with_an_odd_actor_records_system_accounts(db: Database, tmp_path: Path) -> None:
    from clipforge.db.autopilot import AutopilotRepo

    create_account(AccountsRepo(db), make_settings(tmp_path), AccountCreate(
        blueprint="founder-tapes", language="en", handle="founder.tapes"), NOW,
        actor="api")  # fmt: skip
    assert AutopilotRepo(db).history("founder-tapes-en")[0].actor == "system:accounts"


def test_edit_publisher_profile_rewrites_the_path_and_clear_disconnects(
    db: Database, tmp_path: Path
) -> None:
    from tests.accounts.helpers import make_account as stored_account

    kv, repo, settings = MemoryKV(), AccountsRepo(db), make_settings(tmp_path)
    stored_account(db)
    edited = edit_account(repo, settings, "realtalk-clips-en", AccountEdit(
        publisher_profile="realtalk-clips-en", facebook_page_id="123"), NOW, kv=kv)  # fmt: skip
    assert edited.publisher is not None and edited.publisher.facebook_page_id == "123"
    copy = read_schedules(kv)["realtalk-clips-en"]
    assert (copy.publish_via, copy.profile) == ("upload_post", "realtalk-clips-en")
    stored = repo.get("realtalk-clips-en")
    assert stored is not None and stored.publisher == edited.publisher
    edit_account(repo, settings, "realtalk-clips-en", AccountEdit(clear_publisher=True), NOW,
                 kv=kv)  # fmt: skip
    assert read_schedules(kv)["realtalk-clips-en"].publish_via == "assisted"


def test_publish_off_keeps_the_assisted_path_with_a_profile(db: Database, tmp_path: Path) -> None:
    from clipforge.accounts.autopilot import AutopilotService
    from tests.accounts.helpers import make_account as stored_account

    kv, repo, settings = MemoryKV(), AccountsRepo(db), make_settings(tmp_path)
    stored_account(db)
    AutopilotService(db, repo, kv).set("realtalk-clips-en", "publish", False, "cli:mat", None, NOW)
    edit_account(repo, settings, "realtalk-clips-en",
                 AccountEdit(publisher_profile="realtalk-clips-en"), NOW, kv=kv)  # fmt: skip
    assert read_schedules(kv)["realtalk-clips-en"].publish_via == "assisted"


@pytest.mark.parametrize("edit", [
    AccountEdit(facebook_page_id="123"),
    AccountEdit(clear_publisher=True, publisher_profile="x"),
])  # fmt: skip
def test_bad_publisher_edits(db: Database, tmp_path: Path, edit: AccountEdit) -> None:
    from tests.accounts.helpers import make_account as stored_account

    stored_account(db)
    with pytest.raises(AccountError):
        edit_account(AccountsRepo(db), make_settings(tmp_path), "realtalk-clips-en", edit, NOW)


def test_schedule_copy_without_a_publish_path_reads_assisted() -> None:
    kv = MemoryKV()
    kv.put("posting:schedule:realtalk-clips-en", make_account().posting.model_dump_json())
    copy = read_schedules(kv)["realtalk-clips-en"]
    assert (copy.publish_via, copy.profile) == ("assisted", None)


def test_s1_reader_still_validates_the_copy_after_a_rollback() -> None:
    # the publish path is its own key, so S1's PostingSchedule (extra=forbid) still reads the
    # schedule copy after a revert deploy (log #481)
    from clipforge.accounts.service import write_schedule_copy
    from clipforge.models import PostingSchedule

    kv = MemoryKV()
    write_schedule_copy(kv, make_account())
    PostingSchedule.model_validate_json(kv.get("posting:schedule:realtalk-clips-en") or "")


def test_drift_counts_a_missing_publish_path_only_when_it_reads_wrong(db: Database) -> None:
    # right after the S2a deploy no publish key exists yet: assisted is what it reads as, so
    # db_doctor stays clean; a connected profile without its key is drift
    from clipforge.accounts.service import schedule_drift, write_schedule_copy
    from clipforge.models import PublisherProfile
    from tests.dbhelpers import seed

    kv, repo = MemoryKV(), AccountsRepo(db)
    account = make_account(chat_id=ALLOWED_USER)
    seed(db, account)
    write_schedule_copy(kv, account)
    kv.delete("posting:publish:realtalk-clips-en")
    assert schedule_drift(repo, kv) == []
    repo.update(account.model_copy(update={"publisher": PublisherProfile(profile="rt")}), NOW)
    assert schedule_drift(repo, kv) == ["realtalk-clips-en"]
    sync_schedules(repo, kv)
    assert schedule_drift(repo, kv) == []
