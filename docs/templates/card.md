# Card NNN: <stream> — <title>

Status: proposed | sent YYYY-MM-DD | done YYYY-MM-DD (report: docs/reports/NNN-…md) | superseded by NNN
Stream: S1 | S2 | S3 | S3a | S3c | S4+ | X1–X6 | X0 | coordinator
Branch: `<stream>/<topic>` · Worktree: `../clipForge-<stream>` (created with `scripts/worktree.sh <branch>`)
Decision-log range: #NNN–#NNN (append only, in this range)
Model: most capable (design, review) | mid-tier (implementing a written plan)
Depends on: cards NNN merged; owner steps …
Cost cap: $N of Modal/API spend (stop and ask before exceeding it)

## Context
What the session needs to know that isn't in the files below: the state it starts from, decisions made since the plan was written, and what other sessions are doing.

## Read first
1. `CLAUDE.md`, `STATUS.md`
2. …

## Scope
- May edit: … (must match `scripts/scopes.toml` for the branch prefix)
- Must not edit: …

## Actions
1. …
2. …
Stop for the owner at each checkpoint named below.

## Checkpoints
- A: after actions 1–2. Suggested commit: `…`
- B: …

## Done when
- `scripts/check.sh` is green (paste its summary lines).
- …

## Owner steps
- Before: …
- After: commit, push, open the PR (`gh pr create --fill`), merge when CI is green.

## Hand-off
Write `docs/reports/NNN-<stream>-<YYYY-MM-DD>.md` from `docs/templates/handoff-report.md` at every checkpoint and at the end. Don't commit: the owner does.
