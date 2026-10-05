# Card 021: S5 — media servers and producer registry, spec and plan

Status: done 2026-10-05 (report: docs/reports/021-s5d-2026-10-05.md; PR #41)
Stream: S5 · Branch: `s5d/design` · Worktree: `../clipForge-s5d` (created with `scripts/worktree.sh s5d/design`)
Decision-log range: #580–#609 (append only, in this range; new prefix `s5d/`, log #141)
Model: most capable (design and plan, no code)
Depends on: **PR #33 merged** (card 012, the X4 report and its measured numbers); start the session only after that. The build (a later card) needs S4 (done), X1 (done) and X4, and lands after S1's rollout. Runs alongside 010 (rollout, don't touch production), 017, 018, 019, 020
Cost cap: $0 by default. Up to $5 of Modal measurement runs only if the spec needs a number no spike measured (for example a memory-snapshot cold start for one server, or a bf16 copy's load time); the report says why before the first run, every app is stopped at the end (`uv run modal app list` shows none of this card's apps running), and nothing touches the `clipforge` app

## Context
S5 builds what every generative producer needs (ADR-30): open media models as `modal.Cls` servers with weights on the `clipforge-models` Volume, Modal-free protocols in `media/`, a license-gated `media/registry.toml`, and a pipeline registry that drives `dispatch` and `resume` from per-producer step lists. 04's S5 list:
- `media/` protocols plus `registry.toml` with a license-allowlist test; the `clipforge-models` Volume with one-off weight-download functions;
- `modal.Cls` servers for TTS, aligner, image and music, with memory snapshots, `@modal.batched` (except TTS: Qwen3-TTS runs **unbatched behind the guard** until batching is re-tested under it, X1) and step methods inside the class (ADR-12: nothing waits idle);
- the pipeline registry; `app.py` splits into a `modal_app/` package (still the only Modal importer);
- LLM tracing in Langfuse;
- exit: the clip producer runs through the registry, and a no-op "hello" producer proves the GPU step pattern.

Inputs since 04 was written: **X1** (Qwen3-TTS primary, Kokoro fallback, the guard, measured cost and cold starts in `docs/studio/03-tools-and-models.md` and `docs/studio/spikes/x1-voice.md`) and **X4** (card 012: stills, b-roll and music models with their licenses, measured costs, the S6 producer rules, and two renderer requirements: a configurable duck depth and Timeline transitions; `docs/studio/spikes/x4-visuals-music.md` after PR #33). S4's deferred minors (the filter check outside the Modal image, `%` in a still's path, short b-roll padding, 1 ms rounding, the loudness-mode label boundary; STATUS follow-ups) are S5/S6's.

This card is design-and-plan only: checkpoint A is the spec, checkpoint B the plan. **Production is out of bounds today:** card 010 runs the S1 rollout's live steps at 22:00 New York time. Never deploy or stop the `clipforge` app, never touch `clipforge-secrets`, never run Alembic. Any measurement app has its own name (`clipforge-s5-probe`), and its probe code lives in `scratch/s5d/` (ignored once card 017 lands).

## Read first
1. `CLAUDE.md`, `STATUS.md`
2. `docs/DECISIONS.md`: ADR-8, 9, 12, 14, 15, 30, 31, 43, 47; `docs/studio/05-proposed-adrs.md` (ADR-32, 36, 37 drafts)
3. `docs/studio/04-roadmap.md` (S5, S6), `docs/studio/06-session-prompts.md` (the S5 and S6 cards), `docs/studio/02-target-architecture.md` (producers, media servers)
4. `docs/studio/03-tools-and-models.md` (the model table, the monthly cost model), `docs/studio/spikes/x1-voice.md`, `docs/studio/spikes/x4-visuals-music.md`, `docs/studio/spikes/x2-talking-head.md` (what S8 will add)
5. The S4 spec and plan (`docs/superpowers/specs/2026-10-01-studio-s4-timeline-design.md`, `docs/superpowers/plans/2026-10-01-studio-s4.md`): the Timeline contract, `render_graph.py`, `loudness.py`
6. The code it changes (read only): `app.py`, `runtime.py`, `pipeline/` (`deps.py`, `steps.py`), `jobs.py`, `stages/runner.py`, `models.py` (`Timeline`, `JobMetadata`, cost), `config.py` (`Prices`), `doctor.py`
7. Modal docs for `modal.Cls`, memory snapshots (GPU snapshots), `@modal.batched`, Volumes; Langfuse's Python SDK docs

## Scope
- May edit, as `scripts/scopes.toml` allows for `s5d/`: the spec `docs/superpowers/specs/*studio-s5*`, the plan `docs/superpowers/plans/*studio-s5*`, `docs/studio/03-tools-and-models.md` (measured numbers only), `docs/studio/04-roadmap.md` (the S5 section), `docs/studio/05-proposed-adrs.md`, probe code under `scratch/s5d/**`, its own report, and log rows #580–#609.
- Must not edit: code, tests, `alembic/`, `docs/DECISIONS.md`, other specs and plans (propose changes to the S4 or S6 documents in the spec's last section), other cards.

## Actions
1. **Questions first** (superpowers:brainstorming, one at a time, options with a recommendation). At least:
   - which servers S5 builds (TTS and aligner for S6 for sure; image and music from X4's picks; b-roll now or in S6);
   - the renderer additions X4 asks for (duck depth, transitions): in S5, so S6 starts on a finished renderer, or in S6 with its first use;
   - batching b-roll and stills per account per day (one container session per batch) versus per item, given cold-start costs;
   - the `app.py` split into `modal_app/`: in S5 as 04 says, or a separate refactor card first so S5's diff stays reviewable;
   - Langfuse: hosted (keys as secrets) or deferred; what is traced (prompt version, model, tokens, cost);
   - whether the $5 of measurement is needed, and for which number.
2. **Write the spec** `docs/superpowers/specs/2026-10-0X-studio-s5-design.md`, approved section by section:
   - the `media/` protocols (`Tts`, `Aligner`, `ImageGen`, `MusicGen`, `BRoll` as needed), Modal-free, with fakes for fast tests;
   - `media/registry.toml`: model id, pinned revision, license, allowlist, GPU, and the test that fails on a license outside the allowlist (ADR-30's non-commercial list);
   - each `modal.Cls` server: GPU, weights on `clipforge-models` (bf16 copies where X4 measured them), memory snapshots, `@modal.batched` or not (TTS unbatched behind the guard), step methods inside the class, scaledown, the cold-start cost per call and per batch;
   - the weight-download functions and the Volume layout (and X2's ~227 GB already there);
   - the pipeline registry: per-producer step lists, how `dispatch` and `resume` read them, how the clip producer moves onto it with identical behaviour (cache keys and `producer_version` unchanged, ADR-43), and the "hello" producer;
   - cost recording (rule 7: GPU seconds per server call in `JobMetadata`), errors (ADR-15) and the stall sweeper's per-step timeouts;
   - the renderer additions, if the owner puts them in S5 (Timeline contract change first, rule 2; `render.STAGE_VERSION` and the ADR-49 window this opens);
   - tests and safety, rollback, monthly cost against 03's scenarios;
   - the last section: proposed changes to 03, 04, 06 and the S4/S6 documents.
   Stop for the owner's review (checkpoint A).
3. **After approval, write the plan** `docs/superpowers/plans/2026-10-0X-studio-s5.md` in the S2 plan's structure (`docs/superpowers/plans/2026-10-02-studio-s2.md`): Global Constraints (only the Modal package imports `modal`; stage modules stay Modal-free; no license outside the allowlist; every spike or probe app stopped), Review Focus, a File map, tasks with failing tests first and exact signatures, deployable checkpoints with owner steps (`doctor`, the weight downloads, `scripts/deploy.sh --dry-run`, deploy, the hello producer run, `smoke`) and the rollback, and a coverage table against 04's S5 list. S5 adds no database tables; if a task needs one, its migration number is assigned at landing (S3 dashboard spec §8.7).
4. Record measured numbers in 03 (if any were measured), apply the S5-only changes to 04's S5 section, and put any new ADR draft in 05 (the next free ADR number is in log #138).
5. `scripts/check.sh` green (`--docs --scope` at A, the full gate at B), the report with the spend and the stopped apps, log rows in range for the owner's rulings, and stop at checkpoint B.

## Checkpoints
- A: actions 1–2. Suggested commit: `021: s5d: media servers and producer registry design spec`
- B: actions 3–5. Suggested commit: `021: s5d: implementation plan`

## Done when
- The owner approved the spec at A and the plan at B.
- The plan's coverage table maps every item of 04's S5 list to a task with its tests, and names which parts deploy alone.
- Spend is at most $5 and explained in the report, and no measurement app is left running.
- `scripts/check.sh` is green (paste its summary lines).

## Owner steps
- Before: PR #33 merged. `scripts/worktree.sh s5d/design`, open a session in `../clipForge-s5d`, paste `Run card docs/cards/021-s5-media-design.md`.
- During: answer the questions in action 1; approve any measurement run before it starts.
- At each checkpoint: commit, push (`git push -u origin s5d/design` the first time), keep one PR open until B, squash-merge after B.
- After: a Hugging Face token if a chosen model is gated, and Langfuse keys if the spec keeps tracing (both by the `docs/ops/secrets.md` procedure, after card 010 is done); the coordinator writes the build cards.

## Hand-off
Write `docs/reports/021-s5d-<YYYY-MM-DD>.md` from `docs/templates/handoff-report.md` at each checkpoint. Don't commit: the owner does.
