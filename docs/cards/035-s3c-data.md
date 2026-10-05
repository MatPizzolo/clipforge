# Card 035: S3c (S3c-1a) — versioned setup: data, preview, import and verify, routes

Status: proposed
Stream: S3c (S3c-1a) · Branch: `s3c/data` · Worktree: `../clipForge-s3c` (created with `scripts/worktree.sh s3c/data`)
Decision-log range: #250–#299 (append only; #250–#263 are taken, so #264–#299 are free, shared in sequence by cards 035–038: re-read the log and take the next free number)
Model: most capable (the migration, the versions service and its in-transaction preview, the projection onto S1's columns)
Depends on: card 010 **done** (S1's rollout), AND card 014 (S2a: migration 0002, `write_schedule_copy`, the autopilot table, `ACTOR_CHECK`) and card 022 (S3-1: the `admin` endpoint, `admin_routers`, `cli_router`, `require_web_actor`) **deployed** with their owner steps done (log #263). Per log #144, no other code card is on `main` undeployed when this one merges. S3c's migration is numbered at landing: S2a's 0002 first, then whichever of the hooks, S3 and S3c migrations lands next (#260)
Cost cap: $1 of Modal/API spend (fast tests and the local Postgres; no Modal runs needed). The owner's migration, deploy and `setup import` are not session spend

## Context
Card 003 revised the S3c design (ADR-42, amended by ADR-48 and ADR-50) and card 018 revised the spec again and wrote the plan: spec `docs/superpowers/specs/2026-09-30-studio-s3-workspaces-design.md`, plan `docs/superpowers/plans/2026-10-02-studio-s3c.md` (21 tasks in four deployable parts; PR #44; log #250–#263). The build is four cards (log #148, #257): **this card is S3c-1a (plan Tasks 1–7)**, then 036 (S3c-1b, Tasks 8–10), 037 (S3c-2, Tasks 11–16) and 038 (S3c-3, Tasks 17–21). They share the `s3c/` prefix, its log range and one worktree, one card at a time.

S3c-1a adds the data and routes, **with nothing visible and `SETUP_SOURCE=off`**: categories, blueprints and accounts as append-only versions of flat `{path: value}` maps, a pure resolver with origins, the one versions service (the only writer, recomputing the preview inside its transaction and rewriting the schedule copy after commit through S2a's `write_schedule_copy`), `POST /admin/setup/preview`, `clipforge setup import|verify|export` with the five drafted playbooks (#256), notes, and `PATCH /accounts/{id}` writing a version (#255).

Rulings and reviews that bind this card: the review tier, the budget, the pause, `accounts.publisher` and hook patterns are not in the setup (ADR-48, ADR-50; #260); S3c writes none of the hooks tables, `autopilot*`, `posting_state` or `post_events`; the migration carries none of 0002's deferred items and uses S2a's actor check with `system:`; the workspace routes go in `api/admin/setup.py` appended to S3's `admin_routers`, the CLI's routes in S3's `cli_router` (#146; card 027 moves them to `admin` only). If card 031 (S5-1) is deployed, Modal code is in `modal_app/` (S3c-1a adds none).

## Read first
1. `CLAUDE.md`, `STATUS.md`
2. The S3c plan: header, Global Constraints, Review Focus (1, 2 and 5 pin here), File map, Part S3c-1a (Tasks 1–7, the owner steps and the rollback)
3. The S3c spec: §1 (§1.3 ownership, §1.4 the field registry), §3 (§3.4 the preview, §3.5 change classes), §5 (§5.1 routes, §5.3 the migration, §5.4 import, §5.5, §5.6 `SETUP_SOURCE`), §7, §8; the S3 dashboard spec §8.7
4. `docs/DECISIONS.md`: ADR-14, ADR-26, ADR-35, ADR-41, ADR-42, ADR-44, ADR-48, ADR-50
5. Log rows #250–#263, #142, #144, #146, #147, #148
6. Card 014's and card 022's reports (migration numbers, `write_schedule_copy`, `admin_routers`, `cli_router`), and the hooks build's or S3's migration if one landed since
7. The code it changes: `models.py`, `config.py`, `alembic/versions/`, `db/tables.py`, `db/doctor.py`, `db/accounts.py`, `accounts/service.py`, `api/admin/__init__.py`, S3's `cli_router` module, `cli.py`
8. `docs/ops/secrets.md`, runbook §1 and §4

## Scope
- May edit, as `scripts/scopes.toml` allows for `s3c/`: `src/**` (including `src/clipforge/accounts/playbooks/*.md`), `tests/**`, `alembic/**`, `alembic.ini`, `.env.example` (`# SETUP_SOURCE=off`), `web/openapi.json` and `web/lib/api/**` (regenerated; nothing else in `web/` in this card), `docs/ARCHITECTURE.md` (an "Account setup (S3c)" paragraph), `docs/superpowers/plans/*s3c*` (ticks and a status line), `docs/studio/04-roadmap.md` and `ROADMAP.md` (ticks only after the owner confirms the deploy), `CLAUDE.md` (Commands: `clipforge setup …`; Layout), its own report, and log rows in #264–#299.
- Must not edit: the S3c spec, `docs/studio/05`, `06` and `08` (card 018's paths, not this card's), `STATUS.md`, other cards, `web/` pages (S3c-1b's), `needs/`, `dispatch/`, `review/` and the hooks modules, `prompts/`, `docs/ops/secrets.md` (nothing to add: `SETUP_SOURCE` is S3c-2's switch).
- **No new dependencies.** **Only `app.py` (and `modal_app/` once card 031 is deployed) imports `modal`.** **The session never deploys, migrates Neon or changes a secret.** **Never import a module that isn't on `main`.**

## Actions
Each task follows the plan: failing tests first, then the implementation, then its checks, then "check and record".
1. **Task 1, contracts and `SETUP_SOURCE`:** the setup contracts in `models.py`; `Settings.setup_source: Literal["off","db"] = "off"`.
2. **Task 2, the migration and the tables:** `alembic/versions/NNNN_s3c.py` with `NNNN` = the next number after `main`'s head at landing (rename and rebase if another landed first), explicit DDL, append-only triggers on the `*_versions` tables, the author check with `system:`; `db/tables.py`; `EXPECTED_HEAD`. Upgrade, downgrade and an empty autogenerate on a throwaway schema.
3. **Task 3, the field registry and the resolver:** `accounts/registry.py` (v1, spec §1.4), `accounts/setup.py` (`effective_setup` with origins, the projection, `diff`).
4. **Task 4, `SetupRepo` and the versions service:** `db/setup.py`, `accounts/versions.py` (409 on a stale `expected_version`; the projection never touches autopilot columns; the schedule copy rewritten after commit with `_checked`); `AccountsRepo.update` refuses projected columns once versioned; Review Focus 1 (`test_restore_with_unreleased_prompt_is_refused`) and 2 (`test_apply_refuses_all_when_one_schedule_fails`).
5. **Task 5, the one dry run:** `accounts/preview.py` (the diff with change classes, stages re-run, affected accounts and items, `blocked` reasons, the estimate); `test_preview_and_save_agree`.
6. **Task 6, `setup import`, `verify` and `export`:** `accounts/importer.py` and the five drafted playbooks (about 150–300 words each, from 01, 07 and 09); Review Focus 5 (`test_reimport_after_edit_skips_and_verifies_clean`).
7. **Task 7, routes, notes, `PATCH` and the CLI:** `api/admin/setup.py` appended to `admin_routers`; `db/notes.py`, `accounts/notes.py`; `PATCH /accounts/{id}` and `/setup/import|verify|export` in `cli_router` (`PATCH` splits S2's publisher fields from setup fields and refuses `review_tier` with 422); `clipforge setup …`; `web/openapi.json` and the client regenerated.
8. **Checkpoint S3c-1a** (plan Task 7 step 5): `docs/ARCHITECTURE.md`, `CLAUDE.md`, `.env.example`; `pr-reviewer`, `migration-reviewer` (the migration, `db/accounts.py`, the projection, the schedule copy) and `security-reviewer` (the new `/admin/` routes, the `cli_router` additions, actor handling); fix what they find; `scripts/check.sh` green; the report with `NNNN` and the owner steps below; stop.

Stop for the owner at the checkpoint below.

## Checkpoints
- A (S3c-1a): after actions 1–8. Suggested commit: `035: s3c-1a: versioned setup, preview, import and verify`

## Done when
- `scripts/check.sh` is green (paste its summary lines into the report).
- `pr-reviewer`, `migration-reviewer` and `security-reviewer` have no blocking findings, and the report lists what each said.
- S3c's migration upgrades and downgrades on a throwaway schema, autogenerate is empty afterwards, and `EXPECTED_HEAD` matches its number.
- Review Focus 1, 2 and 5 pass; the setup routes answer only on `admin` (`test_setup_routes_not_on_the_web_app`); `web/openapi.json` and `web/lib/api` are up to date.

## Owner steps
- Before: card 010 done; cards 014 and 022 deployed with their owner steps; nothing else undeployed on `main`. `scripts/worktree.sh s3c/data`, open a session in `../clipForge-s3c`, paste `Run card docs/cards/035-s3c-data.md`.
- At A: commit with the suggested message, `git push -u origin s3c/data`, `gh pr create --fill`, squash-merge when CI is green.
- Deploy (from `main`, after the merge, outside the blackout, runbook §1):
  0. **The #144 check:** no other code card is on `main` undeployed (`docs/ops/deploys.md` against `git log`).
  1. **Migrate:** `uv run alembic upgrade head` (`DATABASE_URL_UNPOOLED` from `.env`; CI's deploy job is off).
  2. `uv run modal run src/clipforge/app.py::db_doctor`: S3c's `NNNN` is the head, `ok`.
  3. `scripts/deploy.sh --dry-run`, then `scripts/deploy.sh --reason "S3c-1a: versioned setup (SETUP_SOURCE=off)"`.
  4. `uv run clipforge setup import --dry-run`, read the counts, then `uv run clipforge setup import`.
  5. `uv run clipforge setup verify`: `0 differences`.
  6. `uv run clipforge setup export > ~/clipforge-setup-<date>.json` (kept outside the repo).
  7. Commit the deploy line in `docs/ops/deploys.md`, and tell the coordinator. Nothing changes in Telegram or the dashboard; `clipforge account edit` now writes versions.
- **Rollback:** a revert deploy (`git revert` of the merge, `scripts/deploy.sh --dry-run`, `scripts/deploy.sh --reason "revert S3c-1a"`). The migration is expand-only; the new tables stay and are ignored; `SETUP_SOURCE` is still `off`. After rolling forward again, run `uv run clipforge setup verify`; an account edited through S1's path during the rollback needs one save to become a version.

## Hand-off
Write `docs/reports/035-s3c-<YYYY-MM-DD>.md` from `docs/templates/handoff-report.md` at the checkpoint, with each task's status, the migration number, the reviewers' findings and the owner steps. Don't commit: the owner does. The next card is 036 (S3c-1b), which starts once this and card 026 (S3-5) are deployed; remove this worktree after the merge (`scripts/worktree.sh --remove s3c/data`).
