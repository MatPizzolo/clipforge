# Card 010: S1 — the rollout (Task 22), run with the owner

Status: proposed
Stream: S1 · Branch: `s1/rollout` · Worktree: `../clipForge-s1` (created with `scripts/worktree.sh s1/rollout`)
Decision-log range: #200–#249 (append only; #200–#218 are taken, re-read the log)
Model: most capable (a production change, done live with the owner)
Depends on: cards 002 and 006 deployed, and one clean night after that deploy (a `posting_daily` run at 07:00 UTC and one slot send); O5 collected by the owner (2026-10-01)
Cost cap: $1 (Modal runs of `posting_daily`, `db_doctor`, `doctor`; Neon stays on its free tier)

## Context
S1's code (Postgres for accounts, sources, the posting queue and job records; dual writes behind `STATE_READS`) was merged by card 002 and deployed with card 006. Production still reads from the Dict, with no database wired, because `DATABASE_URL` is out of `clipforge-secrets` (#107). This card moves production onto Postgres, step by step, with the owner running every command that writes or deploys.

Since the S1 plan was written:
- **The rollout creates only realtalk.clipsdaily** (log #135, ADR-48). founder.tapes and hombre.en.construccion are created just before S2.
- **Deploys go through `scripts/deploy.sh`** (blackout, CI green, `.env` settings, and the migration-head check once `DEPLOY_DB_CHECK=on`; card 008). Never a bare `modal deploy`.
- **CI deploys stay off** (`DEPLOY_ENABLED` unset), so the GitHub secret in the plan's Task 22 step 1 isn't needed.
- **The owner has O5**, Billy Garton Jr.'s permission facts. They type them into `clipforge source edit` themselves at step 4. Don't ask for them in chat, and don't write them into any file or report; the database is their only copy.

**The source of truth for the steps is runbook §4c** (`docs/studio/11-owner-runbook.md`). The S1 plan's Task 22 (`docs/superpowers/plans/2026-09-29-studio-s1.md`) supplies the checks and the evidence (its steps 9–12). Where the two differ, the runbook wins.

## Read first
1. `CLAUDE.md`, `STATUS.md`
2. Runbook §1 (the blackout), §4c (the rollout), §8 ("still left")
3. The S1 plan: its STATUS block, Task 22, and the card 002 amendments under Task 23
4. `docs/reports/002-s1-2026-09-30.md` (what was built), ADR-41, ADR-46, `docs/ops/secrets.md`

## Scope
- May edit, as `scripts/scopes.toml` allows for `s1/`: `src/`, `tests/`, `.env.example`, the S1 plan and spec, `docs/studio/03-tools-and-models.md` (the measurements, step 9 of the plan), `docs/studio/04-roadmap.md` and `ROADMAP.md` (the S1 tick), `docs/ARCHITECTURE.md`, `CLAUDE.md`.
- Must not edit: the runbook (tell the coordinator what's wrong in it), `web/`, other cards' files.
- **The session never runs a command that writes to production:** no deploy, no `alembic upgrade`, no `account create`, `source edit`, `posting import`, `jobs backfill`, no secret change. It gives the owner each command, waits for the output, and checks it. It may run read-only commands itself: `clipforge status`, `account list`, `source show`, `posting verify`, `modal app logs`, and, with the owner's OK, `modal run …::db_doctor` and `…::doctor`.

## Actions

### Checkpoint A: two small fixes before going live (code, on this branch)
1. **A manual rebuild during an outage:** `clipforge status --rebuild` (and `POST /posting/rebuild`) must respect the `posting:outage` flag, like `posting_daily` does (#217). It refuses with the outage line and how to clear it. Add a test that fails first.
2. **`DEPLOY_DB_CHECK` in `.env.example`**, with a comment (off until rollout step 2; card 008, #391).
3. `scripts/check.sh` green, report, stop. The owner merges this before step 1 below.

### Checkpoint B: the rollout, live, one step at a time
Before starting, confirm with the owner:
- it's outside a blackout, and there's at least an hour before the next slot;
- last night's deploy is healthy: `modal app logs clipforge` shows `posting_tick` lines without "posting is off", and one `posting_daily:` run.

Then walk runbook §4c's steps 1 → 6b in one sitting (step 2's deploy opens the mirror-alert window, which closes at step 5). After each step, check the result before giving the next command:

| Step | The owner runs | The session checks |
|---|---|---|
| 1 | `uv run alembic upgrade head` | Output ends at revision 0001 |
| 2 | Puts `DATABASE_URL` back in `clipforge-secrets` (dashboard edit), sets `DEPLOY_DB_CHECK=on` in `.env`, then `scripts/deploy.sh --dry-run` and `scripts/deploy.sh --reason "S1 rollout 4c.2: dual write"` | The dry run shows `database at the migration head: … 0001`; after the deploy, logs show the tick and no "posting is off" |
| 3 | `uv run clipforge account create --blueprint realtalk-clips --lang en --handle realtalk.clipsdaily --posting-from-env` | `account list`: one account, posting on, its slots and time zone as before |
| 4 | `source import-toml --account realtalk-clips-en --dry-run`, then for real; `source edit billy-garton …` with the O5 facts | `source show billy-garton`: no missing permission facts, platforms as expected. Never echo the evidence link |
| 5 | `posting import --dry-run`, then `posting import`, then `jobs backfill` | The dry run's counts per status match `clipforge status` |
| 6 | — | `posting verify` exits 0 with `"differences": 0` |
| 6b | Approves `modal run …::posting_daily`, then `…::db_doctor` | `ok: True` and `schedule_drift: []` |

**Stop and ask the owner** at the first surprise (a non-zero difference, an unexpected count, an error in the logs). The rollback is in the runbook: set `STATE_READS=dict` and redeploy. The Dict is still the primary until step 7, so nothing is lost before then.

Then step 7, which can be the same day or the next, outside a blackout: the owner sets `STATE_READS=postgres` in `clipforge-secrets` and `.env`, then runs `scripts/deploy.sh --dry-run` and `scripts/deploy.sh --reason "S1 rollout 4c.7: reads from Postgres" --rollout-step 4c.7`. The session checks `clipforge status` (it now reads from Postgres) and asks the owner to watch the next slot's send and one tap of each kind.

### Checkpoint C: evidence and close-out
1. The S1 plan's Task 22 step 9: measure and record in `docs/studio/03` a "Neon (S1, measured)" block (`clipforge status` timing after 10 idle minutes, three runs; `posting_tick` durations; storage used).
2. Step 10's evidence in the report: `account list`, `posting verify` at 0 differences, one real slot send and tap after `STATE_READS=postgres`.
3. Tick S1 in `docs/studio/04` and `ROADMAP.md`, except "ADR-24's keep-alive retires", which stays open for Task 23.
4. Update the S1 plan's STATUS block (Task 22 done; Task 23 after 7 clean days of `posting_daily: verify` at 0 differences), and log the rollout's rulings in your range.
5. List for the coordinator anything in runbook §4c that was wrong or missing.

## Checkpoints
- A: the two fixes. Suggested commit: `010: s1: rebuild respects the outage flag; DEPLOY_DB_CHECK in .env.example`
- B: the rollout through step 6b, then step 7 (the report records each step's output; no code changes)
- C: measurements, ticks, plan status. Suggested commit: `010: s1: rollout evidence, Neon measurements, S1 ticked`

## Done when
- `posting verify` reports 0 differences after step 7, and one real slot send and tap happened with `STATE_READS=postgres`.
- `scripts/check.sh` is green at A and C.
- The report has every step's output, with no secrets, URLs or permission details in it.

## Owner steps
- Before: deploy cards 002 + 006 (runbook §1; `scripts/deploy.sh`), wait one clean night, then `scripts/worktree.sh s1/rollout`, open a session in `../clipForge-s1`, paste `Run card docs/cards/010-s1-rollout.md`.
- At A: commit, `git push -u origin s1/rollout`, open the PR, and keep it open through C.
- At B: run each command the session gives you, outside a blackout, and paste back the output (redact nothing the session needs; it never asks for secrets).
- At C: commit, push, squash-merge when CI is green.

## Hand-off
Write `docs/reports/010-s1-<YYYY-MM-DD>.md` from `docs/templates/handoff-report.md` at each checkpoint. Don't commit: the owner does.
