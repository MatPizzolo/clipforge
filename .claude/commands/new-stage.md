---
description: Scaffold a new pipeline stage following the stage conventions
argument-hint: <stage_name> <one-line purpose>
---

Create a new pipeline stage: $ARGUMENTS

Follow CLAUDE.md rules 1–7:
- `src/clipforge/stages/<name>.py` with a single `run(input: <InputModel>, job: JobContext) -> <OutputModel>` function.
- Add input/output pydantic models to `models.py`.
- Cache by input hash + stage version; skip if output exists.
- Call `ctx.report(stage, pct, message)` at meaningful progress points; record cost with `ctx.record_cost(...)`.
- Add `tests/stages/test_<name>.py` using fixtures in `tests/fixtures/`; mark GPU/slow tests.
- Wire it into the orchestrator and update the stage table in docs/ARCHITECTURE.md.
