# Card 032: S5 (S5-2) — the producer registry and one engine (clips unchanged)

Status: proposed
Stream: S5 (S5-2) · Branch: `s5/registry` · Worktree: `../clipForge-s5` (created with `scripts/worktree.sh s5/registry`)
Decision-log range: #680–#719 (append only; shared in sequence by cards 031–034: re-read the log and take the next free number after card 031's rows)
Model: most capable (the engine refactor under a golden test, `producer_version`, revertable records)
Depends on: card 031 (S5-1) **deployed** with its owner steps done. It lands as its own code card **between two deployed cards** and never while card 025 (S3-4 Produce) or ADR-48's spend-caps change in `create_job` is open (log #603): the coordinator slots it. Per log #144, no other code card is on `main` undeployed when this one merges
Cost cap: $0.25 of Modal/API spend (log #605; the session needs no Modal run; the owner's `smoke` and one short channel job count)

## Context
Card 031 deployed S5-1: the Modal app lives in `modal_app/`, and only `app.py` and `modal_app/**` import `modal`. **This card builds S5-2, plan Tasks 2–6:** producers become data (`producers/registry.py`: each producer's `StepDef`s and handlers), and one Modal-free engine (`pipeline/engine.py`, from `steps.py`) runs the guard, hand-off, fan-out, fan-in, failure path, resume and sweeper for every producer. Clips run on it **unchanged**: step names, Modal function names and timeouts, Dict keys, cache keys, `producer_version` and output (spec §6.4). A `hello` producer proves the pattern on CPU; its GPU step stays unbound until S5-4, so `POST /jobs {"producer": "hello"}` answers 422 "producer 'hello' isn't deployed yet" (#604). No migration.

Rulings and reviews that bind this card:
- **Globally unique step ids** (#590, #598): clips keep `ingest` … `package`; other producers' steps are `<producer>.<step>`; `spawn` and `dispatch` keep today's signatures.
- **Revertable records** (#599): `JobInput.producer`/`params` and `Job.producer`/`waiting_for` are left out of every dump while they hold their defaults (`Field(exclude_if=…)`), so a clips record keeps today's JSON shape and a revert deploy reads it; a test checks dumps against today's field sets.
- **The golden run** (#600): captured on `main` **before** the refactor with `python -m tests.pipeline.golden_clips` (raw Dict records, spawns, the cache listing, the whole `metadata.json`, ids and times masked); the test fails when the golden file is missing and never rewrites it.
- **The pinned `producer_version`** (#592, #602): the value `runner.producer_version` gives on `main` at this card's start, recorded in the report first (`clips:4c44b731` on 2026-10-03; it may differ if HK-2's flag or another card changed it), then pinned in `tests/pipeline/test_engine.py`; `runner.CLIPS_STAGES` fixes the seven clip stages.
- **Queued is not stalled** (#594): `Job.waiting_for` and the sweeper's two bounds.
- If card 029 (HK-2) deployed first, `clip_step`'s hook pick and `rerender_step` move with the clips handlers unchanged; the golden run captures them.

## Read first
1. `CLAUDE.md`, `STATUS.md`
2. The S5 plan: Global Constraints, Review Focus (1 and 2 pin here), File map, Part S5-2 (Tasks 2–6, the landing note, the owner deploy steps and the rollback)
3. The S5 spec §5.2 (queued vs stalled), §6 (the registry, the engine, §6.4 clips unchanged), §9.2–§9.3
4. `docs/DECISIONS.md`: ADR-8, ADR-12, ADR-14, ADR-15, ADR-43, ADR-49
5. Log rows #585, #590, #592, #594, #598–#605, #144, #148
6. Card 031's report, and the reports of any card deployed since that touched `steps.py`, `runtime.py` or `service.py`
7. The code it changes: `models.py`, `pipeline/steps.py`, `pipeline/deps.py`, `runtime.py`, `service.py`, `cli.py`, `api/main.py`, `stages/runner.py`, `modal_app/pipeline.py`, `tests/pipeline/harness.py`

## Scope
- May edit, as `scripts/scopes.toml` allows for `s5/`: `src/**`, `tests/**`, `web/openapi.json` and `web/lib/api/**` (regenerated if `POST /jobs`'s schema changes), `docs/ARCHITECTURE.md`, `CLAUDE.md` (Commands: `clipforge run --producer`; Layout: `producers/`, `pipeline/engine.py`), `docs/superpowers/plans/*studio-s5*`, `docs/studio/04-roadmap.md` and `ROADMAP.md` (the S5-2 tick only after the owner confirms the deploy), its own report, and log rows in #680–#719.
- Must not edit: stage modules' behavior (`render.STAGE_VERSION` and every cache key stay; if a golden or pinned clip test moves, stop and ask), `alembic/` (no migration), `pyproject.toml`/`uv.lock` (no new dependency), the S5 spec, `STATUS.md`, other cards.
- **Only `app.py` and `modal_app/` import `modal`.** **The session never deploys, stops the app or changes a secret.**

## Actions
Each task follows the plan: failing tests first, then the implementation, then its checks, then "check and record".
1. **Before any code:** record `runner.producer_version` on `main` (the plan's one-liner) in the report, and capture the golden run (`python -m tests.pipeline.golden_clips`) on the unchanged code.
2. **Task 2, contracts:** the new `StageName` members, `JobInput.producer`/`params` and `Job.producer`/`waiting_for` with `exclude_if`, `StageCost.cold_start_s`, `HelloParams`, `HelloResult`, `ProducedMetadata`; the frozen field-set test (#599); regenerate `web/openapi.json` and the client.
3. **Task 3, the registry:** `producers/registry.py` (`StepDef`, `Producer`, `register`, lookups) and the clips step list.
4. **Task 4, the engine, and clips on it:** `pipeline/engine.py`, `producers/clips.py` (today's bodies as handlers), `steps.py` as a compatibility module, `MediaKit`, `FunctionSpawner` keyed by step id, `modal_app/pipeline.py`'s `_spawner()`; the golden test, the pinned `producer_version`, Review Focus 1 (`test_old_job_record_without_producer_finishes_as_clips`); every existing chain and recovery test unchanged.
5. **Task 5, `create_job` by producer:** unknown producer and bad `params` → `InvalidJobInput` → 422; `Spawner.bound` and the "isn't deployed yet" refusal (#604); `clipforge run --producer hello [--param …]`; Review Focus 2 (`test_producer_input_rules_reject_mixed_inputs`).
6. **Task 6, the hello producer:** `producers/hello.py`, `stages/hello.py`, `HelloGpu`, `produced_cpu_step` and `produced_bindings()` in `modal_app/pipeline.py`; `test_every_cpu_step_is_bound`.
7. **Checkpoint S5-2:** `scripts/check.sh` green; update `docs/ARCHITECTURE.md` (the registry and engine) and `CLAUDE.md`; `pr-reviewer`, `pipeline-reviewer` (the engine, cache keys, `producer_version`, ADR-49) and `security-reviewer` (`POST /jobs`'s new `producer`/`params` input); fix what they find; the report with the recorded `producer_version` and the owner steps below; stop.

Stop for the owner at the checkpoint below.

## Checkpoints
- A (S5-2): after actions 1–7. Suggested commit: `032: s5-2: producer registry and one engine (clips unchanged)`

## Done when
- `scripts/check.sh` is green (paste its summary lines into the report).
- `pr-reviewer`, `pipeline-reviewer` and `security-reviewer` have no blocking findings, and the report lists what each said.
- The golden clips test passes against the file captured before the refactor, and `producer_version` equals the value recorded at the start.
- Clips records dump with today's field sets (#599); `POST /jobs {"producer": "hello"}` answers 422 with "isn't deployed yet".

## Owner steps
- Before: card 031 deployed; the coordinator has slotted this card (no card 025 or caps change open, nothing undeployed on `main`). `scripts/worktree.sh s5/registry`, open a session in `../clipForge-s5`, paste `Run card docs/cards/032-s5-registry.md`.
- At A: commit with the suggested message, `git push -u origin s5/registry`, `gh pr create --fill`, squash-merge when CI is green.
- Deploy (from `main`, after the merge, outside the blackout):
  1. **Pre-deploy check (#144, #145):** no other code card is on `main` undeployed (`docs/ops/deploys.md` against `git log`).
  2. `scripts/deploy.sh --dry-run`, then `scripts/deploy.sh --reason "S5-2: producer registry and engine (clips unchanged)"`.
  3. `uv run modal run src/clipforge/app.py::smoke`: `smoke OK`.
  4. One real channel job on a short video (`uv run clipforge clip videos/<channel>/<file>`): it finishes, its clips are queued (`uv run clipforge status`), and `metadata.json`'s `producer_version` equals the previous job's.
  5. Commit the deploy line in `docs/ops/deploys.md`, and tell the coordinator.
- **Rollback:** a revert deploy (`git revert` of the merge, `scripts/deploy.sh --dry-run`, `scripts/deploy.sh --reason "revert S5-2"`). Step ids, Modal function names and Dict keys are unchanged, so jobs in flight finish under either version.

## Hand-off
Write `docs/reports/032-s5-<YYYY-MM-DD>.md` from `docs/templates/handoff-report.md` at the checkpoint, with the recorded `producer_version`, each task's status, the reviewers' findings and the owner steps. Don't commit: the owner does. The next card is 033 (S5-3), after this deploy; remove this worktree after the merge (`scripts/worktree.sh --remove s5/registry`).
