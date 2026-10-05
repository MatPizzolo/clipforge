# Card 039: S1 follow-ups from the rollout

Status: proposed
Stream: S1 · Branch: `s1/followups` · Worktree: `../clipForge-s1` (created with `scripts/worktree.sh s1/followups` after card 010's worktree is removed)
Decision-log range: #200–#249 (append only; #200–#225 are taken, re-read the log)
Model: mid-tier
Depends on: card 010 done (checkpoint C merged). Runs **before** card 014 (S2a): it is small, and under log #144 it merges and deploys before 014 merges.
Cost cap: $0.10 (one smoke-free deploy check; no GPU)

## Context
Card 010's rollout (2026-10-05, report `docs/reports/010-s1-2026-10-05.md`, log #223–#225) found three problems in live S1 code:
1. **A bad setting takes down every container.** The secret held `STATE_READS=postgress`; `Settings` failed validation in every container for 5 minutes (21:45–21:50 UTC). The project rule (ARCHITECTURE, Posting queue → Settings) is that a posting setting mistake turns posting off with the reason in `/status`, never the app.
2. **`GET /posting` is slow:** 20–42 s in dict mode with the database connected and about 11 s on Postgres, because the overview makes many small reads (one source lookup per job summary, `service._account_view`). The CLI's 30 s timeout (`cli.py:412`) makes `clipforge status` fail about half the time.
3. **Telegram callbacks:** answers arrive too late after a cold start (Telegram shows the spinner, then "query is too old"), and `redraw_all` logs "message is not modified" errors.

## Read first
1. `CLAUDE.md`, `docs/ARCHITECTURE.md` (Posting queue, Posting assistant), `STATUS.md`
2. The card 010 report's follow-ups, log #223–#225
3. `src/clipforge/config.py` (`state_reads`, `posting_problem`), `src/clipforge/service.py` (`posting_overview`, `_account_view`), `src/clipforge/cli.py` (the status timeout), `src/clipforge/bot/` (callback handling, `posting/actions.redraw_all`)

## Scope
- May edit, as `scripts/scopes.toml` allows for `s1/`: `src/**`, `tests/**`, `.env.example`, `docs/ARCHITECTURE.md`, its own report, log rows in range.
- Must not edit: `alembic/` (no migration), other cards' docs.

## Actions
1. **A bad `STATE_READS` never crashes the app.** An unknown value turns posting off with a clear `posting_problem` ("STATE_READS must be dict or postgres, got …") and an ops alert, and every non-posting step (the job chain, the API, `/status`) keeps working. Choose and justify what reads use meanwhile (recommended: the Dict, which is still dual-written until S1 Task 23, so nothing is lost). Tests that fail first: a typo in `STATE_READS` builds `Settings`, sets the problem, and the tick sends nothing.
2. **`GET /posting` under 3 s on Postgres.** Batch the per-summary source lookups (one query for all sources the overview needs, or a dict built once per request) and check the other per-record reads the same way. A test counts queries for an overview of N jobs (a constant, not N). Measure before and after against production read-only (`clipforge status` timing) and put both numbers in the report.
3. **The CLI's status timeout** goes to 60 s with one retry on `ReadTimeout`, and prints "slow response, retrying" once.
4. **Telegram callbacks:** answer the callback query first (before any database or Volume work), so a cold start can't exceed Telegram's limit; treat "message is not modified" as success in `redraw_all` (no log line). Tests for both.
5. `scripts/check.sh` green, `pr-reviewer` (and `security-reviewer` for the bot change), the report, log rows in range, stop.

## Checkpoints
- A: actions 1–5. Suggested commit: `039: s1: bad STATE_READS turns posting off; fast posting overview; CLI retry; early callback answers`

## Owner steps
1. Before the deploy: the #144 check (`docs/ops/deploys.md`'s last row matches `git log`: no other code card waiting), then `scripts/deploy.sh --dry-run` and `scripts/deploy.sh --reason "039: S1 follow-ups"`, outside the blackout. If GitHub Actions is down again, use the same exception as log #224 only if `src/` is unchanged since the last green run; otherwise wait.
2. After the deploy: `time uv run clipforge status` (under 3 s), `/status` in Telegram, and `uv run modal app logs clipforge` for errors.
- Rollback: revert the merge and redeploy; nothing is migrated.

## Done when
- A typo in `STATE_READS` turns posting off with a reason and an alert; nothing else fails (test).
- `clipforge status` answers in under 3 s on Postgres (measured).
- Callback answers come first, and "not modified" is silent (tests).

## Hand-off
The report lists the before/after timings and anything left for S1 Task 23 (retiring the Dict writes after 7 clean verifies; a later card).
