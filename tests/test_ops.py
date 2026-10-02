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
    # pinned to noon: callers that pass no `now` (fail_job, enqueue) must not hit quiet hours
    ops = OpsAlerts(kv, sender, ALLOWED_USER, "America/New_York", DASH, clock=lambda: NOON)
    return ops, sender, kv


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
    assert make_settings(tmp_path, owner_timezone="Etc").owner_timezone is None  # a folder


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


def test_a_failed_send_does_not_use_up_the_hours_dedupe_key() -> None:
    # coordinator's A6 review: the claim is written only after Telegram accepted the message
    sender = FakeSender(fail_on={"send_message"})
    ops, _, kv = _ops(sender)
    assert ops.alert("job X failed", "job_failed", "X", now=NOON) == "error"
    assert not [k for k in kv.keys() if k.startswith("notify:job_failed:")]  # noqa: SIM118
    sender.fail_on = set()
    assert ops.alert("job X failed", "job_failed", "X", now=NOON) == "sent"
    assert ops.alert("job X failed", "job_failed", "X", now=NOON) == "duplicate"


def test_a_failed_flush_keeps_the_held_alerts_for_the_next_tick() -> None:
    ops, sender, kv = _ops()
    ops.alert("enqueue failed", "enqueue", "J1", now=NIGHT)
    sender.fail_on = {"send_message"}
    assert ops.flush(NOON + timedelta(days=1)) == 0  # Telegram down at 12:00
    assert kv.get("notify:pending") is not None
    sender.fail_on = set()
    assert ops.flush(NOON + timedelta(days=1, minutes=5)) == 1
    assert kv.get("notify:pending") is None


def test_a_database_error_in_a_step_never_reaches_the_job_error_or_the_alert(
    tmp_path: Path,
) -> None:
    # security review minor 1: clean() keeps hosts and user names; driver errors need redact()
    from sqlalchemy.exc import OperationalError

    harness = Harness.build(tmp_path)
    ops, sender, _ = _ops()
    harness.deps.ops = ops

    def down(*args: object, **kwargs: object) -> None:
        raise OperationalError("SELECT 1", {}, Exception(
            'connection to server at "ep-cool-1234-pooler.us-east-2.aws.neon.tech" '
            '(54.1.2.3), port 5432 failed: FATAL: password authentication failed for '
            'user "neondb_owner"'))  # fmt: skip

    harness.stages.ingest = down  # type: ignore[method-assign]
    job_id = harness.submit()
    harness.run()
    error = harness.store.get(job_id).error
    assert error is not None and error.error_type == "OperationalError"
    shown = [error.message, *(text for _, text, _ in sender.messages)]
    for secret in ("neon.tech", "ep-cool", "neondb_owner", "54.1.2.3"):
        assert all(secret not in text for text in shown), secret


def test_a_resumed_job_that_fails_again_in_the_same_hour_alerts_again(tmp_path: Path) -> None:
    # pipeline review I3: the `failed` claim already dedupes one failure; the hourly key must
    # not swallow the next one
    from collections import Counter

    from clipforge.pipeline.steps import resume

    stages = FakeStages(transient=Counter({"highlights": 99}))
    harness = Harness.build(tmp_path, stages)
    ops, sender, _ = _ops()
    harness.deps.ops = ops
    job_id = harness.submit()
    harness.run()
    resume(harness.deps, job_id)
    harness.run()
    failed = [t for _, t, _ in sender.messages if t.startswith(f"⚠️ Job {job_id} failed")]
    assert len(failed) == 2


def test_overlapping_flushes_send_the_held_alerts_once() -> None:
    # PR review 6: a second tick that starts while the first is sending must not send again
    ops, sender, kv = _ops()
    ops.alert("enqueue failed", "enqueue", "J1", now=NIGHT)
    other = OpsAlerts(kv, sender, ALLOWED_USER, "America/New_York", clock=lambda: NOON)
    morning = NOON + timedelta(days=1)
    inner: list[int] = []
    started: list[bool] = []
    real_send = sender.send_message

    def send_and_overlap(*args: object, **kwargs: object) -> int:
        if not started:
            started.append(True)
            inner.append(other.flush(morning))  # the overlapping tick
        return real_send(*args, **kwargs)  # type: ignore[arg-type]

    sender.send_message = send_and_overlap  # type: ignore[method-assign]
    assert ops.flush(morning) == 1
    assert inner == [0] and len(sender.messages) == 1
