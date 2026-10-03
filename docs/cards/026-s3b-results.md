# Card 026: S3 (S3-5) — Results → Costs, Compare, the account read view

Status: proposed
Stream: S3 (S3-5) · Branch: `s3b/results` · Worktree: `../clipForge-s3b` (created with `scripts/worktree.sh s3b/results`)
Decision-log range: #630–#679 (append only; shared in sequence by cards 022–027: re-read the log and take the next free number after card 025's rows)
Model: mid-tier (implementing a written plan)
Depends on: card 025 (S3-4) **deployed** with its owner steps done. Per log #144, no other code card is on `main` undeployed when this one merges. The strike form, Promote and the Overview's next rung need card 016 (S2c) **deployed**; without it they ship with their "arrives with S2c" states. Online use needs card 004
Cost cap: $2 of Modal/API spend (fast tests and the local Postgres). The owner's deploy is not session spend

## Context
Cards 022–025 deployed the `admin` endpoint, Settings, the needs API, Home, `/act`, Review, Calendar, Produce, Jobs and Sources. Read card 025's report first. **This card builds S3-5, plan Tasks 19–21:** Results → Costs, Accounts → Compare for the weekly hour, and the minimal account read view with the Overview, Autopilot and Activity tabs (and Sources & episodes for clips accounts) (spec §11.6, #615).

Rules that bind this card:
- **Costs** come from `jobs.costs`; per-account caps from S2's `autopilot` row; the fleet cap and the fixed subscriptions from `settings`. **Caps are shown, never enforced.** Stats and Money show "Views and revenue arrive with analytics (S7)". The chart follows the dataviz rules (§7.7) with a table view under it; ranges at most 92 days.
- **Autopilot tab** uses S2's routes (`GET|PUT /admin/accounts/{id}/autopilot`, `POST …/autopilot/promote`, `GET …/ladder`), reused and never re-implemented: presets, controls with what each waits on, a required reason for any Review dial change, Promote only when the ladder says ready.
- **Strikes:** `POST /admin/accounts/{id}/strikes` calls `AutopilotService.record_strike` (S2 Task 21) when S2c is on `main`, else answers 404 "arrives with S2c". The strike event carries `web:<login>`; the demotion it triggers stays `system:demotion` (ADR-48).
- **Never import a module that isn't on `main`** (the ladder, `record_strike`); the report names what waits for card 016.
- **Not in S3:** the studio map, Style, Hooks, Setup & History, Experiments and Notes (S3c and the hooks build); Personas (S8); Decisions (S6); Stats and Money (S7). A `?tab=` the view doesn't have falls back to Overview with "comes with account workspaces (S3c)", so 08 §2b's links never break.

## Read first
1. `CLAUDE.md`, `STATUS.md`
2. Card 025's report, and card 016's if it has merged
3. The S3 plan: Global Constraints, Part S3-5 (Tasks 19–21, owner steps, rollback), the Coverage table
4. The S3 dashboard spec §11.6 (the account read view), §11.1, §7 (Results, Accounts; §7.7 charts); §2.6; mockups `docs/design/dashboard/results.html`, `accounts.html`, `account.html`
5. `docs/DECISIONS.md`: ADR-42, ADR-48, ADR-49, ADR-50
6. Log rows #615, #621, #623, #144–#146
7. The code it changes and calls: `fleet.py`, `accounts/autopilot.py`, `accounts/runway.py`, `db/jobs.py`, `settings_service.py`, `api/admin/`, `web/components/nav.ts`, `web/lib/links.ts`

## Scope
- May edit, as `scripts/scopes.toml` allows for `s3b/`: `src/**`, `tests/**`, `.env.example`, `pyproject.toml`, `uv.lock`, `web/**`, `scripts/export_openapi.py`, `docs/ARCHITECTURE.md`, `docs/ops/secrets.md`, `docs/superpowers/plans/*s3-dashboard*` (task ticks), `docs/studio/04-roadmap.md` and `ROADMAP.md` (ticks only after the owner confirms the deploy), `docs/studio/11-owner-runbook.md` (**§5b only**), `CLAUDE.md` (Commands and Layout), its own report, and log rows in #630–#679.
- Must not edit: the spec, `STATUS.md`, other cards, `prompts/`, stage modules, `alembic/` (S3-5 adds no data), S2 modules that aren't on `main`.
- **No new dependencies.** **Only `app.py` imports `modal`.** **The session never deploys, migrates Neon, changes a secret or touches Vercel.**

## Actions
Each task follows the plan: failing tests first, then the implementation, then its checks, then "check and record".
1. **Task 19, Results → Costs:** `CostsReport`, `AccountCost`, `DayCost` in `models.py`; `results.py` (`costs`); `api/admin/results.py` (`GET /admin/results/costs?from=&to=&accounts=`, at most 92 days); `/results` with the Stats, Money and Costs tabs, the cumulative chart with the cap as a reference line and a table view; nav and `links.ts` (`/results?tab=costs&account=<id>`); `results.spec.ts`.
2. **Task 20, Compare, overview, activity and strikes routes:** `CompareRow`, `Focus`, `CompareView`, `AccountOverview`, `ActivityLine` in `models.py`; `fleet.py` (compare with the focus ranking, overview, activity from `post_events`, `jobs` and `autopilot_events`); `api/admin/accounts.py` (`GET /admin/accounts/compare?days=7`, `GET …/{id}/overview`, `GET …/{id}/activity?date=`, `POST …/{id}/strikes`); `test_strike_records_owner_and_demotion_by_system` only with S2c on `main`.
3. **Task 21, Compare page and the account read view:** `/accounts?view=compare` (three focus cards, then the table; "The studio map comes with account workspaces (S3c)"), `/accounts/<id>?tab=overview|autopilot|activity|sources` with the components and route handlers (including S2's autopilot, promote and ladder), the strike form, the tab fallback; nav and `links.ts` flips; `accounts.spec.ts` at phone and desktop sizes.
4. **Checkpoint S3-5** (plan Task 21 step 4): the full `scripts/check.sh` and `scripts/check.sh --e2e`; `docs/ARCHITECTURE.md` (Results, Compare, the account view) and `CLAUDE.md` (Layout: `results.py`); `pr-reviewer`; fix what it finds; the report; stop.

Stop for the owner at the checkpoint below.

## Checkpoints
- A (S3-5): after actions 1–4. Suggested commit: `026: s3-5: results costs, compare, account view`

## Done when
- `scripts/check.sh` and `scripts/check.sh --e2e` are green (paste the summary lines into the report).
- `pr-reviewer` has no blocking findings, and the report lists what it said.
- No route duplicates S2's autopilot, ladder or promote routes; caps are shown and never enforced; every `exists: true` link in `links.ts` resolves at both sizes.
- The report says which parts wait for card 016 (S2c), if it isn't on `main`.

## Owner steps
- Before: card 025 deployed with its owner steps. After 025's merge, `scripts/worktree.sh --remove s3b/produce`, then `scripts/worktree.sh s3b/results`, open a session in `../clipForge-s3b`, paste `Run card docs/cards/026-s3b-results.md`.
- At A: commit with the suggested message, `git push -u origin s3b/results`, `gh pr create --fill`, squash-merge when CI is green.
- Deploy (from `main`, after the merge, outside the blackout):
  0. **Pre-deploy check (#623):** no other code card is on `main` undeployed (`docs/ops/deploys.md` against `git log`), and `uv run modal run src/clipforge/app.py::db_doctor` shows S3's head.
  1. `scripts/deploy.sh --dry-run`, then `scripts/deploy.sh --reason "S3-5: results, compare, accounts"`. There is no migration.
  2. Online (after card 004; redeploy the dashboard from `main`): Results → Costs, Accounts → Compare (three focus cards), one account's Overview, Autopilot and Activity.
  3. Commit the `docs/ops/deploys.md` line and tell the coordinator the deploy is done.
- **Rollback:** a revert deploy (`git revert` of the merge, `scripts/deploy.sh --dry-run`, `scripts/deploy.sh --reason "revert S3-5"`); it adds no data. In Vercel, promote the previous dashboard deployment.

## Hand-off
Write `docs/reports/026-s3b-<YYYY-MM-DD>.md` from `docs/templates/handoff-report.md` at the checkpoint, with each task's status, what waits for S2c, the reviewer's findings and the owner steps. Don't commit: the owner does. The next card is 027 (S3-5b), which starts only after its 7-day waits.
