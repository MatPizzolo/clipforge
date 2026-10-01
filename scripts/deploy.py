"""The only production deploy path (card 001, decision log #382). Run through scripts/deploy.sh.

It refuses, with every reason, unless all of these hold:
- on `main`, the tree clean (except deploy lines already added to docs/ops/deploys.md) and equal
  to `origin/main`;
- the latest CI run for that commit is green;
- POSTING_SLOTS, POSTING_TIMEZONE and STATE_READS are set explicitly in `.env` (kept identical to
  the `clipforge-secrets` values; config.py's defaults are never used for these checks);
- now is outside the blackout: each posting slot until 30 minutes after it (decision log #108);
- STATE_READS is `dict`, unless the operator passes `--rollout-step 4c.7`.
Then: `modal deploy` with GIT_SHA, a `deploy-YYYYMMDD-HHMM` tag (UTC) pushed to origin, and a line
in docs/ops/deploys.md. `--dry-run` prints every check and deploys nothing.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DEPLOY_LOG = "docs/ops/deploys.md"
BLACKOUT = timedelta(minutes=30)
CI_WORKFLOW = "ci.yml"
ENV_KEYS = ("POSTING_SLOTS", "POSTING_TIMEZONE", "STATE_READS")


def _slots_on(day: date, slots: Sequence[str], zone: ZoneInfo) -> list[datetime]:
    out = []
    for text in slots:
        hour, minute = (int(part) for part in text.split(":"))
        out.append(datetime.combine(day, time(hour, minute), tzinfo=zone))
    return out


def blackout_slot(slots: Sequence[str], timezone: str, now: datetime) -> datetime | None:
    """The posting slot whose blackout (slot .. slot + 30 min, inclusive) contains `now`."""
    zone = ZoneInfo(timezone)
    today = now.astimezone(zone).date()
    for day in (today - timedelta(days=1), today):
        for slot in _slots_on(day, slots, zone):
            if slot <= now <= slot + BLACKOUT:
                return slot
    return None


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class Facts:
    """What the checks look at; gathered by `gather`, faked in tests."""

    branch: str
    dirty: list[str]
    head: str
    origin_main: str
    ci: str  # "success", "failure", "in_progress", "none", ...
    slots: list[str] | None  # None: missing or invalid in .env (see env_problems)
    timezone: str | None
    state_reads: str | None
    now: datetime
    env_problems: tuple[str, ...] = ()


@dataclass(frozen=True)
class EnvSettings:
    slots: list[str] | None
    timezone: str | None
    state_reads: str | None
    problems: tuple[str, ...]


def read_env_settings(path: Path) -> EnvSettings:
    """The three keys the checks need, from `.env` itself: no process env, no defaults."""
    from dotenv import dotenv_values

    from clipforge.schedule import normalize_slots, schedule_problem

    values = dotenv_values(path) if path.is_file() else {}
    problems = []
    raw = {key: (values.get(key) or "").strip() for key in ENV_KEYS}
    for key in ENV_KEYS:
        if not raw[key]:
            problems.append(
                f"{key}= is missing from .env (copy it from clipforge-secrets, identical)"
            )
    slots: list[str] | None = None
    timezone: str | None = None
    if raw["POSTING_SLOTS"] and raw["POSTING_TIMEZONE"]:
        parts = [s.strip() for s in raw["POSTING_SLOTS"].split(",") if s.strip()]
        candidate = normalize_slots(parts)
        problem = schedule_problem(raw["POSTING_TIMEZONE"], candidate, [])
        if problem is None:
            slots, timezone = candidate, raw["POSTING_TIMEZONE"]
        else:
            problems.append(f"POSTING_{problem[0].upper()} in .env: {problem[1]}")
    state_reads: str | None = None
    if raw["STATE_READS"]:
        if raw["STATE_READS"] in ("dict", "postgres"):
            state_reads = raw["STATE_READS"]
        else:
            problems.append(
                f"STATE_READS in .env must be dict or postgres, not {raw['STATE_READS']!r}"
            )
    return EnvSettings(slots, timezone, state_reads, tuple(problems))


def evaluate(facts: Facts, rollout_step: str | None) -> list[Check]:
    checks = [
        Check("branch", facts.branch == "main", f"on {facts.branch or '(detached)'}"),
        Check(
            "clean tree",
            not facts.dirty,
            "clean" if not facts.dirty else "uncommitted: " + ", ".join(facts.dirty[:5]),
        ),
        Check(
            "equal to origin/main",
            bool(facts.head) and facts.head == facts.origin_main,
            f"HEAD {facts.head[:7]}, origin/main {facts.origin_main[:7]}",
        ),
        Check("CI green", facts.ci == "success", f"latest {CI_WORKFLOW} run: {facts.ci}"),
        Check(
            ".env settings",
            not facts.env_problems,
            "; ".join(facts.env_problems) or ", ".join(ENV_KEYS) + " set",
        ),
    ]
    if facts.slots is None or facts.timezone is None:
        checks.append(
            Check(
                "outside the blackout", False, "unknown: needs POSTING_SLOTS and POSTING_TIMEZONE"
            )
        )
    else:
        slot = blackout_slot(facts.slots, facts.timezone, facts.now)
        local = facts.now.astimezone(ZoneInfo(facts.timezone)).strftime("%H:%M %Z")
        if slot is None:
            detail = f"now {local}; slots {','.join(facts.slots)} ({facts.timezone})"
        else:
            until = (slot + BLACKOUT).strftime("%H:%M")
            detail = f"now {local} is inside the {slot:%H:%M} slot's blackout (until {until})"
        checks.append(Check("outside the blackout", slot is None, detail))
    if facts.state_reads is None:
        checks.append(Check("STATE_READS", False, "unknown: not set in .env"))
    elif rollout_step == "4c.7":
        checks.append(Check("STATE_READS", True, f"{facts.state_reads} (rollout step 4c.7)"))
    else:
        checks.append(
            Check(
                "STATE_READS",
                facts.state_reads == "dict",
                f"{facts.state_reads} (only `dict` without --rollout-step 4c.7)",
            )
        )
    return checks


Runner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


def _run(cmd: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(cmd), cwd=ROOT, capture_output=True, text=True)


def _out(run: Runner, *cmd: str) -> str:
    result = run(cmd)
    return result.stdout.strip() if result.returncode == 0 else ""


def ci_conclusion(run: Runner, sha: str) -> str:
    if not sha:
        return "none"
    result = run(
        [
            "gh", "run", "list", "--commit", sha, "--workflow", CI_WORKFLOW, "--limit", "1",
            "--json", "status,conclusion", "--jq", ".[0] | [.status, .conclusion] | @tsv",
        ]
    )  # fmt: skip
    if result.returncode != 0:
        return "unknown (gh failed: is it installed and logged in?)"
    status, _, conclusion = result.stdout.strip().partition("\t")
    if not status:
        return "none"
    return conclusion if status == "completed" else status


def gather(run: Runner = _run) -> Facts:
    run(["git", "fetch", "--quiet", "origin", "main"])
    # Not _out: stripping would eat the first line's status column (" M path").
    porcelain = run(["git", "status", "--porcelain", "--untracked-files=normal"]).stdout
    dirty = [line[3:] for line in porcelain.splitlines() if line.strip() and line[3:] != DEPLOY_LOG]
    head = _out(run, "git", "rev-parse", "HEAD")
    env = read_env_settings(ROOT / ".env")
    return Facts(
        branch=_out(run, "git", "branch", "--show-current"),
        dirty=dirty,
        head=head,
        origin_main=_out(run, "git", "rev-parse", "origin/main"),
        ci=ci_conclusion(run, head),
        slots=env.slots,
        timezone=env.timezone,
        state_reads=env.state_reads,
        now=datetime.now(UTC),
        env_problems=env.problems,
    )


def log_line(now: datetime, sha: str, tag: str, who: str, reason: str) -> str:
    reason = reason.replace("|", "/").replace("\n", " ")
    return f"| {now:%Y-%m-%d %H:%M} | {sha[:7]} | {tag} | {who} | {reason} |\n"


def deploy(facts: Facts, reason: str, run: Runner = _run) -> int:
    sha = facts.head
    tag = f"deploy-{facts.now:%Y%m%d-%H%M}"
    env = {**os.environ, "GIT_SHA": sha}
    print(f"deploying {sha[:7]} (GIT_SHA set) ...", flush=True)
    result = subprocess.run(
        ["uv", "run", "modal", "deploy", "src/clipforge/app.py"], cwd=ROOT, env=env
    )
    if result.returncode != 0:
        print("modal deploy failed: no tag, no log line", file=sys.stderr)
        return result.returncode
    for cmd in (["git", "tag", tag, sha], ["git", "push", "origin", tag]):
        step = run(cmd)
        if step.returncode != 0:
            print(f"deployed, but `{' '.join(cmd)}` failed: {step.stderr.strip()}", file=sys.stderr)
    who = _out(run, "git", "config", "user.name") or os.environ.get("USER", "owner")
    with (ROOT / DEPLOY_LOG).open("a") as log:
        log.write(log_line(facts.now, sha, tag, who, reason))
    print(f"deployed {sha[:7]}, tagged {tag}, logged in {DEPLOY_LOG}")
    print(f"commit {DEPLOY_LOG} in the next coord/ PR (the next deploy ignores that file)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deploy the clipforge Modal app, with checks.")
    parser.add_argument("--dry-run", action="store_true", help="print the checks, deploy nothing")
    parser.add_argument("--reason", help="why (goes into docs/ops/deploys.md); required to deploy")
    parser.add_argument(
        "--rollout-step", choices=["4c.7"], help="allow STATE_READS other than dict (runbook 4c.7)"
    )
    args = parser.parse_args(argv)
    if not args.dry_run and not (args.reason or "").strip():
        parser.error("--reason is required (or use --dry-run)")

    os.chdir(ROOT)
    facts = gather()
    checks = evaluate(facts, args.rollout_step)
    for check in checks:
        print(f"{'ok  ' if check.ok else 'FAIL'} {check.name}: {check.detail}")
    failed = [c.name for c in checks if not c.ok]
    sys.stdout.flush()
    if failed:
        print(f"refused: {', '.join(failed)}", file=sys.stderr)
        return 1
    if args.dry_run:
        print(f"dry run: would deploy {facts.head[:7]} and tag deploy-{facts.now:%Y%m%d-%H%M}")
        return 0
    return deploy(facts, args.reason)


if __name__ == "__main__":
    raise SystemExit(main())
