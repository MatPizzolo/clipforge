# Card 023: S3 (S3-2) — "needs me", Home, `/act` and the link contract

Status: proposed · Updated 2026-10-05 (ADR-54): Telegram is notifications only, so this card's Open buttons are how every "needs me" row reaches the phone; it runs before S2b (card 015)
Stream: S3 (S3-2) · Branch: `s3b/needs` · Worktree: `../clipForge-s3b` (created with `scripts/worktree.sh s3b/needs`)
Decision-log range: #630–#679 (append only; shared in sequence by cards 022–027: re-read the log and take the next free number after card 022's rows)
Model: mid-tier (implementing a written plan); most capable for the router's claim-first action and the alert redraw
Depends on: card 022 (S3-1) **deployed** with its owner steps done (`db_doctor` shows S3's head; `admin` answers with the proxy pair). Per log #144, no other code card is on `main` undeployed when this one merges. Online use needs card 004
Cost cap: $2 of Modal/API spend (fast tests and the local Postgres; no Modal runs needed). The owner's deploy is not session spend

## Context
Card 022 deployed S3-1: the `admin` endpoint (proxy auth plus `ADMIN_API_TOKEN`, writes need `X-Clipforge-Actor`), S3's migration (`needs_log`, `settings`, `batches`, `queue_pin`), Settings, and `upstream.ts` on `admin`. Read card 022's report first for the migration number and any deviation. **This card builds S3-2, plan Tasks 6–11:** the needs API, runway, the fleet scoreboard and slots, Open buttons with the alert redraw, Home as the daily check-in, `/act/<kind>/<subject>` and the link-contract test (ADR-44, spec §7.10).

Rules that bind this card:
- **"Needs me" is derived on read** by one provider per kind (`needs/providers.py`, a registry). The router owns no state except `needs_log`, and **an action claims its row before the owning service runs**, releasing it if the service refuses (#623). A GET never writes `needs_log`.
- **Providers and landing order** (spec §11.1): register only the providers whose sources are on `main`. S1 and S2a give `job_failed`, `held_clips`, `permission_expired`, `outage` and `runway_low`; `review_due`/`review_batch` need S2b's review service (card 015), `publish_failed`/`publisher_disconnected`/`strike` need S2c's `open_problems` and `promotion_ready` needs S2c's ladder (card 016). **Never import a module that isn't on `main`**: a provider for an S2 card that hasn't landed is named in the report as that card's follow-up.
- The same rule for Task 10's optional edits: `publishing/problems.alert_problem` and `dispatch/digest.py`'s `EXISTING_PAGES` change only if they are on `main`. There is no `review/cards.py` any more (ADR-54); card 015's `review/notify.py` sends the review notification through `ops.alert` with this card's Open button.
- **"Needs me" notifications (ADR-54, log #149):** every instant row type is pushed to Telegram as one notification with a URL button Open ↗ → `/act/<kind>/<id>` (or `/review?account=<id>` for "N items need review"), never with decision buttons. Acting on the dashboard redraws it as "✅ Done by …" (#616). Under ADR-54's build order this card lands before S2b, so `review_due` and the S2 failure providers are named in the report as cards 015's and 016's follow-ups.
- `accounts/ladder.py`'s runway input moves to `accounts/runway.py` only if the ladder is on `main` (S2c).
- The failure alert gains **[Resume]**, and typed `/resume <id>` goes through the needs router with `surface="telegram"` when the database is wired (#623), so `/act` shows "Done by telegram:… at …".

## Read first
1. `CLAUDE.md`, `STATUS.md`
2. Card 022's report
3. The S3 plan: Global Constraints, Review Focus (items 1, 2, 4, 5 are pinned in Tasks 8 and 11), Part S3-2 (Tasks 6–11, owner steps, rollback)
4. The S3 dashboard spec §11.1 (the needs mapping, providers and landing order), §11.7 (polling, alert redraw), §11.8 (`needs_log`), §7 (pages, §7.10 the link contract, §7.11 the rows), §2.7 (minutes per row), §3.3 (runway); mockups `docs/design/dashboard/home.html` and `act.html`, `DESIGN.md`
5. `docs/DECISIONS.md`: ADR-14, ADR-44, ADR-45, ADR-54
6. Log rows #612, #616, #620–#623, #144–#146
7. The code it changes: `src/clipforge/ops.py`, `bot/messages.py`, `bot/webhook.py`, `bot/posting.py`, `posting/daily.py`, `service.py`, `sources.py`, `api/admin/`, `web/app/(app)/page.tsx`, `web/lib/`, `web/components/nav.ts`

## Scope
- May edit, as `scripts/scopes.toml` allows for `s3b/`: `src/**`, `tests/**`, `alembic/**` (not needed here: S3-2 has no migration), `.env.example`, `pyproject.toml`, `uv.lock`, `web/**`, `scripts/export_openapi.py`, `docs/ARCHITECTURE.md`, `docs/ops/secrets.md`, `docs/superpowers/plans/*s3-dashboard*` (task ticks), `docs/studio/04-roadmap.md` and `ROADMAP.md` (ticks only after the owner confirms the deploy), `docs/studio/11-owner-runbook.md` (**§5b only**), `CLAUDE.md` (Commands and Layout), its own report, and log rows in #630–#679.
- Must not edit: the spec, `STATUS.md`, other cards, `prompts/`, stage modules, S2 modules that aren't on `main`.
- **No new dependencies; no migration.** **Only `app.py` imports `modal`.** **The session never deploys, migrates Neon, changes a secret or touches Vercel.**

## Actions
Each task follows the plan: failing tests first, then the implementation, then its checks, then "check and record".
1. **Task 6, needs contracts and the provider registry:** `NeedsKind`, `NeedsAction`, `NeedsRow`, `Attention`, `NeedsList`, `NeedsDetail` in `models.py`; `needs/registry.py` (`Provider` with `done`, `AlreadyDone`, `REGISTRY`), `needs/providers.py` (`JobFailedProvider`, `HeldClipsProvider`, `PermissionExpiredProvider`, `OutageProvider`, plus any S2 provider whose module is on `main`), `needs/attention.py` (`estimate_minutes`, `attention`).
2. **Task 7, runway:** `accounts/runway.py` (§3.3: unclipped imported episodes included) and the `runway_low` provider; the ladder's input only if S2c is on `main`.
3. **Task 8, the needs routes and the router:** `needs/router.py` (`list_rows`, `detail` with `open`/`done`/`gone`, the claim-first `act`, `snooze` for digest rows), `api/admin/needs.py` with `subject:path`. Pinning tests: `test_second_action_returns_already_done`, `test_detail_of_vanished_row_is_gone_not_500`, `test_outage_row_first_when_flag_set`, `test_subject_with_colon_round_trips`, and the two-connection concurrency test.
4. **Task 9, fleet scoreboard and slots:** `fleet.py` and `GET /admin/fleet/scoreboard`, `GET /admin/slots` (a day for Home, up to 14 days for Calendar); `waiting_approval` from `slot_plans` only when S2b is on `main`.
5. **Task 10, Open buttons and the alert redraw:** `OpsAlerts.alert(..., row_id=)`, `alert:msg:<row id>` (one writer, `ops.py`), `mark_done` (best-effort, never raises), the fold path; typed `/resume` through the router (the failure alert carries only Open → `/act/job_failed/<id>`, no [Resume] button: ADR-54, owner 2026-10-05); the row-kind callers pass `row_id`; the optional S2 edits only if merged.
6. **Task 11, Home, `/act` and the link-contract test:** the pages and route handlers, `web/lib/links.ts` with `links.json` (`gen:links`, checked by `gen:check`), `NEEDS_POLL_MS = 15_000` (nothing while hidden), §6's nav (pages not built yet left out), Playwright `home`, `act` (including "act shows not found for an unknown id") and `links` at phone and desktop sizes, and `tests/test_link_contract.py`. `web/openapi.json` and the client regenerated with every route change.
7. **Checkpoint S3-2** (plan Task 11 step 5): the full `scripts/check.sh` and `scripts/check.sh --e2e`; `docs/ARCHITECTURE.md` (the needs API, `alert:msg:*`) and `CLAUDE.md` (Layout: `needs/`, `fleet.py`); `pr-reviewer`; fix what it finds; the report, listing the providers registered and those left for the S2 cards' follow-ups; stop.

Stop for the owner at the checkpoint below.

## Checkpoints
- A (S3-2): after actions 1–7. Suggested commit: `023: s3-2: needs API, Home, act view, link contract, alert Open buttons`

## Done when
- `scripts/check.sh` and `scripts/check.sh --e2e` are green (paste the summary lines into the report).
- `pr-reviewer` has no blocking findings, and the report lists what it said.
- The Review Focus tests above pass; a GET of `/admin/needs` writes nothing.
- `links.spec.ts` resolves every `exists: true` path at both sizes, and `test_link_contract.py` matches every `ops.alert` path to one.
- No module imports an S2 module that isn't on `main` (the report says which providers were registered).

## Owner steps
- Before: card 022 deployed with its owner steps. After 022's merge, `scripts/worktree.sh --remove s3b/admin`, then `scripts/worktree.sh s3b/needs`, open a session in `../clipForge-s3b`, paste `Run card docs/cards/023-s3b-needs.md`.
- At A: commit with the suggested message, `git push -u origin s3b/needs`, `gh pr create --fill`, squash-merge when CI is green.
- Deploy (from `main`, after the merge, outside the blackout):
  0. **Pre-deploy check (#623):** no other code card is on `main` undeployed (`docs/ops/deploys.md` against `git log`), and `uv run modal run src/clipforge/app.py::db_doctor` shows S3's head.
  1. `scripts/deploy.sh --dry-run`, then `scripts/deploy.sh --reason "S3-2: needs, Home, act"`. There is no migration.
  2. Online (after card 004): redeploy the dashboard from `main` (`vercel deploy --prod` in `web/`, or the Git integration). Open Home on the phone: needs, the meter, the scoreboard, slots.
  3. The next ops alert with a row (a failed job, a permission hold) carries Open ↗ → `/act/...`. Act on it in the dashboard; the Telegram message turns into "✅ Done by web:<login>".
  4. Commit the `docs/ops/deploys.md` line and tell the coordinator the deploy is done.
- **Rollback:** a revert deploy (`git revert` of the merge, `scripts/deploy.sh --dry-run`, `scripts/deploy.sh --reason "revert S3-2"`). `alert:msg:*` keys are short-lived and ignored by the old code; `needs_log` rows stay and are harmless. In Vercel, promote the previous dashboard deployment.

## Hand-off
Write `docs/reports/023-s3b-<YYYY-MM-DD>.md` from `docs/templates/handoff-report.md` at the checkpoint, with each task's status, the providers registered and left over, the reviewer's findings and the owner steps. Don't commit: the owner does. The next card is 024 (S3-3), after this deploy.
