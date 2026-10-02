# Card 013: X0 — the scope check during merges

Status: proposed
Stream: X0 (tooling) · Branch: `x0/merge-scope` · Worktree: `../clipForge-x0` (created with `scripts/worktree.sh x0/merge-scope`)
Decision-log range: #380–#399 (append only; #380–#394 are taken, re-read the log)
Model: mid-tier
Depends on: nothing. Runs alongside cards 010, 011 and 012
Cost cap: $0

## Context
During an uncommitted merge, `scripts/check_scope.py` compares the working tree with the old merge base and lists `main`'s incoming files as out of scope (seen in cards 008 and 006). It should notice the merge in progress and check only the branch's own files. (The time-zone check for `doctor`, first planned here, moved to card 010: it edits `src/`, which `x0/` branches may not touch, and a guardrail test enforces that.)

## Read first
1. `CLAUDE.md`, `STATUS.md`
2. `scripts/check_scope.py`, `tests/scripts/test_check_scope.py`, decision log #381, #386

## Scope
- May edit, as `scripts/scopes.toml` allows for `x0/`: `scripts/**`, `tests/scripts/**`.
- Must not edit: code under `src/`, `web/`, other docs.

## Actions
1. When a merge is in progress (`git rev-parse --git-path MERGE_HEAD` exists; worktrees included), print one line, "merge in progress: checking against the merge base of HEAD, MERGE_HEAD and origin/main", and compare the working tree with that merge base, so `main`'s incoming files don't count.
2. Tests in the throwaway-repo suite: a clean card branch with `main` merged in but not committed passes; an out-of-scope edit made during the merge still fails.
3. `scripts/check.sh` green, the report, a log row in range, stop.

## Checkpoints
- A: actions 1–3. Suggested commit: `013: x0: scope check aware of merges in progress`

## Done when
- The scope check passes during an uncommitted merge of `main` into a clean card branch, and still catches out-of-scope edits, each with a test.
- `scripts/check.sh` is green.

## Owner steps
- Before: `scripts/worktree.sh x0/merge-scope`, open a session in `../clipForge-x0`, paste `Run card docs/cards/013-x0-small-fixes.md`.
- After: commit, `git push -u origin x0/merge-scope`, open the PR, squash-merge when green.

## Hand-off
Write `docs/reports/013-x0-<YYYY-MM-DD>.md` from `docs/templates/handoff-report.md`. Don't commit: the owner does.
