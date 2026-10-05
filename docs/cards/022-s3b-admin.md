# Card 022: S3 (S3-1) — the `admin` endpoint, proxy auth, S3's migration and Settings

Status: proposed
Stream: S3 (S3-1) · Branch: `s3b/admin` · Worktree: `../clipForge-s3b` (created with `scripts/worktree.sh s3b/admin`)
Decision-log range: #630–#679 (append only; shared in sequence by cards 022–027, which run one at a time: re-read the log and take the next free number in the range)
Model: most capable (the endpoint split, proxy auth and token checks, the migration)
Depends on: card 010 done (S1's rollout through step 7, `STATE_READS=postgres` verified, `posting verify` at 0) AND card 014 (S2a) **deployed** with its owner steps done (`db_doctor` shows `0002`, the one-day `dispatcher:` watch is clean). Per log #144, no other code card is on `main` undeployed when this one merges. S3's migration lands after S2a's 0002, in the order "S2a first, then whichever of hooks, S3, S3c lands next, numbered at landing" (#620). Online use needs card 004 (the owner's Vercel steps, runbook §5b); before that the owner checks locally
Cost cap: $2 of Modal/API spend (fast tests, the local Postgres, at most a few `modal serve` checks of the `admin` function). The owner's deploy is not session spend

## Context
Card 009 designed the dashboard v1 and card 019 planned its build (`docs/superpowers/plans/2026-10-02-studio-s3-dashboard.md`, 23 tasks; spec §11 is the delta after S2's plan and wins where §1–§10 differ). The build is six cards, one per plan checkpoint (log #145): **this card is S3-1 (plan Tasks 1–5)**, then 023 (S3-2), 024 (S3-3), 025 (S3-4), 026 (S3-5) and 027 (S3-5b). They share the `s3b/` prefix, its log range and one worktree, one card at a time.

What S3-1 changes:
- **One route table, two mounts** (#610): `create_app(ctx, surface)` is mounted on `web` (public, `API_TOKEN`: today's routes, the webhooks, and the CLI's routes in one `cli_router`, so the CLI and Telegram are unchanged) and on a new `admin` function (`@modal.asgi_app(requires_proxy_auth=True)`, `ADMIN_API_TOKEN`, missing → 503). `admin` never mounts the public routes; `web` never mounts S3's routers.
- **Every write on `admin` needs `X-Clipforge-Actor: web:<login>`** (validated by `posting/actions.web_actor`, else 400), S1's `/accounts` and `/sources` writes included (#623).
- **Vercel reads `admin`** through `web/lib/upstream.ts`, the only module that reads `ADMIN_API_URL`, `ADMIN_API_TOKEN`, `MODAL_PROXY_KEY` and `MODAL_PROXY_SECRET` (#611).
- **S3's migration** (spec §11.8): `needs_log`, `settings`, `batches` and `content_items.queue_pin`, expand-only, numbered at landing, `EXPECTED_HEAD` moved in the same change.
- **Settings** (`GET|PUT /admin/settings`, `settings_service.py`, the page under More).

Since the plan was written:
- **Owner ruling 2026-10-02 (log #146):** at card 027's cut-over, S1's `/accounts` and `/sources` write routes move off `web` too, so `web` ends public-only. This card doesn't move anything, but keep `cli_router` one router (no S1/S2 split), so 027's cut-over stays a mount change.
- **Routes added before S3-1** (spec §11.2): if the hooks build has landed a dashboard-only route on `web` under `/admin/` (for example its interim `/hooks?account=` routes), this card moves it to the `admin` router; routes the CLI calls stay in `cli_router`.
- S2b (card 015) may be in progress. Merges and deploys are serialized (#144): whichever of 015 and this card merges second waits for the first one's deploy.

## Read first
1. `CLAUDE.md`, `STATUS.md`
2. The S3 plan: header, Global Constraints, Review Focus, File map, Part S3-1 (Tasks 1–5, the owner steps and the rollback), Deployable steps
3. The S3 dashboard spec §11 in full (especially §11.1 the inventory, §11.2 the endpoint, §11.3 the build order, §11.8 the data); then §8.7 and §10.2
4. `docs/DECISIONS.md`: ADR-2, ADR-14, ADR-38, ADR-41, ADR-44, ADR-48
5. Log rows #610–#623, #144, #145, #146 in `docs/studio/10-decision-log.md`
6. Card 014's report (what S2a landed: `/admin/*` routes, migration 0002, `web_actor`) and card 015's if it has merged
7. The code it changes: `src/clipforge/api/main.py`, `config.py`, `app.py`, `db/tables.py`, `db/doctor.py`, `alembic/versions/`, `scripts/export_openapi.py`, `web/lib/upstream.ts`, `web/app/api/cf/**`, `web/README.md`
8. `docs/ops/secrets.md`, runbook §1 (the blackout) and §5b

## Scope
- May edit, as `scripts/scopes.toml` allows for `s3b/`: `src/**`, `tests/**`, `alembic/**`, `alembic.ini`, `.env.example`, `pyproject.toml`, `uv.lock`, `web/**`, `scripts/export_openapi.py`, `docs/ARCHITECTURE.md`, `docs/ops/secrets.md`, `docs/superpowers/plans/*s3-dashboard*` (task ticks and a status line), `docs/studio/04-roadmap.md` and `ROADMAP.md` (ticks only after the owner confirms the deploy), `docs/studio/11-owner-runbook.md` (**§5b only** in this card), `CLAUDE.md` (Commands and Layout), its own report, and log rows in #630–#679.
- Must not edit: the spec, `STATUS.md`, other cards, `prompts/`, stage modules (`src/clipforge/stages/`), the runbook outside §5b, `scripts/` other than `export_openapi.py`.
- **No new dependencies.** **Only `app.py` imports `modal`.** **The session never deploys, migrates Neon, changes a secret or touches Vercel**: the owner does, from the commands below. **Never import a module that isn't on `main`.**

## Actions
Each task follows the plan: failing tests first, then the implementation, then its checks, then "check and record" (`scripts/check.sh` green, the task noted in the report).
1. **Task 1, `create_app(ctx, surface)` and the admin token:** `surface: Literal["web", "admin"]`; the surface-aware bearer check (`hmac.compare_digest`; a missing token answers 503); `cli_router` (the CLI's routes, listed in the plan) on both surfaces; public routes on `web` only; `admin_routers(ctx)` on `admin` only (`api/admin/__init__.py`, `deps.py` with `require_web_actor`); `Settings.admin_api_token`; `scripts/export_openapi.py` exports the `admin` surface; `web/openapi.json` and the client regenerated. `tests/api/admin/test_surfaces.py` pins both mounts.
2. **Task 2, the `admin` Modal function** in `app.py` (`requires_proxy_auth=True`, the same image and secrets as `web`); `tests/test_app.py` checks it is defined and uses `surface="admin"`.
3. **Task 3, S3's migration, tables and repositories:** `alembic/versions/NNNN_s3.py`, where `NNNN` is the next number after `main`'s head at landing (`0003` if S2a's `0002` is the head; rename the file and the revision ids if the hooks build or S3c landed first, and drop any item a previous migration already carries); `db/tables.py`; `EXPECTED_HEAD` in `db/doctor.py`; `db/needs.py` (`NeedsLogRepo` with the claim-first `claim`/`release`, #623), `db/settings.py`, `db/batches.py`; `NeedsLogEntry` and `BatchRow` in `models.py`. The migration test runs upgrade and downgrade on a throwaway schema and checks an empty autogenerate.
4. **Task 4, Settings:** `settings_service.py` (defaults from spec §2.6 and §7.9, one writer), `GET|PUT /admin/settings` on `admin`, the Settings page (under More) with its loading, error, stale and empty states.
5. **Task 5, `upstream.ts` on `admin`, with the actor:** the four variables, `Modal-Key`/`Modal-Secret`/bearer/`X-Clipforge-Actor` headers, the generic `call`, `web/lib/actor.ts`, `UPSTREAM_TIMEOUT_MS` (Review Focus 3: a slow first response is waited through), log lines naming only the route and the status; the Playwright env names. Docs: `docs/ops/secrets.md` (`ADMIN_API_TOKEN` in `clipforge-secrets`; the four Vercel variables, each with where it lives, who reads it and the rotation steps of spec §11.2), runbook §5b (the proxy token, the four variables, removing `CLIPFORGE_API_URL` and `API_TOKEN` from Vercel after the deploy, rotation), `.env.example` (`ADMIN_API_TOKEN=` commented), `web/README.md`.
6. **Checkpoint S3-1** (plan Task 5 step 5): the full `scripts/check.sh` and `scripts/check.sh --e2e`; update `docs/ARCHITECTURE.md` (the `admin` endpoint, S3's tables) and `CLAUDE.md` (Layout: `api/admin/`, `settings_service.py`); `pr-reviewer`, `security-reviewer` (the endpoint split, proxy auth, token checks, the actor header; #618) and `migration-reviewer`; fix what they find; the report with the owner steps below; stop.

Stop for the owner at the checkpoint below.

## Checkpoints
- A (S3-1): after actions 1–6. Suggested commit: `022: s3-1: admin endpoint, proxy auth, S3 migration, settings`

## Done when
- `scripts/check.sh` and `scripts/check.sh --e2e` are green (paste the summary lines into the report).
- `pr-reviewer`, `security-reviewer` and `migration-reviewer` have no blocking findings, and the report lists what each said.
- `test_surfaces.py` passes: `admin` answers 503 without `ADMIN_API_TOKEN`, never mounts a public route, and refuses a write without a valid actor (400); `web` mounts no S3 router and its routes and token are unchanged.
- S3's migration upgrades and downgrades on a throwaway schema, autogenerate is empty afterwards, and `EXPECTED_HEAD` matches its number.
- `web/openapi.json` and `web/lib/api` are up to date (the `openapi contract` and `web gen:check` lines).
- The report has the owner steps below with `NNNN` filled in.

## Owner steps
- Before: card 010 done and card 014 deployed with its owner steps (above); nothing else undeployed on `main`. `scripts/worktree.sh s3b/admin`, open a session in `../clipForge-s3b`, paste `Run card docs/cards/022-s3b-admin.md`.
- At A: commit with the suggested message, `git push -u origin s3b/admin`, `gh pr create --fill`, squash-merge when CI is green.
- Deploy (from `main`, after the merge, outside the blackout, runbook §1):
  0. **Pre-deploy check (#623):** no other code card is on `main` undeployed (`docs/ops/deploys.md` against `git log`), and `uv run modal run src/clipforge/app.py::db_doctor` shows the expected head (`0002`, or the hooks build's if it deployed first).
  1. **Secret:** add `ADMIN_API_TOKEN` to `clipforge-secrets` with the `docs/ops/secrets.md` procedure (a random value: `python -c "import secrets; print(secrets.token_urlsafe(32))"`), never `modal secret create --force`.
  2. **Migrate:** `uv run alembic upgrade head` (`DATABASE_URL_UNPOOLED` from `.env`; CI's deploy job is off while `DEPLOY_ENABLED` is unset, so the owner migrates).
  3. **Deploy:** `scripts/deploy.sh --dry-run` (it must show the database at the new head), then `scripts/deploy.sh --reason "S3-1: admin endpoint"`.
  4. `uv run modal run src/clipforge/app.py::db_doctor`: the head is S3's `NNNN`.
  5. **Proxy token:** create a Modal proxy token (Settings → Proxy Auth Tokens). From the laptop: `curl -s -o /dev/null -w "%{http_code}" <admin url>/accounts` → `401`; `curl -s -H "Modal-Key: …" -H "Modal-Secret: …" -H "Authorization: Bearer <ADMIN_API_TOKEN>" <admin url>/admin/settings` → the defaults.
  6. **Vercel (only if card 004 is done):** set `ADMIN_API_URL`, `ADMIN_API_TOKEN`, `MODAL_PROXY_KEY` and `MODAL_PROXY_SECRET` (runbook §5b), redeploy, check Home and Settings on the phone, then remove `CLIPFORGE_API_URL` and `API_TOKEN` from Vercel. Without card 004: `ADMIN_API_URL=… npm --prefix web run dev` with `AUTH_DISABLED=1`.
  7. Commit the line `scripts/deploy.sh` added to `docs/ops/deploys.md`, and tell the coordinator the deploy is done: 023 starts from it, and the roadmap ticks follow it.
- **Rollback:** a revert deploy only: `git revert` of the merge on `main`, `scripts/deploy.sh --dry-run`, then `scripts/deploy.sh --reason "revert S3-1"`. The migration is expand-only, so the old code runs on it. On Vercel, put `CLIPFORGE_API_URL` and `API_TOKEN` back. `web`'s routes and token don't change in S3-1, so the CLI and Telegram are unaffected throughout.

## Hand-off
Write `docs/reports/022-s3b-<YYYY-MM-DD>.md` from `docs/templates/handoff-report.md` at the checkpoint, with each task's status, the migration number, the reviewers' findings and the owner steps. Don't commit: the owner does. The next card is 023 (S3-2), which starts after this deploy; remove this worktree after the merge (`scripts/worktree.sh --remove s3b/admin`) so 023 can create `../clipForge-s3b` on its branch.
