# Card 029: HK (HK-2) — hook variants behind `HOOK_VARIANTS`, ranking, ratings and re-render

Status: proposed
Stream: HK (HK-2) · Branch: `hk/variants` · Worktree: `../clipForge-hk` (created with `scripts/worktree.sh hk/variants`)
Decision-log range: #550–#579 (append only; shared in sequence by cards 028–030: re-read the log and take the next free number after card 028's rows)
Model: most capable (captions cache keys and `producer_version`, the clip step, re-render's Dual-written supersede)
Depends on: card 028 (HK-1) **deployed** with its owner steps done (`db_doctor` shows the hooks head; `clipforge hooks seed` ran). Per log #144, no other code card is on `main` undeployed when this one merges. The parts that need cards 015, 016, 022, 023 and 024 use the plan's fallbacks where those cards aren't deployed (Context). The `HOOK_VARIANTS` flip is a separate owner redeploy after this card's deploy
Cost cap: $2 of Modal/API spend (fast tests with the LLM mocked; at most a few real `keywords_v3` calls if a prompt check needs one). The owner's deploys, the flag flip and one channel job (about $0.0025 of Haiku per clip) are not session spend

## Context
Card 028 deployed HK-1: the hook tables, six seeded patterns per clips account, the rotation frozen on each job, control stamps on items and in `metadata.json`, the `/admin` hooks routes and `clipforge hooks`. Read card 028's report first (the migration number, where the routes were mounted). **This card builds HK-2, plan Tasks 7–11:** the shared variants interface, `prompts/keywords_v3.md` in captions behind `HOOK_VARIANTS` (default off), the pick in the clip step, ranking with ratings and the weak-pattern rows, and re-rendering one item (G21, #557, #562).

**Deployed-card fallbacks (plan Global Constraints, #144, #562).** At the start, check `docs/ops/deploys.md` and record in the report which of these is deployed; each missing one uses its fallback:

| Needs | Fallback when it isn't deployed |
|---|---|
| card 015 (S2b: `posts.state`, `publishing:inflight:<ref>`) | re-render's refusal checks `posted_at` only and says so in a code comment; the in-flight checks are added, with a test, by the first hooks or later card after 015 deploys (tell the coordinator) |
| card 016 (S2c: the digest's `DigestProvider` tuple) | `hooks/digest.py`'s providers ship with their tests, unregistered; no digest lines until 016 |
| card 022 (S3-1: `cli_router`, the `admin` endpoint) | the CLI's routes in `create_app` next to S2's `/admin/*` on `web`; the rating and re-render routes on `web` behind the bearer token; S3-1 moves them |
| card 023 (S3-2: the needs registry, `needs_providers`) | `HookWeakProvider` ships with its tests, unregistered |
| card 024 (S3-3: Review's re-render button) | the route works from the API and CLI tests; the button stays disabled until 024 |

Also:
- **S2's ladder and demotion counts and S3c's reject rate exclude `superseded:<id>` rejects** (spec §10.4, §10.6): if those modules are on `main`, add the exclusion with a test there; otherwise tell the coordinator.
- **If card 031 (S5-1) is deployed**, `rerender_step`'s Modal function goes in `modal_app/pipeline.py`, not `app.py`. **If card 032 (S5-2) is deployed**, `clip_step`'s body lives in `producers/clips.py` and a new step needs a registry `StepDef`: follow the engine's pattern (step id `rerender`, the clip step's timeout), and stop and ask the coordinator if the plan's sketch doesn't fit.
- **The flag flip (#555):** `HOOK_VARIANTS=true` changes every clips account's `producer_version` once and opens ADR-49's 5-item window per account (about 15 reviews). The owner flips it alone, right after this deploy, unless another clips stage or prompt bump is due the same week (#439).
- `prompts/keywords_v3.md` is new; `keywords_v2.md` is never edited (CLAUDE.md rule 4).

- **Follow-ups from the HK-1 post-deploy review (2026-10-06, coordinator; fix them in this card, each with a test):**
  1. `hooks seed` can seed an account twice when two runs overlap (`hooks/library.py:221` checks "no patterns yet" without a lock). Lock the account row (`SELECT … FOR UPDATE` on `accounts`) before the check.
  2. `POST /admin/hooks/seed` writes as `system:migration` with no person (`api/main.py:282`). Require `person` and record the caller in the `seeded` event's data (ADR-48: `system:` only when nobody tapped).
  3. The hook routes answer a bare 500 on `IntegrityError` or a lock timeout. Map those to 409 or 503 with a clean message.
  4. `HookSeedRequest.account_ids` has no length cap.
  5. Index `hook_events.account_id` in the next migration that lands (S3 or S3c), or here if this card adds one.
  6. `package` writes the hook metadata without a `STAGE_VERSION` bump (ADR-8's status note, log #564). This card adds `flag_on` to the package key.

## Read first
1. `CLAUDE.md`, `STATUS.md`
2. The hooks plan: Global Constraints, Review Focus (1–4 pin in this part), File map, Part HK-2 (Tasks 7–11, the owner deploy steps and the rollback)
3. The hooks spec: §2 (variants, the prompt, the flag), §3.2, §5 (ranking), §6 (re-render), §7, §10.4–§10.6
4. `docs/DECISIONS.md`: ADR-8, ADR-15, ADR-18, ADR-20, ADR-41, ADR-43, ADR-49, ADR-50
5. Log rows #550–#562, #142, #144, #147, #148 and card 028's rows
6. Card 028's report; the reports of whichever of cards 015, 016, 022, 023, 024, 031 and 032 are deployed
7. The code it changes: `stages/captions.py`, `stages/runner.py`, `stages/package.py`, `pipeline/steps.py`, `posting/enqueue.py`, `posting/actions.py`, `posting/repo.py`, `db/posting.py`, `db/hooks.py`, `runtime.py`, `app.py` (or `modal_app/pipeline.py`), `api/main.py` (or S3's routers), `cli.py`, `prompts/keywords_v2.md`, `prompts/metadata.json`
8. `docs/ops/secrets.md` (the add-only procedure), runbook §1

## Scope
- May edit, as `scripts/scopes.toml` allows for `hk/`: `src/**`, `tests/**`, `prompts/keywords_v3.md` (new) and `prompts/metadata.json` (its entry), `.env.example` (`HOOK_VARIANTS`), `web/openapi.json` and `web/lib/api/**` (regenerated), `docs/ARCHITECTURE.md`, `docs/ops/secrets.md` (the `HOOK_VARIANTS` row), `docs/superpowers/plans/*studio-hooks*` (ticks and a status line), `docs/studio/04-roadmap.md` and `ROADMAP.md` (HK-2 ticks only after the owner confirms the deploy), `CLAUDE.md`, its own report, and log rows in #563–#579.
- Must not edit: any released prompt (`keywords_v2.md`, `highlights_v*.md`, …), the hooks spec, `STATUS.md`, other cards, `alembic/` (HK-2 has no migration), `web/` beyond the two generated paths, `needs/` and `dispatch/digest.py` (register through `build_deps` only), `docs/studio/05` and `08`.
- **No new dependencies.** **Only `app.py` (and `modal_app/` once card 031 is deployed) imports `modal`.** Stage modules stay free of database and Modal code. **The session never deploys, migrates Neon or changes a secret.**

## Actions
Each task follows the plan: failing tests first, then the implementation, then its checks, then "check and record".
1. **Task 7, `hooks/variants.py`:** `render_task`, `valid_lines` (every line through `captions.title_words()`), `settle`.
2. **Task 8, `keywords_v3` and variants in captions:** `prompts/keywords_v3.md` and its `metadata.json` entry (`released`, `model_default: claude-haiku-4-5`, `notes`); `captions.stage_version(settings)` and `keywords_prompt(settings)`; `captions.run(..., pick, manual_title)` with the pick and the `manual:<sha16>` title as cache-key inputs; `runner.producer_version(settings)` from the two functions. Flag off stays byte-identical (pinned tests); Review Focus 3 (`test_line_empty_after_cleaning_is_invalid`); rule 5's single retry, then `fallback = true`.
3. **Task 9, the pick through clip, render, package and enqueue:** `clip_step` draws with `pick(job.input.hooks, clip_seed(...))` when the flag and a rotation are set; `RenderedClip.hook`, `PackagedClip.hook` and `title`, `ClipFacts.hook`; Review Focus 1 (`test_stamp_uses_the_version_frozen_on_the_job`) and 2 (`test_resume_of_a_pre_hk_job_runs_control_mode`).
4. **Task 10, ranking, ratings and the weak-pattern rows:** `hooks/stats.py` (Wilson 90%, 10-item floor, drawn items only, superseded excluded), `hooks/ratings.py`, `hooks/needs.py::HookWeakProvider`, `hooks/digest.py`; `GET /admin/hooks/{id}/stats`, `PUT /admin/items/{id}/hook-rating`, `clipforge hooks stats`; register the providers in `runtime.build_deps` only where cards 023 and 016 are on `main` (fallbacks above).
5. **Task 11, re-render one item:** `hooks/rerender.py` (`request` with the stale-claim rule, numbering over the base clip), `Step.RERENDER` and `rerender_step`, the Modal function, `posting/actions.supersede` (Dual-written: `repo.add` for the new item first, then the reject with reason `superseded:<new id>` and `superseded_by`), `set_verdict`'s optional `reason`, superseded items out of the eligible pick, S3's `POST /admin/review/{item}/rerender?preview=` (#619); re-render files under `<job_id>/rerender/<clip_id>r<N>/`, never in `metadata.json`; Review Focus 4 (`test_second_rerender_request_is_refused_while_the_first_runs`).
6. **Checkpoint HK-2** (plan Task 11 step 5): update `docs/ARCHITECTURE.md` (captions: hook variants, the flag, re-render), `.env.example`, `docs/ops/secrets.md` (`HOOK_VARIANTS`: a setting in `clipforge-secrets`, not a secret; missing = off), `CLAUDE.md` if commands changed; then `pr-reviewer`, `pipeline-reviewer` (captions, render inputs, `producer_version`), `migration-reviewer` (`posting/repo.py`, `db/posting.py`, the Dual write of `supersede`, `posting verify`) and `security-reviewer` (the new routes, LLM text into ASS); fix what they find; `scripts/check.sh` green; the report with the fallbacks in force and the owner steps below; stop.

Stop for the owner at the checkpoint below.

## Checkpoints
- A (HK-2): after actions 1–6. Suggested commit: `029: hk-2: keywords_v3 hook variants behind HOOK_VARIANTS, ranking, ratings, re-render`

## Done when
- `scripts/check.sh` is green (paste its summary lines into the report).
- `pr-reviewer`, `pipeline-reviewer`, `migration-reviewer` and `security-reviewer` have no blocking findings, and the report lists what each said.
- With the flag off, the captions stage version, prompt, cache key and `producer_version` equal today's (pinned); with it on, "4" and `keywords_v3`.
- Review Focus 1–4 tests pass; a crash between `repo.add` and `supersede` is finished by the step's retry (test).
- The report lists which of cards 015, 016, 022, 023 and 024 were deployed and the fallback used for each missing one, plus anything the coordinator must pick up (in-flight checks, provider registrations, the superseded exclusions).

## Owner steps
- Before: card 028 deployed with its owner steps; nothing else undeployed on `main`. `scripts/worktree.sh hk/variants`, open a session in `../clipForge-hk`, paste `Run card docs/cards/029-hk-variants.md`.
- At A: commit with the suggested message, `git push -u origin hk/variants`, `gh pr create --fill`, squash-merge when CI is green.
- Deploy (from `main`, after the merge, outside the blackout):
  0. **The #144 check:** no other code card is on `main` undeployed (`docs/ops/deploys.md` against `git log`). Note which of cards 015, 016, 022, 023 and 024 are deployed.
  1. `uv run modal run src/clipforge/app.py::db_doctor` (the hooks head, unchanged: HK-2 has no migration), then `scripts/deploy.sh --dry-run`, then `scripts/deploy.sh --reason "HK-2: hook variants (flag off)"`. Clip output is still unchanged.
  2. Check that no other clips stage or prompt bump is due this week (#439); if one is, ship them together instead.
  3. **The flag flip (a separate redeploy):** add `HOOK_VARIANTS=true` to `clipforge-secrets` with `docs/ops/secrets.md`'s add-only procedure (never `modal secret create --force`), then `scripts/deploy.sh --dry-run` and `scripts/deploy.sh --reason "HOOK_VARIANTS on"`. Expect ADR-49's 5-item window per clips account (about 15 reviews).
  4. Clip one episode. Its title cards show rewritten lines; `metadata.json` has `hook.result.variants`; `uv run clipforge hooks list realtalk-clips-en` shows items per pattern.
  5. `uv run clipforge hooks stats <pattern>`, and one re-render from the API (`POST /admin/review/<item>/rerender?preview=true`, then without `preview`).
  6. Commit the deploy lines in `docs/ops/deploys.md` and tell the coordinator: 030 needs this deploy and card 022's.
- **Rollback:** the variants only: remove `HOOK_VARIANTS` (or set it `false`) and redeploy; captions use their old keys and stamps go back to the control. `producer_version` returns to its previous value, which reopens ADR-49's window only for accounts with fewer than 5 counted decisions under the old version (#562). The whole part: `git revert` of the merge, `scripts/deploy.sh --dry-run`, `scripts/deploy.sh --reason "revert HK-2"`. No migration.

## Hand-off
Write `docs/reports/029-hk-<YYYY-MM-DD>.md` from `docs/templates/handoff-report.md` at the checkpoint, with each task's status, the fallbacks in force, the reviewers' findings and the owner steps. Don't commit: the owner does. The next card is 030 (HK-3) once this and card 022 are deployed; remove this worktree after the merge (`scripts/worktree.sh --remove hk/variants`).
