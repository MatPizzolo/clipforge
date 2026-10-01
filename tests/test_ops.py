"""Ops alerts (ADR-45, card 002 A6): dedupe, quiet hours, the hourly cap, folding, wiring."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from clipforge.ops import MAX_PER_HOUR, OpsAlerts, ops_alerts, owner_chat
from clipforge.pipeline.deps import MemoryKV, NullVolume, QueueSpawner
from clipforge.pipeline.steps import StageName, fail_job
from clipforge.posting.repo import DualPostingRepo
from clipforge.runtime import build_deps
from tests.bot.fakes import ALLOWED_USER, FakeSender, make_settings
from tests.pipeline.fakes import FakeStages
from tests.pipeline.harness import Harness

NY = ZoneInfo("America/New_York")
NOON = datetime(2026, 9, 30, 12, 0, tzinfo=NY)
NIGHT = datetime(2026, 9, 30, 23, 30, tzinfo=NY)
DASH = "https://dash.example"


def _ops(sender: FakeSender | None = None) -> tuple[OpsAlerts, FakeSender, MemoryKV]:
    sender = sender or FakeSender()
    kv = MemoryKV()
    return OpsAlerts(kv, sender, ALLOWED_USER, "America/New_York", DASH), sender, kv


def test_one_alert_per_kind_and_subject_per_hour() -> None:
    ops, sender, _ = _ops()
    assert ops.alert("job X failed", "job_failed", "X", path="/jobs/X", now=NOON) == "sent"
    assert ops.alert("job X failed", "job_failed", "X", now=NOON + timedelta(minutes=5)) == (
        "duplicate"
    )
    assert ops.alert("job Y failed", "job_failed", "Y", now=NOON) == "sent"
    assert ops.alert("job X failed", "job_failed", "X", now=NOON + timedelta(hours=1)) == "sent"
    assert len(sender.messages) == 3 and sender.messages[0][1] == "⚠️ job X failed"
    assert sender.keyboards[101] == [[("Open ↗", f"{DASH}/jobs/X")]]


def test_quiet_hours_hold_until_flush_and_urgent_breaks_through() -> None:
    ops, sender, kv = _ops()
    assert ops.alert("enqueue failed", "enqueue", "J1", now=NIGHT) == "held"
    assert ops.alert("tick failed", "tick", "acct", now=NIGHT) == "held"
    assert ops.alert("spend over 2x", "budget", "all", urgent=True, now=NIGHT) == "sent"
    assert ops.flush(NIGHT + timedelta(hours=2)) == 0  # 01:30, still quiet
    assert ops.flush(NIGHT + timedelta(hours=9)) == 2  # 08:30
    folded = sender.messages[-1][1]
    assert folded.startswith("⚠️ 2 alerts held") and "• enqueue failed" in folded
    assert ops.flush(NIGHT + timedelta(hours=9, minutes=5)) == 0  # nothing left
    assert not [k for k in kv.keys() if k.startswith("notify:held:")]  # noqa: SIM118


def test_over_the_hourly_cap_alerts_are_folded() -> None:
    ops, sender, _ = _ops()
    results = [ops.alert(f"job {n} failed", "job_failed", str(n), now=NOON) for n in range(25)]
    assert results.count("sent") == MAX_PER_HOUR and results.count("held") == 5
    assert ops.flush(NOON + timedelta(minutes=5)) == 5
    assert sender.messages[-1][1].startswith("⚠️ 5 alerts held")


def test_many_held_alerts_fold_into_n_more() -> None:
    ops, sender, _ = _ops()
    for n in range(8):
        ops.alert(f"job {n} failed", "job_failed", str(n), now=NIGHT)
    assert ops.flush(NOON + timedelta(days=1)) == 8
    assert sender.messages[-1][1].endswith("3 more → dashboard")


def test_an_alert_never_raises() -> None:
    ops, _, _ = _ops(FakeSender(fail=True))
    assert ops.alert("x", "k", now=NOON) == "error"
    assert ops.flush(NOON) == 0


def test_owner_chat_and_wiring(tmp_path: Path) -> None:
    assert owner_chat(make_settings(tmp_path)) == ALLOWED_USER  # the first allowed user
    assert owner_chat(make_settings(tmp_path, telegram_allowed_user_ids=[])) is None
    assert ops_alerts(MemoryKV(), None, make_settings(tmp_path)) is None  # no bot token
    ops = ops_alerts(MemoryKV(), FakeSender(), make_settings(tmp_path))
    assert ops is not None and ops.timezone == "America/New_York"
    owner = make_settings(tmp_path, owner_timezone="America/Argentina/Buenos_Aires")
    assert ops_alerts(MemoryKV(), FakeSender(), owner).timezone.endswith("Buenos_Aires")  # type: ignore[union-attr]
    assert make_settings(tmp_path, owner_timezone="Mars/Base").owner_timezone is None


def test_a_failed_job_without_a_notifier_alerts_the_owner(tmp_path: Path) -> None:
    harness = Harness.build(tmp_path)
    ops, sender, _ = _ops()
    harness.deps.ops = ops
    channel = harness.submit()  # no Telegram target, like `clipforge clip`
    fail_job(harness.deps, channel, StageName.INGEST, "boom", "no audio track")
    [(_, text, _)] = sender.messages
    assert text == f"⚠️ Job {channel} failed at ingest: no audio track\n/resume {channel}"
    fail_job(harness.deps, channel, StageName.INGEST, "boom", "again")  # notified once
    assert len(sender.messages) == 1


def test_a_queueing_failure_alerts_the_owner(tmp_path: Path) -> None:
    from tests.posting.builders import run_channel_job

    harness = Harness.build(tmp_path)
    ops, sender, _ = _ops()
    harness.deps.ops = ops
    assert harness.deps.posting is not None

    def broken(*args: object, **kwargs: object) -> bool:
        raise RuntimeError("dict down")

    harness.deps.posting.repo.add = broken  # type: ignore[method-assign]
    run_channel_job(harness)
    assert any("for posting failed" in text for _, text, _ in sender.messages)


def test_build_deps_alerts_on_mirror_failures(tmp_path: Path, db: object) -> None:
    from clipforge.db.engine import Database

    assert isinstance(db, Database)
    sender = FakeSender()
    deps = build_deps(make_settings(tmp_path), kv=MemoryKV(), volume=NullVolume(),
                      spawner=QueueSpawner(), stages=FakeStages(), sender=sender,
                      db=db)  # fmt: skip
    assert deps.ops is not None and deps.posting is not None
    repo = deps.posting.repo
    assert isinstance(repo, DualPostingRepo)
    repo._mirror("set_posted", lambda: (_ for _ in ()).throw(RuntimeError("neon asleep")))
    assert repo.mirror_failures == 1
    # sent or held depending on the wall clock; either way the alert was claimed once
    claims = [k for k in deps.store.kv.keys() if k.startswith("notify:mirror:set_posted:")]  # noqa: SIM118
    assert len(claims) == 1
