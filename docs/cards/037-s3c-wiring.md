# Card 037: S3c (S3c-2) — the clip producer reads the setup

Status: proposed
Stream: S3c (S3c-2) · Branch: `s3c/wiring` · Worktree: `../clipForge-s3c` (created with `scripts/worktree.sh s3c/wiring`)
Decision-log range: #250–#299 (append only; shared in sequence by cards 035–038: re-read the log and take the next free number)
Model: most capable (`create_job`, per-job prompts and `producer_version`, the captions cache key, the format window)
Depends on: card 036 (S3c-1b) **deployed** with its owner steps done, and card 014 (S2a, which defines `FormatWindowSource` and `ReviewRepo(db, format_source=…)`) deployed (it is, since 035 needed it; log #142, #261, #263). Per log #144, no other code card is on `main` undeployed when this one merges. The `SETUP_SOURCE=db` switch is a separate owner redeploy after this card's deploy
Cost cap: $2 of Modal/API spend (fast tests with the LLM mocked; no Modal runs needed). The owner's deploys and one channel job are not session spend

## Context
Cards 035 and 036 deployed the versioned setup, its routes and the workspaces, with `SETUP_SOURCE=off` (jobs still use today's constants). **This card builds S3c-2, plan Tasks 11–16:** `create_job` reads the account's effective setup and stamps `JobInput.setup` (account, version, prompts, language) and the `ClipOptions`; prompts load by name per job and `producer_version(settings, prompts)` follows them (equal to today's for the defaults); the caption preset enters the captions key only when not `default`; a job whose detected language differs from the account's is held (never a Whisper hint, #254); items record `setup_version` and sends are attributed by time (`SetupRepo.version_at`), so no posting writer changes; `SetupRepo.format_window` is wired as S2's `FormatWindowSource` in `runtime.build_deps` only (#142, #261); and the Framing & captions tab with the last-frame link.

What to watch:
- **Clips must not change with `SETUP_SOURCE=off` or with the defaults:** the captions key, `producer_version` and every cache key stay pinned; `setup_version` is in no cache key (ADR-42).
- **If card 032 (S5-2) is deployed**, `highlights_step`'s body lives in `producers/clips.py` and `runner.producer_version` is frozen to clips' seven stages (#592, #602): the hold goes in the clips handler, and `producer_version(settings, prompts)` must keep S5's pinned value for the default prompts (the pinned test must not move; if it would, stop and ask).
- **If card 029 (HK-2) is deployed**, the captions key already carries the hook pick and the flag's stage version: add the preset alongside without changing the flag-off key.
- The last-frame still goes in `/jobs/frames/<item>.jpg` with a Volume commit, its item id validated before any path is built (review finding 8).

## Read first
1. `CLAUDE.md`, `STATUS.md`
2. The S3c plan: Global Constraints, Review Focus 3, Part S3c-2 (Tasks 11–16, the owner steps and the rollback)
3. The S3c spec §3.1–§3.3 (jobs and items), §3.5 (the format window), §5.6 (`SETUP_SOURCE`), §2.5 (Framing & captions)
4. The S2 plan's Task 6 as amended (`FormatWindowSource`, `NoFormatWindow`, `WindowCounts.format_version`)
5. `docs/DECISIONS.md`: ADR-8, ADR-29, ADR-42, ADR-43, ADR-49
6. Log rows #142, #254, #260, #261, #263, #592, #602, #144, #148
7. Cards 035's and 036's reports, and those of cards 029 and 032 if deployed
8. The code it changes: `models.py`, `service.py`, `stages/runner.py`, `stages/captions.py`, `pipeline/steps.py` (or `producers/clips.py`), `posting/enqueue.py`, `db/posting.py`, `db/setup.py`, `runtime.py`, `api/admin/setup.py`, `web/components/account/`

## Scope
- May edit, as `scripts/scopes.toml` allows for `s3c/`: `src/**`, `tests/**`, `.env.example` (the `SETUP_SOURCE` note), `docs/ops/secrets.md` (the `SETUP_SOURCE` row: a setting in `clipforge-secrets`, missing = `off`), `web/**` (the Framing & captions tab, Style's frame, `web/openapi.json` and `web/lib/api` regenerated), `docs/ARCHITECTURE.md`, `docs/superpowers/plans/*s3c*`, `docs/studio/04-roadmap.md` and `ROADMAP.md` (the S3c-2 tick only after the owner confirms the switch), `CLAUDE.md`, its own report, and log rows in #264–#299.
- Must not edit: any S2 module under `review/`, `dispatch/` or `posting/actions.py`, `needs/`, the hooks modules, `prompts/` (the setup only picks a released version), `alembic/` (no migration), the S3c spec, `STATUS.md`, other cards.
- **No new dependencies.** **Only `app.py` (and `modal_app/` once card 031 is deployed) imports `modal`**; stage modules stay Modal-free and DB-free. **The session never deploys, migrates Neon or changes a secret.**

## Actions
Each task follows the plan: failing tests first, then the implementation, then its checks, then "check and record".
1. **Task 11, `JobSetup` and `ContentItem.setup_version`** in `models.py` (additive); `web/openapi.json` regenerated.
2. **Task 12, `create_job` reads the setup:** `SetupReader`, `DbSetupReader`, per-job prompts in `PipelineStages`, `producer_version(settings, prompts=None)`, `runtime` passing the reader only with `SETUP_SOURCE=db`; Review Focus 3 (`test_create_job_without_current_version_uses_constants`), `test_create_job_off_ignores_setup`.
3. **Task 13, the preset in the captions key and the language hold:** `captions.cache_key_for(...)` (`test_default_preset_keeps_todays_key`, `test_setup_version_in_no_cache_key`); the hold message in the highlights step.
4. **Task 14, `setup_version` on items and sends by time:** `items_for`, `db/posting.py`'s insert and read, `SetupRepo.send_versions` (hand-off claim time).
5. **Task 15, the format window:** `SetupRepo.format_window`, wired as `ReviewRepo(db, format_source=SetupRepo(db))` in `build_deps` (`test_build_deps_wires_setup_repo_as_format_source`); no S2 module edited.
6. **Task 16, Framing & captions and Style's frame:** `GET /admin/accounts/{id}/last-frame` (a signed link; the still in `/jobs/frames/`, Volume commit), `FramingCaptionsTab.tsx`, the frame in `StyleTab.tsx`; `docs/ARCHITECTURE.md`, `.env.example`, `docs/ops/secrets.md`.
7. **Checkpoint S3c-2** (plan Task 16 step 5): `scripts/check.sh --e2e`; `pr-reviewer`, `pipeline-reviewer` (per-job prompts, `producer_version`, the captions key, the hold) and `security-reviewer` (the last-frame route: the signed link, ffmpeg in the API container, path checks); fix what they find; the report with the owner steps below; stop.

Stop for the owner at the checkpoint below.

## Checkpoints
- A (S3c-2): after actions 1–7. Suggested commit: `037: s3c-2: the clip producer reads the setup`

## Done when
- `scripts/check.sh` and `scripts/check.sh --e2e` are green (paste the summary lines into the report).
- `pr-reviewer`, `pipeline-reviewer` and `security-reviewer` have no blocking findings, and the report lists what each said.
- With `SETUP_SOURCE=off`, and with `db` and the default setup, every pinned cache key and `producer_version` equals today's.
- Review Focus 3 passes; the format window opens after a format change and closes after 10 counted decisions (`test_route_opens_then_closes_the_window`).

## Owner steps
- Before: card 036 deployed; nothing else undeployed on `main`. `scripts/worktree.sh s3c/wiring`, open a session in `../clipForge-s3c`, paste `Run card docs/cards/037-s3c-wiring.md`.
- At A: commit with the suggested message, `git push -u origin s3c/wiring`, `gh pr create --fill`, squash-merge when CI is green.
- Deploy (from `main`, after the merge, outside the blackout):
  0. **The #144 check:** no other code card is on `main` undeployed (`docs/ops/deploys.md` against `git log`); `uv run modal run src/clipforge/app.py::db_doctor` shows the expected head (S3c-2 adds no migration).
  1. `scripts/deploy.sh --dry-run`, then `scripts/deploy.sh --reason "S3c-2: setup wiring (SETUP_SOURCE still off)"`.
  2. `uv run clipforge setup verify`: `0 differences`.
  3. **The switch (a separate redeploy):** add `SETUP_SOURCE=db` to `clipforge-secrets` with `docs/ops/secrets.md`'s add-only procedure, then `scripts/deploy.sh --dry-run` and `scripts/deploy.sh --reason "SETUP_SOURCE=db"`.
  4. Clip one episode (`uv run clipforge clip videos/<source>/<file> --fetch`): `uv run clipforge status <job>` shows the job's setup version; the clips match the account's lengths; the queued items carry `setup_version`.
  5. Commit the deploy lines in `docs/ops/deploys.md`, and tell the coordinator.
- **Rollback:** remove `SETUP_SOURCE` from the secret (back to `off`) and redeploy; jobs return to today's constants and stamped items keep their version. The whole part: `git revert` of the merge, `scripts/deploy.sh --dry-run`, `scripts/deploy.sh --reason "revert S3c-2"`.

## Hand-off
Write `docs/reports/037-s3c-<YYYY-MM-DD>.md` from `docs/templates/handoff-report.md` at the checkpoint, with each task's status, the reviewers' findings and the owner steps. Don't commit: the owner does. The next card is 038 (S3c-3), once this and card 016 (S2c) are deployed; remove this worktree after the merge (`scripts/worktree.sh --remove s3c/wiring`).
