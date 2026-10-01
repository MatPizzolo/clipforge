# Card 002: S1 — finish the foundations (stop before the rollout)

Status: sent 2026-09-30 (PR #5)
Stream: S1 · Branch: `s1/finish` · Worktree: `../clipForge-s1`
Decision-log range: #200–#249
Model: mid-tier for implementing the plan; most capable for the final whole-branch review
Depends on: card 001 merged. Can run alongside cards 003 and 005.
Cost cap: $0 (no Modal runs, no deploys; `db_doctor` runs only at the rollout, with the owner)

## Context
S1 stopped cleanly at the 2026-09-30 pause (tag `pause-2026-09-30`), with 736 fast tests passing. Done: Tasks 1–20, fix card 1 (13b), the checkpoint D fixes, and addendum step A1 (ADR-43's derived `producer_version`, one sanitizer).
- Production is live and Dict-only (`STATE_READS=dict`).
- `DATABASE_URL` is **not** in the Modal secret until rollout step 4c.2 (#107).
- Accepted since the plan was written: ADR-43–46 (`docs/DECISIONS.md`).
- The coordinator's addendum items and their mapping to the plan's steps A2–A6 are in `STATUS.md` (addendum tracker).

## Read first
1. `CLAUDE.md`, `STATUS.md`, `docs/templates/checkpoint.md`
2. `docs/superpowers/plans/2026-09-29-studio-s1.md`: its STATUS block at the top and its addendum section, then its spec
3. `docs/studio/11-owner-runbook.md` §1 (the deploy blackout) and §4 (the rollout); `docs/studio/08-dashboard-and-operations.md` §2b (surfaces, notifications, deep links)

## Scope
- May edit: as `scripts/scopes.toml` allows for `s1/`.
- Must not edit: `web/`, the S3c docs, `docs/studio/08`.

## Actions
1. **A2 = Task 21a:**
   - mount `blueprints/` into the images;
   - a read-only `db_doctor` Modal function (connect ms, `alembic_version` equal to the code's expected revision, pooled host yes/no, no writes);
   - the database variables in `.env.example`;
   - `alembic/env.py` requires `DATABASE_URL_UNPOOLED` for DDL, with no silent fallback to the pooled URL.
2. **A3:**
   - a slot guard from sends: return "taken" if any record has a send for this slot, before `claim_slot`;
   - compute the slot before any database call, and read schedules from a Dict copy `posting:schedule:<account>` written only by the accounts service;
   - test that hashtags come from the account in postgres mode;
   - test that item platforms are frozen per item.
3. **A4:**
   - `src/clipforge/posting/actions.py` with `set_posted`, `skip`, `reject`, `set_reason`, `pause(account)`, `send_next(account)` and `redraw_all(ref)`. The webhook calls it.
   - An actor on every write: `telegram:<user id>`, or `web:<login>` from `X-Clipforge-Actor`.
   - On a database error, answer "store unavailable, nothing changed".
   - `SET LOCAL statement_timeout = '5s'` in `Database.begin`.
   - The actor goes into `post_events.data.actor` (omitted for system writes such as the tick's sends), with a test that reads it back: 0001 is frozen, and S3c's migration 0002 copies that key into a `post_events.actor` column (#251).
   - An optional `DASHBOARD_URL` setting, and URL buttons on bot messages with the link formats in 08 §2b. No button when the setting is unset.
4. **A5:**
   - The job view and the overview read the `jobs` table first.
   - Additive overview fields: `state`, `posted_total`, and per account `unanswered` and `last_sent_at`.
   - Keep the contract additive (#49), and regenerate `web/openapi.json` with `scripts/export_openapi.py` in the same checkpoint. `check.sh` fails otherwise.
5. **A6:**
   - `ops_alert(text, kind)` to the owner chat, deduped by a Dict claim, following ADR-45: quiet hours 23:00–08:00, one alert per (kind, subject) per hour, at most 20 an hour.
   - `posting_keepalive` becomes `posting_daily` (ADR-46).
6. **Task 21b:**
   - `db=database_from_settings` in `app.py`'s `build_deps`;
   - ADR-41 into `docs/DECISIONS.md`;
   - `ci.yml`: `alembic upgrade head` (secret `DATABASE_URL_UNPOOLED`) before `modal deploy`. Skip the deploy job when only `web/**` or docs changed, and keep the `DEPLOY_ENABLED` gate and X0's `check.sh` job.
   - The CI deploy job must apply the same blackout check as `scripts/deploy.sh` (reuse `scripts/deploy.py`'s `blackout_slot`, with the slots and timezone from repository variables), so turning on `DEPLOY_ENABLED` can't deploy inside a posting slot.
   - ARCHITECTURE (Postgres, `STATE_READS`, the per-account keys) and the `CLAUDE.md` commands.
7. **The final whole-branch review.** Fix the Critical and Important findings. List the deferred minors:
   - the per-account overview isn't isolated;
   - `posting_tick` builds its dependencies when posting is off;
   - `resume` records its row before the spawn;
   - the backfill dry run has no preview;
   - the rebuild test doesn't check the video path.
8. **STOP before Task 22** (the rollout). Remove nothing listed under Task 23. Write into the plan's Task 23 that `scripts/deploy.py` drops its `--rollout-step 4c.7` requirement once `STATE_READS=postgres` is permanent (an `x0/` change, since `scripts/` is X0's scope).

## Checkpoints
One per action (A–G). Each is a PR update. Suggested commits are `card 002: <action>`.

## Done when
- `scripts/check.sh` is green after every action (paste the summary).
- The scope check passes.
- The final review's Critical and Important findings are fixed, each with a test that failed first.

## Owner steps
- Before: `scripts/worktree.sh s1/finish`, then paste `Run card docs/cards/002-s1-finish.md` in a session opened in `../clipForge-s1`.
- At each checkpoint: `docs/templates/checkpoint.md`. Merge card 002 **before** cards 004 and 006.

## Hand-off
Reports go in `docs/reports/002-s1-<date>.md`. Don't commit. The owner's first push from the worktree is `git push -u origin <branch>`, then `gh pr create --fill`; PRs are squash-merged with the card number in the title.
