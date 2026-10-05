# Card 038: S3c (S3c-3) — experiments and results

Status: proposed
Stream: S3c (S3c-3) · Branch: `s3c/experiments` · Worktree: `../clipForge-s3c` (created with `scripts/worktree.sh s3c/experiments`)
Decision-log range: #250–#299 (append only; shared in sequence by cards 035–038: re-read the log and take the next free number)
Model: mid-tier (implementing a written plan); most capable for the experiment lifecycle's transactions and the hooks freeze
Depends on: card 037 (S3c-2) **deployed** with its owner steps done AND card 016 (S2c: the digest's `DigestProvider` tuple) **deployed** (log #263). Per log #144, no other code card is on `main` undeployed when this one merges. The hooks freeze is a no-op (`NoHookFreezer`) unless the hooks build (card 028) is deployed
Cost cap: $1 of Modal/API spend (fast tests and the local Postgres; no Modal runs). The owner's deploy and the experiment's clip jobs are not session spend

## Context
Cards 035–037 deployed the versioned setup, the workspaces and the producer wiring (`SETUP_SOURCE=db`). **This card builds S3c-3, plan Tasks 17–21:** experiments (one running per account; start, stop and decide are the only writes, each recomputing the preview inside its transaction and pushing the hooks freeze in the same transaction), the metric registry with before/during, the Wilson verdict and "too few items", "needs a decision", autopilot markers, the re-cut estimate in the preview, the `/admin/experiments` routes, the digest line through S2c's `DigestProvider` (#261), the `experiment_decision` "needs me" row through S3's `needs_providers` (#147), and the pages (the Experiments nav item, the experiment page, the account's Results and Experiments tabs, learnings in the category playbook). Keep and revert are decided only on `/experiments/<id>` (#252).

What to watch:
- **`HookFreezer` has one home** (#562): `src/clipforge/hooks/freezer.py`. If card 028 (HK-1) created it, import it and change nothing; otherwise create it with exactly the plan's Task 17 content. If the hooks library is on `main`, `runtime.build_deps` wires `SqlHookFreezer(HookLibrary(db))` (HK-1's Task 5 rule), else `NoHookFreezer()`; and if the hooks build deploys after this card, its `clipforge hooks seed` freezes the experiments already running (#559).
- **If card 029 (HK-2) is deployed**, the reject-rate metric excludes rejects with reason `superseded:<id>` (hooks spec §10.6), with a test; otherwise tell the coordinator so HK-2 adds it.
- **If card 027 (S3-5b) is deployed**, `cli_router` is on `admin` only; the experiments routes are `admin`-only regardless.
- No file under `needs/`, `dispatch/` or `review/` changes; providers register in `runtime.build_deps`.

## Read first
1. `CLAUDE.md`, `STATUS.md`
2. The S3c plan: Global Constraints, Review Focus 4, Part S3c-3 (Tasks 17–21, the owner steps and the rollback), the coverage tables
3. The S3c spec §2.6–§2.8, §4 (experiments and results, §4.1 metrics, §4.4 the freeze), §5.1; the hooks spec §4.4 and §10.6
4. The S3 dashboard spec §7.7 (dataviz) and §7.10; `docs/studio/08-dashboard-and-operations.md` §2c (nav order)
5. `docs/DECISIONS.md`: ADR-42, ADR-45, ADR-48, ADR-50
6. Log rows #250, #252, #259–#263, #142, #147, #554, #559, #562, #144, #148
7. Cards 035–037's reports, card 016's, and card 028's and 029's if deployed
8. The code it changes: `models.py`, `accounts/preview.py`, `accounts/versions.py`, `runtime.py`, `api/admin/__init__.py`, `web/components/nav.ts`, the account workspace, the category page, Home's needs list, the link-contract test

## Scope
- May edit, as `scripts/scopes.toml` allows for `s3c/`: `src/**` (including `src/clipforge/hooks/freezer.py` only if it doesn't exist), `tests/**`, `web/**` (the experiment pages, tabs, nav, `web/openapi.json` and `web/lib/api` regenerated), `docs/ARCHITECTURE.md`, `docs/superpowers/plans/*s3c*`, `docs/studio/04-roadmap.md` and `ROADMAP.md` (the S3c-3 tick only after the owner confirms the deploy), `CLAUDE.md` (Layout), its own report, and log rows in #264–#299.
- Must not edit: `needs/`, `dispatch/`, `review/`, any other hooks module (and `hooks/freezer.py` if it exists), `alembic/` (no migration expected: stop and ask if one seems needed), `prompts/`, the S3c spec, `STATUS.md`, other cards.
- **No new dependencies.** **Only `app.py` (and `modal_app/` once card 031 is deployed) imports `modal`.** **The session never deploys, migrates Neon or changes a secret.**

## Actions
Each task follows the plan: failing tests first, then the implementation, then its checks, then "check and record".
1. **Task 17, experiments:** `db/experiments.py`, `accounts/experiments.py` (start, stop, decide; one running per account; the `experiment_running` blocked reason; saves inside an experiment carry `experiment_id`), `hooks/freezer.py` (only if absent), the experiment contracts; `test_start_freezes_and_stop_releases_in_the_same_transaction`, `test_failed_freeze_rolls_back_start`.
2. **Task 18, results:** `accounts/results.py` (`METRICS` with the nine "available now" rows and the S7 rows greyed, before/during, the Wilson verdict, `needs_decision`, markers including autopilot changes); Review Focus 4 (`test_items_window_never_closes_without_items`); `test_metric_registry_has_no_hook_metrics`.
3. **Task 19, the re-cut estimate** in the preview (`RecutScope`).
4. **Task 20, routes and wiring:** `api/admin/experiments.py` appended to `admin_routers`; `digest_line` in S2c's providers and `ExperimentDecisionProvider` in `needs_providers` through `runtime.build_deps`; the freezer wiring above.
5. **Task 21, the pages:** `/experiments` (`?needs=decision`) and `/experiments/<id>` (the decide bar, before/during cards, the verdict line, the markers chart with a table view), the account's Results and Experiments tabs and banner, Learnings on the category page, the nav item (after Produce on the laptop, first under More on the phone), the link-contract rows; `docs/ARCHITECTURE.md`, `CLAUDE.md`.
6. **Checkpoint S3c-3** (plan Task 21 step 5): `scripts/check.sh --e2e`; `pr-reviewer`, `migration-reviewer` (no migration expected; it confirms), `security-reviewer` (the `/admin/experiments` routes) and `docs-auditor`; fix what they find; the report with the freezer wiring used and the owner steps below; stop.

Stop for the owner at the checkpoint below.

## Checkpoints
- A (S3c-3): after actions 1–6. Suggested commit: `038: s3c-3: experiments and results`

## Done when
- `scripts/check.sh` and `scripts/check.sh --e2e` are green (paste the summary lines into the report).
- `pr-reviewer`, `migration-reviewer`, `security-reviewer` and `docs-auditor` have no blocking findings, and the report lists what each said.
- Review Focus 4 passes; a failed freeze rolls back a start; the digest provider and the needs provider are registered (`test_build_deps_registers_the_providers`) with no file under `needs/`, `dispatch/` or `review/` changed.
- The report says whether `hooks/freezer.py` was created or imported, and which freezer `build_deps` wires.

## Owner steps
- Before: cards 037 and 016 deployed; nothing else undeployed on `main`. `scripts/worktree.sh s3c/experiments`, open a session in `../clipForge-s3c`, paste `Run card docs/cards/038-s3c-experiments.md`.
- At A: commit with the suggested message, `git push -u origin s3c/experiments`, `gh pr create --fill`, squash-merge when CI is green.
- Deploy (from `main`, after the merge, outside the blackout):
  0. **The #144 check:** no other code card is on `main` undeployed (`docs/ops/deploys.md` against `git log`); `uv run modal run src/clipforge/app.py::db_doctor` shows the expected head.
  1. `scripts/deploy.sh --dry-run`, then `scripts/deploy.sh --reason "S3c-3: experiments"`; the Vercel deploy follows `main` (runbook §5b).
  2. **The exit (04's S3c):** on realtalk, start an experiment on max clip length (45 s, metric reject rate, 7 days) from the phone; clip new episodes during the window; after it, open the 09:00 digest's "experiments need a decision" link, read before and during for the reject rate and the posted rate, choose Keep with a reason and add the learning; check it shows in the clips playbook on the laptop.
  3. Commit the deploy line in `docs/ops/deploys.md`, and tell the coordinator.
- **Rollback:** a revert deploy (`git revert` of the merge, `scripts/deploy.sh --dry-run`, `scripts/deploy.sh --reason "revert S3c-3"`). Running experiments stay `running` in the tables and are ignored by the old code; hook weights stay frozen until a redeploy with S3c-3 decides or stops them, so stop the experiments before reverting if that matters.

## Hand-off
Write `docs/reports/038-s3c-<YYYY-MM-DD>.md` from `docs/templates/handoff-report.md` at the checkpoint, with each task's status, the freezer wiring, the reviewers' findings and the owner steps. Don't commit: the owner does. This closes S3c's build; remove the worktree after the merge (`scripts/worktree.sh --remove s3c/experiments`).
