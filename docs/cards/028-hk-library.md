# Card 028: HK (HK-1) — the hook library: tables, seeds, rotation on jobs, control stamps

Status: sent 2026-10-06; PR 1 (hk-1a: contracts, migration 0003, the freezer protocol) merged 2026-10-06 (PR #54), deploy next; PR 2 (library, seeds, rotation, stamps, CLI) after PR 1 is deployed
Stream: HK (HK-1) · Branch: `hk/library` · Worktree: `../clipForge-hk` (created with `scripts/worktree.sh hk/library`)
Decision-log range: #550–#579 (append only; #550–#562 are taken, so #563–#579 are free, shared in sequence by cards 028–030: re-read the log and take the next free number)
Model: mid-tier (implementing a written plan); most capable for the migration and Task 5's enqueue and package change
Depends on: card 010 **done** (S1's rollout through step 7: `STATE_READS=postgres` verified, `clipforge posting verify` at 0) AND card 014 (S2a) **deployed** with its owner steps done (`db_doctor` shows `0002`, or the head of whichever of S3's and S3c's migrations deployed since; S2a's `system:` actors, `ACTOR_CHECK` and `/admin/*` style are on `main`). Per log #144, no other code card is on `main` undeployed when this one merges. The hooks migration is numbered at landing: S2a's 0002 first, then whichever of the hooks, S3 and S3c migrations lands next (#141, #620)
Cost cap: $1 of Modal/API spend (fast tests and the local Postgres; the LLM is mocked; no Modal runs needed). The owner's deploy, the seed and one channel job are not session spend

## Context
Card 020 designed and planned the hook library (ADR-50): spec `docs/superpowers/specs/2026-10-02-studio-hooks-design.md` (owner-approved), plan `docs/superpowers/plans/2026-10-02-studio-hooks.md` (12 tasks, three deployable parts; PR #42; log #550–#562). The build is three cards (log #148): **this card is HK-1 (plan Tasks 1–6)**, then 029 (HK-2, Tasks 7–11) and 030 (HK-3, Task 12). They share the `hk/` prefix, its log range and one worktree, one card at a time.

HK-1 is data and library only, **with `HOOK_VARIANTS` off: clip output doesn't change**. What the owner sees after the deploy: `clipforge hooks list|seed|…`, six seeded patterns per clips account (#552), and new items stamped with the control pattern (`hook_pattern_id`, `hook_version`, `hook_weights`), also in `metadata.json`.

Decisions since the plan was written, and what to watch:
- **One home for `HookFreezer`** (coordinator, 2026-10-05; #562): `src/clipforge/hooks/freezer.py` with the plan's verbatim content. S3c-3 (card 038) will come later, so **this card creates the file** (check first that it doesn't exist) and `SqlHookFreezer` in `hooks/library.py` implements it.
- **Routes (Task 6):** every path is under `/admin`. If S3-1's `cli_router` (card 022) is on `main`, the CLI's hooks routes go in it; otherwise add them in `create_app` next to S2's `/admin/*` routes with `Depends(require_token)`, and card 022 moves them. Say in the report which one applied.
- **The migration** copies S2a's `ACTOR_CHECK` string (migrations never import each other), carries none of 0002's deferred items, and moves `EXPECTED_HEAD`. If 0002 is somehow not on `main`, stop and ask the coordinator.
- **If card 031 (S5-1) has deployed**, Modal code lives in `modal_app/`: "only `app.py` imports `modal`" reads "only `app.py` and `modal_app/`". HK-1 adds no Modal function.

Other sessions: S2 (015, 016), S3 (022–027) and S5 (031–034) cards develop alongside; merges and deploys are serialized (#144).

## Read first
1. `CLAUDE.md`, `STATUS.md`
2. The hooks plan: Global Constraints (the dependency table, migrations, one writer per table, routes, extension points, `HookFreezer`), Review Focus, File map, Part HK-1 (Tasks 1–6, the owner deploy steps and the rollback)
3. The hooks spec: §1 (contracts), §2.1 and §2.5 (the flag), §3 (data), §4 (library, rotation, the freeze), §7.1 (routes), §10
4. `docs/DECISIONS.md`: ADR-8, ADR-14, ADR-41, ADR-42, ADR-48, ADR-49, ADR-50
5. Log rows #550–#562, #141, #142, #144, #147 and #148 in `docs/studio/10-decision-log.md`
6. Card 014's report (migration 0002, `ACTOR_CHECK`, `/admin/*` routes, `system:` actors), and card 022's if it has deployed
7. The code it changes: `models.py`, `config.py`, `db/tables.py`, `db/doctor.py`, `db/posting.py`, `alembic/versions/`, `service.py`, `pipeline/steps.py`, `stages/package.py`, `stages/captions.py` (comments only), `posting/enqueue.py`, `posting/actions.py`, `runtime.py`, `api/main.py`, `cli.py`
8. `docs/ops/secrets.md`, runbook §1 (the blackout)

## Scope
- May edit, as `scripts/scopes.toml` allows for `hk/`: `src/**`, `tests/**`, `alembic/**`, `alembic.ini`, `.env.example` (`# HOOK_VARIANTS=false`), `web/openapi.json` and `web/lib/api/**` (regenerated with the routes), `docs/ARCHITECTURE.md`, `docs/superpowers/plans/*studio-hooks*` (task ticks and a status line), `docs/studio/04-roadmap.md` and `ROADMAP.md` (HK-1 ticks only after the owner confirms the deploy), `CLAUDE.md` (Commands and Layout), its own report, and log rows in #563–#579.
- Must not edit: the hooks spec, `STATUS.md`, other cards, `prompts/` (HK-2's), `web/` beyond the two generated paths (HK-3's), `needs/` and `dispatch/digest.py` (extension points only, #142, #147), `docs/studio/05` and `08` (card 020's paths, not this card's), `docs/ops/secrets.md` (nothing to add in HK-1).
- **No new dependencies.** **Only `app.py` (and `modal_app/` once card 031 is deployed) imports `modal`.** **The session never deploys, migrates Neon or changes a secret**: the owner does, from the commands below. **Never import a module that isn't on `main`.**

## Actions
Each task follows the plan: failing tests first, then the implementation, then its checks, then "check and record" (`scripts/check.sh` green, the task noted in the report).
1. **Task 1, contracts, the setting and the `keywords_v1` comment fix:** the hook contracts in `models.py` exactly as spec §1, the optional fields on `JobInput`, `CaptionFiles`, `RenderedClip`, `PackagedClip`, `ContentItem`, `KeywordsReply`, `Job.hooks_note`, `Versions.hook_rotation` (every new field optional with a default); `Settings.hook_variants = False`; the stale `keywords_v1` comments in `stages/captions.py` and `tests/stages/test_captions.py` (the STATUS follow-up).
2. **Task 2, the migration and the tables:** `alembic/versions/NNNN_hooks.py` with `NNNN` = the next number after `main`'s head at landing (rename the file and the revision ids if S3's or S3c's migration landed first), the six tables and five `content_items` columns, `db/tables.py`, `EXPECTED_HEAD`. The migration test runs upgrade and downgrade on a throwaway schema and checks an empty autogenerate; the append-only and actor checks have their tests.
3. **Task 3, rotation (pure):** `hooks/rotation.py` (`resolve`, `seed_for`, `clip_seed`, `pick`, `control_entry`, `weights_of`, `control_stamp`); Review Focus 5 (`test_empty_rotation_picks_none`).
4. **Task 4, the library, the freezer and the seeds:** `db/hooks.py`, `hooks/library.py` (the one writer of the hook tables; `SqlHookFreezer`), `hooks/seeds.py` (six patterns, idempotent, actor `system:migration`; "No promises" in Number + stakes and Bold claim), and `hooks/freezer.py` with the plan's verbatim content.
5. **Task 5, the rotation on the job and the control stamp on items:** `service.create_job` freezes the account's rotation (any exception → `hooks=None`, `Job.hooks_note = "unavailable"`, a warning); `package` writes `Versions.hook_rotation` and, flag off, the control stamp on `PackagedClip.hook`; `enqueue` stamps items through `control_stamp`; `db/posting._item_row` writes the stamp columns and the reader fills `hook_stamp` and `superseded_by`; `runtime.build_deps` sets `Deps.hooks`. The captions cache key and `producer_version` stay byte-identical (pinned tests).
6. **Task 6, library routes and the CLI:** the `/admin` hooks routes (`cli_router` if on `main`, else the interim mount above), `clipforge hooks list|show|add|edit|approve|retire|share|weight|seed|stats` (stats filled by HK-2), `web/openapi.json` and the client regenerated (`npm --prefix web run gen`); Review Focus 5 (`test_library_reports_empty_rotation`).
7. **Checkpoint HK-1** (plan Task 6 step 5): update `docs/ARCHITECTURE.md` (the hooks tables and the stamp, under "Durable state in Postgres"), `.env.example`, `CLAUDE.md` (Commands: `clipforge hooks …`; Layout: `hooks/`), then `pr-reviewer`, `migration-reviewer` (the migration, `db/posting.py`) and `pipeline-reviewer` (Task 5's package and enqueue change, the pinned cache key and `producer_version`); fix what they find; `scripts/check.sh` green; the report with the owner steps below and `NNNN` filled in; stop.

Stop for the owner at the checkpoint below.

## Checkpoints
- A (HK-1): after actions 1–7. Suggested commit: `028: hk-1: hook library tables, seeds, rotation on jobs, control stamps`

## Done when
- `scripts/check.sh` is green (paste its summary lines into the report).
- `pr-reviewer`, `migration-reviewer` and `pipeline-reviewer` have no blocking findings, and the report lists what each said.
- The hooks migration upgrades and downgrades on a throwaway schema, autogenerate is empty afterwards, and `EXPECTED_HEAD` matches its number.
- With `HOOK_VARIANTS` unset, `captions.stage_version` is "3", the prompt is `keywords_v2`, and the captions cache key and `producer_version` equal today's (pinned tests).
- `web/openapi.json` and `web/lib/api` are up to date (the `openapi contract` and `web gen:check` lines).
- The report says where the routes were mounted (`cli_router` or the interim mount) and that `hooks/freezer.py` was created.

## Owner steps
- Before: card 010 done and card 014 deployed (above); nothing else undeployed on `main`. `scripts/worktree.sh hk/library`, open a session in `../clipForge-hk`, paste `Run card docs/cards/028-hk-library.md`.
- At A: commit with the suggested message, `git push -u origin hk/library`, `gh pr create --fill`, squash-merge when CI is green.
- Deploy (from `main`, after the merge, outside the blackout, runbook §1):
  0. **The #144 check:** no other code card is on `main` undeployed (`docs/ops/deploys.md` against `git log`); `uv run clipforge posting verify` at 0.
  1. **Migrate:** `uv run alembic upgrade head` (`DATABASE_URL_UNPOOLED` from `.env`; CI's deploy job is off while `DEPLOY_ENABLED` is unset, so the owner migrates).
  2. **Deploy:** `scripts/deploy.sh --dry-run` (it must show the database at the hooks head), then `scripts/deploy.sh --reason "HK-1: hook library, control stamps"`.
  3. `uv run modal run src/clipforge/app.py::db_doctor`: the head is the hooks `NNNN`.
  4. `uv run clipforge hooks seed --dry-run`, then `uv run clipforge hooks seed`: "realtalk-clips-en: 6 patterns" (and each other clips account).
  5. `uv run clipforge hooks list realtalk-clips-en`: six patterns, weight 1.0, "6 rotating".
  6. Clip one episode (`uv run clipforge clip videos/<source>/<file>`). When it's done, its items carry `hook_pattern_id` = the control's id (Neon console: `select id, hook_pattern_id, hook_version from content_items order by queued_at desc limit 5`), and the clips look exactly as before.
  7. Commit the line `scripts/deploy.sh` added to `docs/ops/deploys.md`, and tell the coordinator the deploy is done: 029 starts from it, and the roadmap ticks follow it.
- **Rollback:** a revert deploy only: `git revert` of the merge on `main`, `scripts/deploy.sh --dry-run`, then `scripts/deploy.sh --reason "revert HK-1"`. The migration is expand-only; the older code ignores the new tables and columns.

## Hand-off
Write `docs/reports/028-hk-<YYYY-MM-DD>.md` from `docs/templates/handoff-report.md` at the checkpoint, with each task's status, the migration number, the route mount, the reviewers' findings and the owner steps. Don't commit: the owner does. The next card is 029 (HK-2), which starts after this deploy; remove this worktree after the merge (`scripts/worktree.sh --remove hk/library`) so 029 can create `../clipForge-hk` on its branch.
