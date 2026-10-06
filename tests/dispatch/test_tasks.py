"""The dispatcher (ADR-27, S2 spec §4.1; card 014 Task 7)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from clipforge.bot.context import BotContext
from clipforge.bot.posting import extras, post_html
from clipforge.config import Settings
from clipforge.dispatch.tasks import (
    CLAIM_PREFIX,
    DispatchCtx,
    DispatchView,
    Task,
    run_spawned,
    tick,
)
from clipforge.models import Brake, PostingSchedule, ScheduleCopy
from clipforge.ops import OpsAlerts
from clipforge.pipeline.deps import MemoryKV
from clipforge.posting import brake
from clipforge.posting.backend import Posting, build_posting
from clipforge.posting.keepalive import OUTAGE_KEY
from clipforge.posting.queue import pick_next
from clipforge.posting.repo import PostingClaims
from clipforge.posting.slots import current_slot
from tests.bot.fakes import ALLOWED_USER, FakeSender, make_settings
from tests.bot.helpers import dispatch_ctx
from tests.pipeline.harness import Harness
from tests.posting.builders import run_channel_job

NOW = datetime(2026, 10, 2, 12, 2, tzinfo=UTC)
RT = "realtalk-clips-en"


class Exploding:
    """Any attribute is a call that fails: the dispatcher must not touch Postgres."""

    def __getattr__(self, name: str) -> Any:
        def fail(*args: object, **kwargs: object) -> Any:
            raise AssertionError(f"the database was touched: {name}")

        return fail


def _ctx(
    tmp_path: Path, schedules: dict[str, ScheduleCopy] | None = None,
    registry: list[Task] | None = None,
) -> tuple[DispatchCtx, FakeSender]:  # fmt: skip
    kv = MemoryKV()
    found = schedules or {}
    posting = Posting(repo=Exploding(), claims=PostingClaims(kv), accounts=Exploding().list,  # type: ignore[arg-type]
                      source=Exploding().get, default_account_id=RT,
                      schedules=lambda: found)  # fmt: skip
    alerts = FakeSender()
    ops = OpsAlerts(kv, alerts, ALLOWED_USER, "UTC")
    settings = make_settings(tmp_path)
    ctx = DispatchCtx(settings=settings, kv=kv, posting=posting, bot=None,
                      spawn=lambda n, k: spawned.append((n, k)), ops=ops)  # fmt: skip
    spawned: list[tuple[str, str]] = []
    ctx.spawned = spawned  # type: ignore[attr-defined]
    if registry is not None:
        ctx.registry = registry
    return ctx, alerts


def _copy(slots: list[str], tz: str = "UTC", via: str = "assisted") -> ScheduleCopy:
    return ScheduleCopy.of(PostingSchedule(chat_id=ALLOWED_USER, timezone=tz, slots=slots)
                           ).model_copy(update={"publish_via": via})  # fmt: skip


def test_nothing_due_never_opens_postgres(tmp_path: Path) -> None:
    ctx, _ = _ctx(tmp_path, {RT: _copy(["08:00"])})
    assert tick(ctx, NOW) == [f"{RT}: no slot"]


def test_a_due_key_runs_once_across_overlapping_ticks(tmp_path: Path) -> None:
    runs: list[str] = []
    task = Task("t", lambda v: ["k"], lambda c, k, n: runs.append(k) or "ok", budget_s=5)
    ctx, _ = _ctx(tmp_path, registry=[task])
    assert tick(ctx, NOW) == ["k: ok"]
    assert tick(ctx, NOW) == ["k: done already"]
    assert runs == ["k"] and ctx.kv.get(f"{CLAIM_PREFIX}t:k") is not None


def test_a_failed_task_releases_its_claim_and_alerts(tmp_path: Path) -> None:
    calls = {"n": 0}

    def boom(c: DispatchCtx, k: str, n: datetime) -> str:
        calls["n"] += 1
        raise RuntimeError("x")

    ctx, alerts = _ctx(tmp_path, registry=[Task("t", lambda v: ["k"], boom, budget_s=5)])
    assert tick(ctx, NOW) == ["k: error"]
    tick(ctx, NOW + timedelta(minutes=5))
    assert calls["n"] == 2
    assert "⚠️ Dispatcher task t failed: RuntimeError: x" in [t for _, t, _ in alerts.messages]


def test_the_alert_fold_runs_every_tick(tmp_path: Path) -> None:
    ctx, alerts = _ctx(tmp_path)
    ctx.kv.put("notify:held:2026-10-02T03:00:00+00:00:x:y", "held overnight")
    ctx.kv.put("notify:pending", "1")
    assert tick(ctx, NOW) == ["idle"]
    assert any("held overnight" in text for _, text, _ in alerts.messages)


def test_a_braked_account_is_skipped(tmp_path: Path) -> None:
    ctx, _ = _ctx(tmp_path, {RT: _copy(["12:00"])})
    brake.write(ctx.kv, Brake(scope="all", on=True, at=NOW, actor="telegram:1"))
    assert tick(ctx, NOW) == [f"{RT}: braked"]


def test_every_brake_key_is_read_every_tick(tmp_path: Path) -> None:
    ctx, _ = _ctx(tmp_path)
    brake.write(ctx.kv, Brake(scope=RT, on=False, at=NOW, actor="telegram:1"))
    reads: list[str] = []
    real = ctx.kv.get
    ctx.kv.get = lambda key: reads.append(key) or real(key)  # type: ignore[method-assign]
    tick(ctx, NOW)
    assert f"brake:{RT}" in reads


def test_a_spawned_task_runs_through_spawn(tmp_path: Path) -> None:
    task = Task("slow", lambda v: ["k"], lambda c, k, n: "ok", budget_s=5, spawn=True)
    ctx, _ = _ctx(tmp_path, registry=[task])
    assert tick(ctx, NOW) == ["k: spawned slow"]
    assert ctx.spawned == [("slow", "k")]  # type: ignore[attr-defined]
    assert run_spawned(ctx, "slow", "k", NOW) == "slow k: ok"


def test_a_failed_spawned_run_releases_its_claim(tmp_path: Path) -> None:
    def boom(c: DispatchCtx, k: str, n: datetime) -> str:
        raise RuntimeError("x")

    task = Task("slow", lambda v: ["k"], boom, budget_s=5, spawn=True)
    ctx, _ = _ctx(tmp_path, registry=[task])
    tick(ctx, NOW)
    with pytest.raises(RuntimeError):
        run_spawned(ctx, "slow", "k", NOW)
    assert ctx.kv.get(f"{CLAIM_PREFIX}slow:k") is None


def test_the_view_holds_dict_state_only(tmp_path: Path) -> None:
    seen: list[DispatchView] = []
    task = Task("t", lambda v: seen.append(v) or [], lambda c, k, n: "", budget_s=5)
    ctx, _ = _ctx(tmp_path, {RT: _copy(["08:00"])}, registry=[task])
    ctx.kv.put("publish:last_handoff", "2026-10-02T11:30:00+00:00")
    tick(ctx, NOW)
    [view] = seen
    assert view.last_handoff == datetime(2026, 10, 2, 11, 30, tzinfo=UTC)
    assert set(view.schedules) == {RT} and view.owner_zone == ctx.settings.owner_zone()


# ---- posting_tick's behavior, kept (log #461)

NY = ZoneInfo("America/New_York")
AT_8 = datetime(2026, 9, 29, 8, 1, tzinfo=NY)


def _dict_only(harness: Harness) -> BotContext:
    """Production before S1's rollout: no DATABASE_URL, STATE_READS=dict, the env account from
    the POSTING_* settings, built with build_posting(settings, kv, None) as posting_tick was."""
    run_channel_job(harness)
    settings = make_settings(harness.root, posting_chat_id=ALLOWED_USER, posting_slots="08:00")
    harness.deps.posting = build_posting(settings, harness.deps.store.kv, None)
    return BotContext(settings, FakeSender(), harness.deps)


def test_no_database_sends_the_env_accounts_slot_like_posting_tick(harness: Harness) -> None:
    ctx = _dict_only(harness)
    posting = ctx.deps.posting
    assert posting is not None
    records = posting.repo.records(RT)
    best = pick_next(records, AT_8)
    assert best is not None
    account = posting.account(RT)
    assert account is not None
    tags, links = extras(account, None, best.item)
    schedule = posting.all_schedules()[RT]
    slot = current_slot(schedule, AT_8)
    assert slot is not None
    lines = tick(dispatch_ctx(ctx), AT_8)
    assert lines == [f"{RT}:{slot.isoformat()}: sent {best.item.id}"]
    sender = ctx.sender
    assert isinstance(sender, FakeSender)
    # the oracle: the same clip and text posting_tick sent (S1's tick tests)
    [(chat, text, _)] = sender.messages
    assert chat == ALLOWED_USER and text == post_html(best.item, tags, best.platforms, links)
    assert len(sender.videos) == 1
    assert tick(dispatch_ctx(ctx), AT_8 + timedelta(minutes=5)) == [
        f"{RT}:{slot.isoformat()}: taken"]  # fmt: skip


def test_a_posting_problem_alerts_and_sends_nothing(harness: Harness) -> None:
    run_channel_job(harness)
    settings = make_settings(harness.root, posting_chat_id=ALLOWED_USER, posting_slots="9am")
    assert settings.posting_problem is not None
    harness.deps.posting = build_posting(settings, harness.deps.store.kv, None)
    harness.deps.posting.problem = settings.posting_problem
    alerts = FakeSender()
    harness.deps.ops = OpsAlerts(harness.deps.store.kv, alerts, ALLOWED_USER, "UTC")
    ctx = BotContext(settings, FakeSender(), harness.deps)
    assert tick(dispatch_ctx(ctx), AT_8) == [f"off: {settings.posting_problem}"]
    assert alerts.messages[-1][1] == f"⚠️ Posting is off: {settings.posting_problem}"


def test_postgres_mode_without_a_database_is_off_and_alerts(tmp_path: Path) -> None:
    deps = Harness.build(tmp_path).deps
    settings = make_settings(tmp_path, state_reads="postgres")
    deps.posting = build_posting(settings, deps.store.kv, None)
    alerts = FakeSender()
    deps.ops = OpsAlerts(deps.store.kv, alerts, ALLOWED_USER, "UTC")
    lines = tick(dispatch_ctx(BotContext(settings, FakeSender(), deps)), AT_8)
    assert lines == ["off: DATABASE_URL is not configured"]
    assert alerts.messages[-1][1] == "⚠️ Posting is off: DATABASE_URL is not configured"


def test_an_outage_sends_nothing(harness: Harness) -> None:
    ctx = _dict_only(harness)
    ctx.deps.store.kv.put(OUTAGE_KEY, "2026-09-25")
    assert tick(dispatch_ctx(ctx), AT_8)[0].startswith("outage since 2026-09-25")
    assert isinstance(ctx.sender, FakeSender) and ctx.sender.videos == []


def test_without_a_telegram_token_nothing_is_sent(harness: Harness) -> None:
    ctx = dispatch_ctx(_dict_only(harness))
    ctx.bot = None
    assert tick(ctx, AT_8)[0].endswith(": no Telegram token")


def test_settings_owner_zone_reaches_the_view(tmp_path: Path) -> None:
    s = Settings(_env_file=None, owner_timezone="Europe/Madrid")
    assert s.owner_zone() == "Europe/Madrid"


def test_brake_keys_are_read_during_an_outage_and_a_problem(tmp_path: Path) -> None:
    # spec §6.7: a key must never expire into "go", so every tick reads them first
    ctx, _ = _ctx(tmp_path)
    brake.write(ctx.kv, Brake(scope=RT, on=True, at=NOW, actor="telegram:1"))
    reads: list[str] = []
    real = ctx.kv.get
    ctx.kv.get = lambda key: reads.append(key) or real(key)  # type: ignore[method-assign]
    ctx.kv.put(OUTAGE_KEY, "2026-09-25")
    assert tick(ctx, NOW)[0].startswith("outage since")
    assert f"brake:{RT}" in reads
    reads.clear()
    ctx.posting.problem = "POSTING_SLOTS is invalid"
    assert tick(ctx, NOW) == ["off: POSTING_SLOTS is invalid"]
    assert f"brake:{RT}" in reads


def test_an_upload_post_account_says_it_waits_for_s2b(tmp_path: Path) -> None:
    ctx, _ = _ctx(tmp_path, {RT: _copy(["12:00"], via="upload_post")})
    assert tick(ctx, NOW) == [f"{RT}: upload_post, waiting for S2b's publishing"]
