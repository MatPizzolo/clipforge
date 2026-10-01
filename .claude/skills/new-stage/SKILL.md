---
name: new-stage
description: Scaffold a new pipeline stage following the stage conventions (CLAUDE.md rules 1–7). Use when a card asks for a new stage in src/clipforge/stages/.
argument-hint: <stage_name> <one-line purpose>
---

Create a new pipeline stage: $ARGUMENTS

Follow CLAUDE.md rules 1–7. Copy the shape of an existing stage (`stages/ingest.py` is the shortest).
- `src/clipforge/stages/<name>.py` with a module-level `STAGE_VERSION = "1"` and one entry point: `run(ctx: JobContext, <inputs>, deps) -> Stored[<Output>]`. It never imports Modal.
- Add the input and output pydantic models to `models.py` first (rule 2).
- Cache (ADR-8): build the key with `hashing.cache_key("<name>", STAGE_VERSION, ...)` from the narrowest inputs that decide the output, and wrap the work in `jobs.cached_stage(ctx, StageName.<NAME>, key, <Output>, compute)`. It skips the work when a valid `result.json` exists. Bump `STAGE_VERSION` whenever the output changes.
- Call `ctx.report(stage, pct, message)` at meaningful progress points. Record cost inside `compute` with `ctx.record_cost(StageCost(stage=StageName.<NAME>, ...))` (GPU seconds, LLM tokens, rule 7).
- Add `tests/stages/test_<name>.py` using fixtures in `tests/fixtures/`; mark GPU tests `gpu` and network/LLM tests `slow`.
- Wire it in:
  - add it to `StageRunner` (`pipeline/deps.py`), `PipelineStages` and `STAGE_VERSIONS` (`stages/runner.py`; the latter feeds `producer_version`, ADR-43);
  - add a step in `src/clipforge/pipeline/steps.py` (or call it from an existing one, as `clip_step` does);
  - add its Modal function in `src/clipforge/app.py` if it is a new step;
  - add a row to the "Stages and contracts" table in `docs/ARCHITECTURE.md`.
