# Card 014: S2a — rails: migration 0002, the dispatcher, the brake, autopilot, the gate and routing

Status: proposed · Updated 2026-10-05 (ADR-54; read the S2 plan's amendment note): Task 1 drops `Settings.review_batch`; Task 2's 0002 has no `review_messages` table and its `posts.state` value `fallback` is `final_failed`; the assisted flow is built unchanged but stays paused by the owner's `/pause`, so the one-day watch compares paused ticks, not sends
Stream: S2 (S2a) · Branch: `s2a/dispatch-gate` · Worktree: `../clipForge-s2a` (created with `scripts/worktree.sh s2a/dispatch-gate`)
Decision-log range: #480–#499 (append only, in this range)
Model: mid-tier (implementing a written plan); most capable for the migration and the dispatcher's cut-over from `posting_tick`
Depends on: card 010 fully done: step 7 (`STATE_READS=postgres`) verified, `clipforge posting verify` at 0 differences with Dual writes on, `db_doctor` showing a schedule copy for every account, and Neon's head at `0001` (no hooks or S3c migration landed first; if one did, see Action 2)
Cost cap: $0 of Modal/API spend (fast tests and the local Postgres only; no Upload-Post, no Modal runs). The owner's deploy and one-day watch are not session spend

## Context
S2 replaces the owner's hand posting with publishing through Upload-Post, reviewed where it pays off. Card 011 designed it (spec `docs/superpowers/specs/2026-10-01-studio-s2-design.md`, approved; plan `docs/superpowers/plans/2026-10-02-studio-s2.md`, 26 tasks; PR #27). The build is three cards, one per plan checkpoint (log #140): **this card is S2a (Tasks 1–8)**, then 015 (S2b, Tasks 9–20) and 016 (S2c, Tasks 21–26).

S2a lays the rails with **the assisted flow unchanged**: what the owner sees after the deploy is the same clips at the same slots, plus `/pause all` and `clipforge autopilot show`. Decisions since the plan was written:
- **ADR-27 (the dispatcher) and ADR-33 (tracking links) are accepted** (2026-10-02, log #138); they are in `docs/DECISIONS.md`.
- **The gate is log-only in S2a** behind `GATE_ENFORCE=off` (#461): it stamps violations and never holds or routes an item. `clipforge policy dry-run` (Task 8) is what the owner runs before turning it on in S2b.
- **The dispatcher builds its schedules from `Posting.all_schedules()`** and keeps `posting_tick`'s problem and outage handling (#461): with no `DATABASE_URL` the env account still posts, and `posting.problem` still alerts. A test pins it.
- **Migration 0002** is the first new migration, so it carries the S3 dashboard spec §8.7 deferred items: `jobs.error`, `post_events.actor` (backfilled from `data.actor`) and `posting_state.changed_by`/`reason`, plus the S2 tables (spec §3). Expand-only; `0001` is frozen. It takes the next number after the head on `main` and moves `EXPECTED_HEAD` in `db/doctor.py`. If the hooks card's or S3c's migration lands first, renumber, and drop any deferred item that migration already carries.
- **The Dict stays current until S1 Task 23** (spec §3.1): "posted" is always written through `PostingRepo.set_posted` (Dual), and `posting verify` must stay at 0.
- **Owner time zone:** planning and the digest run in `OWNER_TIMEZONE` (else `POSTING_TIMEZONE`) for every account (R3, #455); the planner itself is S2b's.

Other sessions: card 012 (X4) may still be running; cards 015 and 016 start only after this one is deployed. The hooks card and S3c's plan may write migrations too: migrations land one at a time, in landing order.

## Read first
1. `CLAUDE.md`, `STATUS.md`
2. The S2 plan: Global Constraints, Review Focus, File map, and Part S2a (Tasks 1–8, with the owner deploy steps and the rollback after Task 8)
3. The S2 spec: §0 and §0.1 (rulings), §1, §2 (contracts), §3 (migration 0002, §3.1 modes), §4 (the dispatcher), §5.1–§5.4 (gate, routing, review, autopilot), §6.7 (the brake), §8 (tests and safety)
4. `docs/DECISIONS.md`: ADR-14, ADR-24, ADR-26, ADR-27, ADR-29, ADR-41, ADR-45, ADR-46, ADR-48, ADR-49
5. Log rows #440–#461 and #138–#140 in `docs/studio/10-decision-log.md`
6. The code it changes: `alembic/versions/0001*`, `src/clipforge/db/` (`tables.py`, `doctor.py`, `posting.py`, `accounts.py`), `posting/actions.py`, `posting/daily.py`, `bot/posting.py`, `bot/commands.py`, `accounts/service.py`, `app.py`, `runtime.py`
7. `docs/ops/secrets.md`, runbook §1 (the blackout) and §6

## Scope
- May edit, as `scripts/scopes.toml` allows for `s2a/`: `src/**`, `tests/**`, `alembic/**`, `alembic.ini`, `.env.example`, `pyproject.toml`, `uv.lock`, `web/openapi.json`, `web/lib/api/**`, `web/lib/mocks.ts` and `web/tests/unit/summaries.test.ts` (only if an additive API field reaches those fixtures, as #132), `docs/ops/secrets.md`, `docs/ARCHITECTURE.md`, `docs/superpowers/plans/*-studio-s2*` (task ticks and a status line), `docs/studio/04-roadmap.md` and `ROADMAP.md` (S2a ticks), `CLAUDE.md` (Commands and Layout), its own report, and log rows #480–#499.
- Must not edit: the spec, the runbook, `STATUS.md`, other cards, `web/` beyond the files above, `prompts/`, stage modules (`src/clipforge/stages/`: S2 changes no stage).
- **No new dependencies.** **Only `app.py` imports `modal`.** **The session never deploys, migrates Neon, or changes a secret**: the owner does, from the commands below.

## Actions
Each task follows the plan: failing tests first, then the implementation sketch, then its checks, then "check and record" (`scripts/check.sh` green, the task noted in the report).
0. **Before Task 1: the wall-clock ordering fix** (card 017 report item 9, log #143; a test that fails first for each):
   - `db/jobs.py` `upsert`: a terminal status (`done`, `failed`) always replaces a non-terminal one (`queued`, `running`), whatever the `updated_at` order; log a warning when `record_job`'s upsert writes nothing. Regression test: the package flow with `steps.utcnow` shifted back 2 s.
   - `posting/queue.py` `status()` and `posting/actions.py`: a verdict answers the send it was made for. Either `actions` stamps `at = max(now, the record's latest send or verdict time)`, or the verdict records the send number it answers; pick one and say why. Regression test: a skip stamped 2 s before its send still counts as answered.
   - Remove the flaky-test comment from `tests/test_service.py` once both pass under a shifted clock.
1. **Task 1, contracts and settings:** the S2 contracts in `models.py` first (`PostCopy`, `Autopilot` and `hands_on`, `Routing`, `PublisherProfile`, `PublishState` with `retrying`, `Brake` with `on`, `Link`, `Click`), the settings in `config.py` (`GATE_ENFORCE` default `off`, `MEDIA_LINK_TTL_S` (no `REVIEW_BATCH`: ADR-54), `RECOVERY_WINDOW_S` default 0, `UPLOAD_POST_PROFILE_LIMIT`, `UPLOAD_POST_URL`, the two optional Upload-Post secrets; `owner_zone()`), and the `system:` actors in `posting/actions.py`.
2. **Task 2, migration 0002 and the tables:** `alembic/versions/0002_s2.py` (or the next number), `db/tables.py`, `EXPECTED_HEAD`, `db/posting.py` (`_event` writes the `actor` column; `PostRecord.publish`). The backfill of `post_events.actor` from `data.actor`; every existing account seeded Hands-on with actor `system:migration` (#451). The migration test runs upgrade and downgrade on a throwaway schema and checks an empty autogenerate.
3. **Task 3, the autopilot service and the schedule copy:** `db/autopilot.py`, `accounts/autopilot.py` (the one writer, with its append-only history), account create inserts the row, the schedule copy gains `publish_via` and `profile`, `AccountEdit` gains `publisher_profile`, `facebook_page_id`, `clear_publisher`. A missing autopilot row reads as Hands-on.
4. **Task 4, the brake:** `posting/brake.py` (`brake:<scope>`), `actions.pause(scope)` writes the Dict key first and `posting_state` second, `/pause all` and `/go all` in `bot/commands.py`, `/go <account>` under a fleet brake says "still braked", and the newer-wins repair in `posting_daily` (a missing key is never restored blindly).
5. **Task 5, the policy gate v1:** `policy/gate.py`, pure, with golden cases for disclosure, #ad, credits, the license manifest and cross-account duplicates.
6. **Task 6, routing, windows and spot checks** (amended 2026-10-02, log #142: `route` reads the format window from `WindowCounts.format_version`, and `ReviewRepo` takes an injected `FormatWindowSource`, default `NoFormatWindow()`, so S3c-2 only wires `SetupRepo` and edits no S2 module): `review/routing.py` and `db/review.py`; the producer-version window (5), the format window (10; always closed until S3c's `account_versions` exists), the dub window (10), the deterministic spot-check rule. No assisted-card tap counts (R2, R6, #454).
7. **Task 7, the dispatcher:** `dispatch/tasks.py`, `bot/posting.py` (`tick` becomes `assisted_tick`; the gate log-only unless `GATE_ENFORCE`; the in-flight exclusion), the first `copy_for` in `posting/captions.py`, and `app.py` (`dispatcher` cron replaces `posting_tick`; `dispatch_task`), `runtime.py`. The pinning test: with no `DATABASE_URL`, the dispatcher sends the env account's slot exactly as `posting_tick` did. Every tick folds held alerts first (ADR-45) and reads every `brake:*` key with `get`.
8. **Task 8, the autopilot CLI and admin routes:** `clipforge autopilot show|set|preset`, `clipforge policy dry-run [--account]` (exits 1 when anything would be held), the admin routes under the bearer token, and `web/openapi.json` regenerated (`scripts/check.sh` checks it and the generated client).
9. **Checkpoint S2a** (plan Task 8 step 5): update `docs/ARCHITECTURE.md` (the dispatcher, the brake keys, the autopilot table) and `.env.example` (the new settings, commented; none is needed for S2a), tick the S2a items in `docs/studio/04-roadmap.md` and `ROADMAP.md` only after the owner confirms the deploy (otherwise leave them for the coordinator), then run `pr-reviewer` and `migration-reviewer`, fix what they find, `scripts/check.sh` green, the report, and stop.

Stop for the owner at the checkpoint below.

## Checkpoints
- A (S2a): after actions 1–9. Suggested commit: `014: s2a: migration 0002, dispatcher, brake, autopilot, gate and routing`

## Done when
- `scripts/check.sh` is green (paste its summary lines into the report).
- `migration-reviewer` and `pr-reviewer` have no blocking findings, and the report lists what each said.
- The pinning test passes: with no `DATABASE_URL`, the dispatcher sends the env account's slot as `posting_tick` did, and `posting.problem` still alerts.
- With `GATE_ENFORCE` unset, no test shows the gate holding or routing an item.
- Migration 0002 upgrades and downgrades on a throwaway schema, autogenerate is empty afterwards, and `EXPECTED_HEAD` matches.
- The report has the owner's deploy steps below, ready to paste.

## Owner steps
- Before: card 010 done (above). `scripts/worktree.sh s2a/dispatch-gate`, open a session in `../clipForge-s2a`, paste `Run card docs/cards/014-s2a-dispatch-gate.md`.
- At A: commit with the suggested message, `git push -u origin s2a/dispatch-gate`, `gh pr create --fill`, squash-merge when CI is green.
- Deploy (from `main`, after the merge; the preconditions in "Depends on" still hold, and outside the posting slots):
  1. `uv run alembic upgrade head` (migration 0002; `DATABASE_URL_UNPOOLED` from `.env`; CI's deploy job is off while `DEPLOY_ENABLED` is unset, so the owner migrates), then `scripts/deploy.sh --dry-run` (it must show `database at the migration head: … 0002`), then `scripts/deploy.sh --reason "S2a: dispatcher replaces posting_tick"`.
  2. `uv run modal run src/clipforge/app.py::db_doctor`: the head is `0002`.
  3. For one day: compare the `dispatcher:` log lines with the previous day's `posting_tick:` lines (same sends), and `uv run clipforge posting verify` reports 0 differences.
  4. In Telegram: `/pause realtalk-clips-en`, `/go realtalk-clips-en`, `/pause all`, `/go all`. Then `uv run clipforge autopilot show realtalk-clips-en`: Hands-on, "Publish: on, waiting for a connected profile".
  5. `uv run clipforge policy dry-run` (the gate is still log-only). Note the count for S2b.
- **Rollback:** a revert deploy only: `git revert` of the S2a merge on `main`, then `scripts/deploy.sh --dry-run` and `scripts/deploy.sh --reason "revert S2a"`. Migration 0002 is expand-only, so the S1 code runs on it; a missing autopilot row reads as Hands-on. `STATE_READS` doesn't change (ADR-41's own rollback stays separate).

## Hand-off
Write `docs/reports/014-s2a-<YYYY-MM-DD>.md` from `docs/templates/handoff-report.md` at the checkpoint, with each task's status, the reviewers' findings and the deploy steps. Don't commit: the owner does. The next card is 015 (S2b), which starts after this deploy and one clean day.
