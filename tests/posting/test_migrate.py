import json
from pathlib import Path

from clipforge.bot.context import BotContext
from clipforge.bot.posting import handle_callback
from clipforge.db.engine import Database
from clipforge.db.jobs import JobsRepo
from clipforge.db.posting import SqlPostingRepo
from clipforge.models import LEGACY_PLATFORMS, Platform, PostStatus, PostVerdict
from clipforge.pipeline.deps import MemoryKV
from clipforge.posting import migrate
from clipforge.posting.backend import build_posting
from clipforge.posting.repo import DictPostingRepo
from tests.bot.fakes import ALLOWED_USER, FakeSender, make_settings
from tests.dbhelpers import BILLY_SOURCE, make_account, seed
from tests.pipeline.harness import Harness
from tests.posting.builders import ACCOUNT, T0, item, send

P = list(LEGACY_PLATFORMS)


def _dict_with_three(kv: MemoryKV) -> DictPostingRepo:
    repo = DictPostingRepo(kv, ACCOUNT)
    a, b, c = item("clip_01"), item("clip_02", start=40, end=70), item("clip_03", start=80, end=110)
    for it in (a, b, c):
        repo.add(it, P)
    repo.add_send(a.id, send(1, message_id=100))
    repo.toggle_posted(a.id, Platform.TIKTOK, T0)
    repo.set_verdict(b.id, PostVerdict(kind="rejected", at=T0))
    kv.put("posting:paused", "1")
    return repo


def test_import_dry_run_then_real_then_rerun(tmp_path: Path, db: Database) -> None:
    seed(db, make_account(chat_id=ALLOWED_USER), sources=[BILLY_SOURCE])
    kv = MemoryKV()
    _dict_with_three(kv)
    dry = migrate.import_posting(kv, tmp_path, db, ACCOUNT, dry_run=True)
    assert dry.imported == 3 and SqlPostingRepo(db).records(ACCOUNT) == []
    real = migrate.import_posting(kv, tmp_path, db, ACCOUNT, dry_run=False)
    assert real.imported == 3 and real.paused is True
    assert real.by_status == {
        PostStatus.PARTLY_POSTED: 1,
        PostStatus.REJECTED: 1,
        PostStatus.QUEUED: 1,
    }
    again = migrate.import_posting(kv, tmp_path, db, ACCOUNT, dry_run=False)
    assert again.imported == 0 and again.already == 3
    assert migrate.verify_posting(kv, db, ACCOUNT).differences == 0
    rec = SqlPostingRepo(db).get(item("clip_01").id)
    assert rec is not None and rec.item.assets[0].license == "creator_agreement"


def test_import_fills_expired_keys_from_the_newest_snapshot(tmp_path: Path, db: Database) -> None:
    seed(db, make_account(), sources=[BILLY_SOURCE])
    kv = MemoryKV()
    _dict_with_three(kv)
    folder = tmp_path / "posting" / "snapshots"
    folder.mkdir(parents=True)
    (folder / "2026-09-28.json").write_text(json.dumps(dict(kv.items())))
    for key in [k for k in kv.keys() if k.startswith(f"post:{item('clip_03').id}")]:  # noqa: SIM118
        kv.delete(key)  # expired from the Dict
    report = migrate.import_posting(kv, tmp_path, db, ACCOUNT, dry_run=False)
    assert report.from_snapshot >= 1 and report.imported == 3


def test_missing_source_is_reported_not_imported(tmp_path: Path, db: Database) -> None:
    seed(db, make_account())  # no billy-garton row
    kv = MemoryKV()
    _dict_with_three(kv)
    report = migrate.import_posting(kv, tmp_path, db, ACCOUNT, dry_run=False)
    assert report.imported == 0 and len(report.missing_source) == 3


def test_verify_reports_a_planted_difference(tmp_path: Path, db: Database) -> None:
    seed(db, make_account(), sources=[BILLY_SOURCE])
    kv = MemoryKV()
    _dict_with_three(kv)
    migrate.import_posting(kv, tmp_path, db, ACCOUNT, dry_run=False)
    SqlPostingRepo(db).toggle_posted(item("clip_03").id, Platform.YOUTUBE, T0)
    report = migrate.verify_posting(kv, db, ACCOUNT)
    assert report.differences == 1 and "clip_03" in report.first[0]


def test_imported_item_accepts_old_buttons(tmp_path: Path, db: Database) -> None:
    seed(db, make_account(chat_id=ALLOWED_USER), sources=[BILLY_SOURCE])
    harness = Harness.build(tmp_path)
    _dict_with_three(harness.store.kv)  # type: ignore[arg-type]
    migrate.import_posting(harness.store.kv, tmp_path, db, ACCOUNT, dry_run=False)
    settings = make_settings(tmp_path, state_reads="postgres")
    harness.deps.posting = build_posting(settings, harness.store.kv, db)
    ref = item("clip_01").id
    handle_callback(BotContext(settings, FakeSender(), harness.deps), "cb", f"p:ig:{ref}",
                    ALLOWED_USER, 100, T0)  # a message sent before the switch  # fmt: skip
    assert set(SqlPostingRepo(db).get(ref).posted) == {Platform.TIKTOK, Platform.INSTAGRAM}  # type: ignore[union-attr]


def test_backfill_from_metadata_and_dict(tmp_path: Path, db: Database) -> None:
    from tests.posting.builders import run_channel_job

    harness = Harness.build(tmp_path)
    done = run_channel_job(harness)  # writes metadata.json through the fake package stage
    running = harness.submit()  # Dict only, no metadata.json
    report = migrate.backfill_jobs(harness.store.kv, tmp_path, db, dry_run=False)  # type: ignore[arg-type]
    assert report.from_metadata == 1 and report.from_dict == 1 and report.written == 2
    assert JobsRepo(db).get(done).metadata_path is not None  # type: ignore[union-attr]
    assert JobsRepo(db).get(running) is not None
    assert migrate.backfill_jobs(harness.store.kv, tmp_path, db, dry_run=False).written == 0  # type: ignore[arg-type]


def test_verify_detects_both_directions_and_never_writes_the_dict(
    tmp_path: Path, db: Database
) -> None:
    seed(db, make_account(), sources=[BILLY_SOURCE])
    kv = MemoryKV()
    repo = _dict_with_three(kv)
    before = dict(kv.items())
    migrate.import_posting(kv, tmp_path, db, ACCOUNT, dry_run=False)
    assert dict(kv.items()) == before
    repo.add(item("clip_04", start=120, end=150), P)  # only in the Dict
    repo.set_verdict(item("clip_03").id, PostVerdict(kind="skipped", at=T0))  # status differs
    SqlPostingRepo(db).add(item("clip_05", start=200, end=230), P)  # only in Postgres
    report = migrate.verify_posting(kv, db, ACCOUNT)
    assert report.differences == 3
    assert any("only in the Dict" in x for x in report.first)
    assert any("only in Postgres" in x for x in report.first)


def test_import_preserves_marks_and_timestamps(tmp_path: Path, db: Database) -> None:
    seed(db, make_account(chat_id=ALLOWED_USER), sources=[BILLY_SOURCE])
    kv = MemoryKV()
    _dict_with_three(kv)
    migrate.import_posting(kv, tmp_path, db, ACCOUNT, dry_run=False)
    rec = SqlPostingRepo(db).get(item("clip_01").id)
    assert rec is not None and rec.posted == {Platform.TIKTOK: T0} and len(rec.sends) == 1
    assert rec.platforms == P
    assert SqlPostingRepo(db).paused(ACCOUNT)


def test_daily_verify_is_a_noop_without_a_database_and_never_raises() -> None:
    from clipforge.posting.keepalive import verify_daily

    kv = MemoryKV()
    assert verify_daily(kv, None, ACCOUNT) is None

    class Broken:
        def begin(self) -> None:
            raise RuntimeError("postgres://user:pw@host/db")

    assert verify_daily(kv, Broken(), ACCOUNT) is None  # type: ignore[arg-type]


def test_snapshot_does_not_revive_an_unticked_platform(tmp_path: Path, db: Database) -> None:
    seed(db, make_account(), sources=[BILLY_SOURCE])
    kv = MemoryKV()
    repo = _dict_with_three(kv)
    repo.set_posted(item("clip_01").id, Platform.YOUTUBE, True, T0)
    folder = tmp_path / "posting" / "snapshots"
    folder.mkdir(parents=True)
    (folder / "2026-09-28.json").write_text(json.dumps(dict(kv.items())))
    repo.set_posted(item("clip_01").id, Platform.YOUTUBE, False, T0)  # unticked after
    migrate.import_posting(kv, tmp_path, db, ACCOUNT, dry_run=False)
    rec = SqlPostingRepo(db).get(item("clip_01").id)
    assert rec is not None and Platform.YOUTUBE not in rec.posted
    assert Platform.TIKTOK in rec.posted


def test_invalid_dict_key_is_counted_as_failed(tmp_path: Path, db: Database) -> None:
    seed(db, make_account(), sources=[BILLY_SOURCE])
    kv = MemoryKV()
    _dict_with_three(kv)
    kv.put(f"post:{item('clip_01').id}:verdict", "not json")
    report = migrate.import_posting(kv, tmp_path, db, ACCOUNT, dry_run=True)
    assert report.failed == [f"post:{item('clip_01').id}:verdict"]


def test_verify_compares_posted_at_and_unavailable_and_paused(tmp_path: Path, db: Database) -> None:
    from datetime import timedelta

    seed(db, make_account(), sources=[BILLY_SOURCE])
    kv = MemoryKV()
    repo = _dict_with_three(kv)
    migrate.import_posting(kv, tmp_path, db, ACCOUNT, dry_run=False)
    assert migrate.verify_posting(kv, db, ACCOUNT).differences == 0
    a, b = item("clip_01").id, item("clip_02").id
    repo.set_posted(a, Platform.TIKTOK, True, T0 + timedelta(hours=1))  # only posted_at differs
    assert migrate.verify_posting(kv, db, ACCOUNT).differences == 1
    repo.set_posted(a, Platform.TIKTOK, True, T0)
    repo.mark_unavailable(b, T0)  # b is rejected, so the derived status stays rejected
    report = migrate.verify_posting(kv, db, ACCOUNT)
    assert report.differences == 1 and b in report.first[0]
    SqlPostingRepo(db).mark_unavailable(b, T0)
    SqlPostingRepo(db).set_paused(ACCOUNT, False, T0)
    report = migrate.verify_posting(kv, db, ACCOUNT)
    assert report.differences == 1 and report.first[0].startswith("paused")


def test_reason_and_unavailable_round_trip(tmp_path: Path, db: Database) -> None:
    from clipforge.models import RejectReason

    seed(db, make_account(), sources=[BILLY_SOURCE])
    kv = MemoryKV()
    repo = _dict_with_three(kv)
    repo.set_verdict(
        item("clip_02").id, PostVerdict(kind="rejected", at=T0, reason=RejectReason.BAD_CROP)
    )
    repo.mark_unavailable(item("clip_03").id, T0)
    migrate.import_posting(kv, tmp_path, db, ACCOUNT, dry_run=False)
    rec = SqlPostingRepo(db).get(item("clip_02").id)
    assert rec is not None and rec.verdict is not None
    assert rec.verdict.reason is RejectReason.BAD_CROP
    rec3 = SqlPostingRepo(db).get(item("clip_03").id)
    assert rec3 is not None and rec3.unavailable
    assert migrate.verify_posting(kv, db, ACCOUNT).differences == 0


def test_live_sub_keys_win_over_the_snapshot_when_the_base_key_expired(
    tmp_path: Path, db: Database
) -> None:
    from datetime import timedelta

    seed(db, make_account(), sources=[BILLY_SOURCE])
    kv = MemoryKV()
    repo = _dict_with_three(kv)
    ref = item("clip_01").id
    folder = tmp_path / "posting" / "snapshots"
    folder.mkdir(parents=True)
    (folder / "2026-09-28.json").write_text(json.dumps(dict(kv.items())))
    later = T0 + timedelta(hours=5)
    repo.set_posted(ref, Platform.TIKTOK, True, later)  # live value differs from the snapshot
    kv.delete(f"post:{ref}")  # the base key expired
    before = sum(1 for k, _ in kv.items() if k.startswith("post:"))
    report = migrate.import_posting(kv, tmp_path, db, ACCOUNT, dry_run=False)
    rec = SqlPostingRepo(db).get(ref)
    assert rec is not None and rec.posted[Platform.TIKTOK] == later
    assert len(rec.sends) == 1  # the snapshot's send came back
    assert report.imported == 3 and report.from_snapshot >= 1
    assert before == sum(1 for k, _ in kv.items() if k.startswith("post:"))  # Dict untouched


def test_verify_ignores_the_hook_stamp(db: Database) -> None:
    # ADR-50: the stamp lives in Postgres and metadata.json only; the Dict keeps the legacy
    # item, so a stamped item is the same in both stores until card 040 retires the Dict
    from clipforge.hooks.library import HookLibrary
    from clipforge.hooks.rotation import control_stamp
    from clipforge.hooks.seeds import seed as seed_hooks
    from clipforge.models import LEGACY_PLATFORMS
    from clipforge.posting.repo import DictPostingRepo

    seed(db, make_account(), sources=[BILLY_SOURCE])
    library = HookLibrary(db)
    seed_hooks(library, [ACCOUNT], T0)
    stamp = control_stamp(library.rotation_for(ACCOUNT, "clips"), "A title")
    stamped = item("clip_01").model_copy(update={"hook_stamp": stamp})
    kv = MemoryKV()
    DictPostingRepo(kv, ACCOUNT).add(stamped, list(LEGACY_PLATFORMS))
    SqlPostingRepo(db).add(stamped, list(LEGACY_PLATFORMS))
    assert migrate.verify_posting(kv, db, ACCOUNT).differences == 0
