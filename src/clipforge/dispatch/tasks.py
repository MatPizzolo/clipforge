"""The dispatcher (ADR-27, S2 spec §4.1): one cron, every 5 minutes, that runs each periodic
task when it is due. It replaced `posting_tick`; `sweeper` and `posting_daily` stay (3 crons).

Each tick:
1. folds the ops alerts held over quiet hours or the hourly cap (ADR-45), as `posting_tick` did;
2. keeps `posting_tick`'s guards: a misconfigured posting setup (`Posting.problem`) is off and
   alerts, and the outage flag (#217) stops everything until /go or a restore;
3. reads every `brake:*` key with `get` (activity against the Dict's 7-day expiry, ADR-24);
4. works out what is due from Dict state only (the schedule copies, the brakes, markers), so
   Postgres is opened only when a task is due and Neon still scales to zero between due times;
5. runs each due key, claimed set-if-absent as `dispatch:<task>:<key>` so overlapping ticks run
   it once; a run that raises releases its claim (the next tick retries) and alerts. A slow
   task is spawned (`dispatch_task`) and the tick moves on.

In S2a the registry holds one task, `assisted` (the posting assistant at each slot; paused by
the owner since 2026-10-05, ADR-54). Modal-free: `app.py` builds the context.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from clipforge.bot.context import BotContext
from clipforge.bot.posting import assisted_tick
from clipforge.config import Settings
from clipforge.db.engine import Database, redact
from clipforge.models import Brake, ScheduleCopy
from clipforge.ops import OpsAlerts
from clipforge.pipeline.deps import KV
from clipforge.posting import brake
from clipforge.posting.backend import Posting
from clipforge.posting.keepalive import outage_since
from clipforge.posting.slots import current_slot

log = logging.getLogger(__name__)

CLAIM_PREFIX = "dispatch:"
LAST_HANDOFF_KEY = "publish:last_handoff"  # written by publishing/state.py (S2b)


@dataclass(frozen=True)
class DispatchView:
    """What `due` may look at: Dict state only, read once per tick."""

    now: datetime
    schedules: dict[str, ScheduleCopy]
    brakes: list[Brake]
    outage: str | None
    problem: str | None
    last_handoff: datetime | None
    owner_zone: str

    def braked(self, account_id: str) -> bool:
        return any(b.on and b.scope in (brake.ALL, account_id) for b in self.brakes)


@dataclass
class DispatchCtx:
    settings: Settings
    kv: KV
    posting: Posting
    bot: BotContext | None  # None without a Telegram token: nothing is sent
    spawn: Callable[[str, str], None]
    ops: OpsAlerts | None = None
    db: Callable[[], Database | None] = lambda: None  # opened only by a due task (S2b)
    registry: list[Task] = field(default_factory=lambda: list(REGISTRY))


@dataclass(frozen=True)
class Task:
    """`due(view)` lists the keys to run now; `run(ctx, key, now)` returns a log line. `once=False`
    skips the dispatch claim for a task that keeps its own guards and must run on every tick
    while due (the assisted path: its slot claim and the #202 guard, so a failed send is
    retried at the next tick inside the slot window, as `posting_tick` did; log #489)."""

    name: str
    due: Callable[[DispatchView], list[str]]
    run: Callable[[DispatchCtx, str, datetime], str]
    budget_s: float
    spawn: bool = False
    once: bool = True


def tick(ctx: DispatchCtx, now: datetime) -> list[str]:
    """One cron tick; returns the log lines."""
    if ctx.ops is not None:
        ctx.ops.flush(now)  # ADR-45's fold, moved from posting_tick (ADR-27)
    # every brake key is read first, even while posting is off or in an outage, so no key can
    # expire into "go" (spec §6.7, ADR-24)
    brakes = brake.touch_all(ctx.kv)
    posting = ctx.posting
    if posting.problem is not None:  # kept from posting_tick: misconfigured = off, and say so
        log.warning("dispatch: posting is off: %s", posting.problem)
        if ctx.ops is not None:
            ctx.ops.alert(f"Posting is off: {posting.problem}", "posting", "problem", now=now)
        return [f"off: {posting.problem}"]
    since = outage_since(ctx.kv)
    if since is not None:  # kept from posting_tick (#217): nothing goes out until /go or restore
        return [f"outage since {since}: restore, check /status, then /go"]
    # the Dict copies in postgres mode; the env account (always assisted) in dict mode
    schedules = posting.all_schedules()
    if not schedules and posting.schedules is not None and ctx.ops is not None:
        # postgres mode with no schedule copy at all: nothing would ever send (A3, #203)
        ctx.ops.alert("Posting found no schedule copies (posting:schedule:*), so no account "
                      "will send. Run the daily sync, or edit an account, to rewrite them.",
                      "posting", "schedules", path="/accounts", now=now)  # fmt: skip
    view = DispatchView(now=now, schedules=schedules, brakes=brakes, outage=None, problem=None,
                        last_handoff=_last_handoff(ctx.kv),
                        owner_zone=ctx.settings.owner_zone())  # fmt: skip
    lines: list[str] = []
    for task in ctx.registry:
        for key in task.due(view):
            lines.append(_run_due(ctx, task, key, now))
    lines += _idle_accounts(view, lines)
    return lines or ["idle"]


def _run_due(ctx: DispatchCtx, task: Task, key: str, now: datetime) -> str:
    claim = f"{CLAIM_PREFIX}{task.name}:{key}"
    if task.once and not ctx.kv.put(claim, now.isoformat(), skip_if_exists=True):
        return f"{key}: done already"
    started = time.monotonic()
    try:
        if task.spawn:
            ctx.spawn(task.name, key)
            return f"{key}: spawned {task.name}"
        result = task.run(ctx, key, now)
    except Exception as exc:
        if task.once:
            ctx.kv.delete(claim)
        log.warning("dispatch: %s %s failed: %s", task.name, key, redact(exc))
        if ctx.ops is not None:
            ctx.ops.alert(f"Dispatcher task {task.name} failed: {redact(exc)}", "dispatch",
                          task.name, now=now)  # fmt: skip
        return f"{key}: error"
    took = time.monotonic() - started
    if took > task.budget_s:
        log.warning("dispatch: %s %s took %.1f s (budget %.0f s)", task.name, key, took,
                    task.budget_s)  # fmt: skip
    return f"{key}: {result}"


def _idle_accounts(view: DispatchView, lines: list[str]) -> list[str]:
    """One line per posting account that ran nothing this tick: braked, or no slot."""
    out = []
    for account_id, schedule in sorted(view.schedules.items()):
        if schedule.chat_id is None or any(line.startswith(f"{account_id}:") for line in lines):
            continue
        if view.braked(account_id):
            state = "braked"
        elif schedule.publish_via == "upload_post":
            # a connected profile with Publish on: nothing posts it until S2b registers its
            # phases (ADR-54: no assisted fallback)
            state = "upload_post, waiting for S2b's publishing"
        else:
            state = "no slot"
        out.append(f"{account_id}: {state}")
    return out


def run_spawned(ctx: DispatchCtx, name: str, key: str, now: datetime) -> str:
    """`dispatch_task(name, key)`: a spawned task's run. Its claim was taken by the tick; a
    failure releases it, so the next tick spawns it again."""
    task = next((t for t in ctx.registry if t.name == name), None)
    if task is None:
        return f"{name}: unknown task"
    try:
        return f"{name} {key}: {task.run(ctx, key, now)}"
    except Exception as exc:
        ctx.kv.delete(f"{CLAIM_PREFIX}{name}:{key}")
        if ctx.ops is not None:
            ctx.ops.alert(f"Dispatcher task {name} failed: {redact(exc)}", "dispatch", name,
                          now=now)  # fmt: skip
        raise


def _last_handoff(kv: KV) -> datetime | None:
    raw = kv.get(LAST_HANDOFF_KEY)
    try:
        return datetime.fromisoformat(raw) if raw else None
    except ValueError:
        return None


# ---- the assisted task (S2a): posting_tick's slot sends, for accounts on the assisted path


def _assisted_due(view: DispatchView) -> list[str]:
    keys = []
    for account_id, schedule in sorted(view.schedules.items()):
        if schedule.publish_via != "assisted" or schedule.chat_id is None:
            continue
        if view.braked(account_id):
            continue  # reported by _idle_accounts as "braked"
        slot = current_slot(schedule, view.now)
        if slot is not None:
            keys.append(f"{account_id}:{slot.isoformat()}")
    return keys


def _assisted_run(ctx: DispatchCtx, key: str, now: datetime) -> str:
    """`posting_tick`'s body for one account; it computes the slot again from `now`."""
    account_id = key.split(":", 1)[0]
    if ctx.bot is None:
        return "no Telegram token"
    lines = assisted_tick(ctx.bot, now, [account_id])  # reads the copies again: a slot is due
    return lines[0].split(": ", 1)[1] if lines else "no account"


ASSISTED = Task("assisted", _assisted_due, _assisted_run, budget_s=900, once=False)
REGISTRY: list[Task] = [ASSISTED]
