# Card 033: S5 (S5-3) — media protocols, the model registry, the media stages and renderer additions

Status: proposed
Stream: S5 (S5-3) · Branch: `s5/media` · Worktree: `../clipForge-s5` (created with `scripts/worktree.sh s5/media`)
Decision-log range: #680–#719 (append only; shared in sequence by cards 031–034: re-read the log and take the next free number)
Model: mid-tier (implementing a written plan); most capable for Task 10 (the render graph and the pinned clip keys)
Depends on: card 032 (S5-2) **deployed** with its owner steps done. **It deploys alone** (log #601), with the bookworm render run, `smoke` and one real channel job, because it changes `render_graph`, `captions` and `doctor` on the live clip path. Per log #144, no other code card is on `main` undeployed when this one merges
Cost cap: $0.25 of Modal/API spend (log #605; fast tests and a local Docker bookworm run; the owner's `doctor --skip-gpu`, `smoke` and one short channel job count)

## Context
Cards 031 and 032 deployed the `modal_app/` split and the registry with one engine (clips unchanged; `hello` refused with 422 until S5-4). **This card builds S5-3, plan Tasks 7–11:** the Modal-free `media/` package (contracts, protocols, fakes, and `src/clipforge/media/registry.toml` with its license-allowlist test, ADR-30), the `narrate` stage with X1's guard and word timings, the `stills` and `music` stages, the renderer additions X4 asked for (crossfades, a duck depth, the bed level relative to the voice), `captions.for_words`, and an ffmpeg filter check that runs inside the Modal base image. **No live change:** no producer calls the new stages yet, and every clip Timeline keeps its key and graph.

Rulings that bind this card:
- **Clip output doesn't change** (#581): new fields are optional, defaults leave clip Timelines' keys and graphs unchanged (`render.key` drops `transition_in` and `duck_db` when `None`), and `render.STAGE_VERSION` stays "4". **If a golden or pinned clip test moves, stop and ask** (a bump opens ADR-49's window).
- **The bed level** (#595): `ProducedStyle.bed_gain_db(narration_lufs, bed_lufs)` = `(narration LUFS − 16) − bed LUFS`; `duck_db` (6 dB) is the extra dip while a line is spoken.
- **Crossfades** (#596): real frames where the media has them, clones only for the shortfall; every part normalized (`fps`, `settb=AVTB`, `format=yuv420p`, `setsar=1`) before `xfade` (ffmpeg 5.1 needs it).
- **A narration line failing the guard twice** is a `PermanentError` naming the line and the reason (#587); Kokoro is a model-level fallback only.
- **S4's loudness-mode label fix stays deferred** (#593). Two S4 minors (the `%` in a still's path, short b-roll padding) are fixed here; the 1 ms rounding only if the golden strings stay identical.
- **No LLM tracing** (#597): no Langfuse code, no `LLMClient` change. S5 adds no secret.

## Read first
1. `CLAUDE.md`, `STATUS.md`
2. The S5 plan: Global Constraints, Review Focus (3 is S5-4's; 4 and 5 pin here), File map, Part S5-3 (Tasks 7–11, the owner deploy steps and the rollback)
3. The S5 spec §3 (narration, X1's guard), §4 (the registry), §8 (renderer additions), §9.2
4. `docs/DECISIONS.md`: ADR-8, ADR-20, ADR-30, ADR-31, ADR-47, ADR-49
5. Log rows #580–#582, #587, #589, #593, #595, #596, #601, #605, #148
6. `docs/studio/03-tools-and-models.md` (the license allowlist), the X1 and X4 spike reports in `docs/studio/spikes/`, and card 032's report
7. The code it changes: `models.py`, `stages/render_graph.py`, `stages/render.py`, `stages/captions.py`, `doctor.py`, `modal_app/entrypoints.py`, `pyproject.toml` (package data for `registry.toml`), `tests/stages/helpers.py`

## Scope
- May edit, as `scripts/scopes.toml` allows for `s5/`: `src/**` (including `src/clipforge/media/registry.toml`), `tests/**`, `pyproject.toml` (package data only; **no new dependency in `uv.lock`**), `docs/ARCHITECTURE.md`, `CLAUDE.md` (Layout: `media/`), `docs/studio/03-tools-and-models.md` (only if a registry pin needs its row corrected), `docs/superpowers/plans/*studio-s5*`, `docs/studio/04-roadmap.md` and `ROADMAP.md` (the S5-3 tick only after the owner confirms the deploy), `scratch/s5/**` (gitignored probes), its own report, and log rows in #680–#719.
- Must not edit: `render.STAGE_VERSION`, any existing golden render string or pinned key, released prompts, `alembic/`, the S5 spec, `STATUS.md`, other cards.
- **Only `app.py` and `modal_app/` import `modal`**; `media/` and the stages never do. **The session never deploys, stops the app, changes a secret or touches the `clipforge-models` Volume.**

## Actions
Each task follows the plan: failing tests first, then the implementation, then its checks, then "check and record".
1. **Task 7, `media/`:** the media contracts in `models.py`, `media/protocols.py`, `media/fakes.py`, `media/registry.py` and `registry.toml` (repos, full revision SHAs, weights, code and dependency licenses, each server's GPU, memory, snapshot mode, window, container cap, `max_batch_items`, `item_s`), with the license test (banned, unknown, `review` without `owner_ruling`, GPL-3.0 without its server-only `condition`, short SHA).
2. **Task 8, `narrate` and X1's guard:** per line, `seed` then `seed + 1`; the guard's duration and WER checks; words snapped and mapped; one `StageCost`; `ctx.report` per line; Review Focus 5 (`test_guard_accepts_short_lines`).
3. **Task 9, `stills` and `music`:** cached stages over the fakes, one report per image or bed, one `StageCost` each; beds normalized to -20 LUFS with the fades.
4. **Task 10, renderer additions:** `Crossfade`, `transition_in`, `duck_db`, `ProducedStyle`, the `Timeline` validators (Review Focus 4: `test_crossfade_longer_than_a_neighbour_is_rejected`), `render_graph` and `render.key`; the existing golden tests untouched; then the render tests locally and **in bookworm** (the plan's `docker run … python:3.12-bookworm` command; paste the summary).
5. **Task 11, `captions.for_words` and the filter check:** `ProducedCaptions`, `doctor.FILTERS` and `ffmpeg_filter_check()`, the `filter_doctor` function in `modal_app/` and its line in the `doctor` entrypoint.
6. **Checkpoint S5-3:** `scripts/check.sh` green; update `docs/ARCHITECTURE.md` (media protocols and the registry; the Timeline's new fields) and `CLAUDE.md`; `pr-reviewer` and `pipeline-reviewer` (stages, cache keys, the render graph, `STAGE_VERSION`, cost and progress); fix what they find; the report with the bookworm summary and the owner steps below; stop.

Stop for the owner at the checkpoint below.

## Checkpoints
- A (S5-3): after actions 1–6. Suggested commit: `033: s5-3: media protocols, model registry, narrate/stills/music stages, renderer additions`

## Done when
- `scripts/check.sh` is green (paste its summary lines into the report).
- The bookworm run of `test_render_graph.py`, `test_render_timeline.py` and `test_render_keys.py` passes (summary in the report).
- `pr-reviewer` and `pipeline-reviewer` have no blocking findings, and the report lists what each said.
- Every pre-existing golden render string and pinned clip key is unchanged, and `render.STAGE_VERSION` is "4".
- The license test fails on each banned case and passes on `registry.toml`.

## Owner steps
- Before: card 032 deployed; nothing else undeployed on `main`. `scripts/worktree.sh s5/media`, open a session in `../clipForge-s5`, paste `Run card docs/cards/033-s5-media.md`.
- At A: commit with the suggested message, `git push -u origin s5/media`, `gh pr create --fill`, squash-merge when CI is green.
- Deploy (its own deploy, #601; from `main`, after the merge, outside the blackout):
  1. The bookworm run is green in the card's report.
  2. **Pre-deploy check (#144, #145):** no other code card on `main` undeployed (`docs/ops/deploys.md` against `git log`); `scripts/deploy.sh --dry-run`, then `scripts/deploy.sh --reason "S5-3: media stages and renderer additions (clip output unchanged)"`.
  3. `uv run modal run src/clipforge/app.py::doctor --skip-gpu`: the "Modal base image" filter check is ok.
  4. `uv run modal run src/clipforge/app.py::smoke`: `smoke OK`.
  5. One real channel job on a short video (`uv run clipforge clip videos/<channel>/<file>`): it finishes, its clips are queued, and a clip rendered before the deploy is served from the render cache (`StageCost.cached` true in `metadata.json`), proving the key didn't move.
  6. Commit the deploy line in `docs/ops/deploys.md`, and tell the coordinator.
- **Rollback:** a revert deploy (`git revert` of the merge, `scripts/deploy.sh --dry-run`, `scripts/deploy.sh --reason "revert S5-3"`); no cache entry was written under a changed key.

## Hand-off
Write `docs/reports/033-s5-<YYYY-MM-DD>.md` from `docs/templates/handoff-report.md` at the checkpoint, with each task's status, the bookworm summary, the reviewers' findings and the owner steps. Don't commit: the owner does. The next card is 034 (S5-4), after this deploy; remove this worktree after the merge (`scripts/worktree.sh --remove s5/media`).
