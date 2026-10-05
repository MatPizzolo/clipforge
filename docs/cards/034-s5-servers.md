# Card 034: S5 (S5-4) — weights, the three media servers and the hello producer on Modal

Status: proposed
Stream: S5 (S5-4) · Branch: `s5/servers` · Worktree: `../clipForge-s5` (created with `scripts/worktree.sh s5/servers`)
Decision-log range: #680–#719 (append only; shared in sequence by cards 031–034: re-read the log and take the next free number)
Model: most capable (GPU images, memory snapshots, the weights Volume, the server step pattern)
Depends on: card 033 (S5-3) **deployed** with its owner steps done (and so 031 and 032). Per log #144, no other code card is on `main` undeployed when this one merges
Cost cap: $5 of Modal/API spend (log #605; the session's probes and the owner's weight downloads, prep, `doctor`, hello run and gpu tests together; stop and ask before going over). Every probe app has its own name and is stopped before the session ends

## Context
Cards 031–033 deployed the `modal_app/` split, the registry and engine (with `hello` refused until its server is bound), and the Modal-free `media/` package, stages and renderer additions. **This card builds S5-4, plan Tasks 12–15:** the real media adapters (`media/impl/`, heavy imports inside `load()`), the weight download and prep functions for the `clipforge-models` Volume, the server classes built from `registry.toml` (the Narrator: Qwen3-TTS + faster-whisper on one L4; stills: Qwen-Image-2512 + Lightning on an L40S; music: ACE-Step 1.5 on an L4) and the hello server, with GPU work in a `run_step` method inside each class, one item per call (#580, #582). Then the owner runs hello end to end on Modal and one gpu test per server.

Rulings that bind this card:
- **Weights** (#588): `download_weights` fetches only registry-listed files at full SHAs and writes `MANIFEST.json`; `prepare_weights` writes the fused Qwen-Image transformer to `prepared/<model>/<rev>-p<N>/` atomically; servers mount the Volume read-only, set `HF_HUB_OFFLINE=1`, check the manifest at startup and never download. No Hugging Face token. A missing or mismatched manifest is a `PermanentError` with one ops alert (Review Focus 3: `test_manifest_mismatch_is_permanent`).
- **Snapshots** (#586): the Narrator and music use CPU snapshots; stills load the prepared fused transformer, with a GPU snapshot only as a registry flag the build turns on if it measures better (owner step 6).
- **Queued is not stalled** (#594): the 4-part hello run measures `idle_before_s` for the warm-window assumption.
- **Server-only packages** (torch, qwen-tts, diffusers, ACE-Step, …) are pinned in `registry.toml` and installed in their images, **not** in `uv.lock`; mypy ignores their imports through `pyproject.toml` overrides.
- No `@modal.batched`; no LLM tracing (#597); clips never call a server.

## Read first
1. `CLAUDE.md`, `STATUS.md`
2. The S5 plan: Global Constraints (licenses, weights, probe apps), Review Focus 3, File map, Part S5-4 (Tasks 12–15, the owner steps and the rollback), Deployable steps and coverage
3. The S5 spec §5 (servers, §5.1–§5.5), §6.3, §7
4. `docs/DECISIONS.md`: ADR-9, ADR-11, ADR-12, ADR-30
5. Log rows #580, #582, #586, #588, #589, #594, #605, #148
6. `docs/studio/03-tools-and-models.md`, card 021's probe notes (the reference loading code in the S5 spec and its reports), and cards 031–033's reports
7. The code it changes: `modal_app/images.py`, `modal_app/pipeline.py`, `modal_app/entrypoints.py`, `pipeline/engine.py`, `config.py`, `pyproject.toml`, `media/`
8. Runbook §1 (the blackout) and the memory note on long Modal calls from WSL (use spawn and poll, not a long `.remote()`)

## Scope
- May edit, as `scripts/scopes.toml` allows for `s5/`: `src/**` (`media/impl/`, `media/weights.py`, `modal_app/servers.py`, `modal_app/weights.py`, …), `tests/**`, `pyproject.toml` (mypy overrides only), `docs/ARCHITECTURE.md` (media servers, the registry, `modal_app/`), `CLAUDE.md` (Layout: `modal_app/`, `producers/`, `media/`; Commands: `weights`), `docs/studio/11-owner-runbook.md` (a "Media weights" section with the owner commands below), `docs/ops/**` (deploy notes, if needed), `docs/studio/03-tools-and-models.md` (the measured cold starts), `docs/superpowers/plans/*studio-s5*`, `docs/studio/04-roadmap.md` and `ROADMAP.md` (S5 ticks only after the owner confirms what's live), `scratch/s5/**` (probes, gitignored), its own report, and log rows in #680–#719.
- Must not edit: `uv.lock` (no new dependency there), the `clipforge` app (only the owner deploys), stage behavior for clips, `alembic/`, the S5 spec, `STATUS.md`, other cards.
- **Only `app.py` and `modal_app/` import `modal`.** **The session never deploys or stops the `clipforge` app, never writes the `clipforge-models` Volume (the owner's `weights` runs do), and never changes a secret.**

## Actions
Each task follows the plan: failing tests first, then the implementation, then its checks, then "check and record".
1. **Task 12, `media/impl/`:** `QwenTts`, `WhisperAligner`, `QwenImage` (the prepared fused transformer, layerwise fp8 casting), `AceStep` (DiT-only, instrumental), `TorchHelloGpu`, `check_manifest`; `tests/media/test_impl_imports.py` (cheap imports) and `tests/media/test_impl_gpu.py` (`@pytest.mark.gpu`, run by the owner); the mypy overrides.
2. **Task 13, weights:** `media/weights.py` (`plan_download`, the manifest, the prep recipe) and `modal_app/weights.py`, the `weights` entrypoint (`--model`, `--prep`, `--check`).
3. **Task 14, the servers:** `images.server_image(entry)`, `modal_app/servers.py` (one class per registry server, settings from the registry, `run_step`, the manifest check at startup, `idle_before_s`), `produced_bindings()` binding the server steps, `Prices.gpu_per_second` for L40S and H100, `models_root`, `cold_start_s` on the first call; `test_spawner_binds_every_registry_step`, `test_first_call_records_cold_start`, Review Focus 3.
4. **Task 15, docs:** `docs/ARCHITECTURE.md`, `CLAUDE.md`, the runbook's "Media weights" section; `scripts/check.sh --docs`.
5. **Checkpoint S5-4:** `scripts/check.sh` green; `pr-reviewer`, `pipeline-reviewer` (the engine's cold-start record, cost, the server step pattern) and `security-reviewer` (the weights functions: registry-only downloads, read-only mounts, no token, no secrets in logs); fix what they find; `uv run modal app list` shows no probe app running; the report with the session's spend and the owner steps below; stop.
6. **After the owner's run:** record in the report the hello run's four parts (GPU name, cost, `idle_before_s`), the three gpu-test results and the measured cold starts; if stills' cold start is above 90 s, propose the one follow-up deploy with `snapshot = "gpu"` for stills; tick only what's live.

Stop for the owner at the checkpoint below, and again after the owner's run.

## Checkpoints
- A (S5-4 code): after actions 1–5. Suggested commit: `034: s5-4: weights, media servers, hello producer`
- B (the owner's run): action 6. Suggested commit: `034: s5-4: measured cold starts and the hello run`

## Done when
- `scripts/check.sh` is green (paste its summary lines into the report).
- `pr-reviewer`, `pipeline-reviewer` and `security-reviewer` have no blocking findings, and the report lists what each said.
- After the owner's run: `clipforge run --producer hello --param parts=4` is `done` on an `NVIDIA L4` under $0.03; the three gpu tests pass; `weights --check` shows every entry `ok`; the cold starts and `idle_before_s` values are in the report; total spend is under $5.
- `uv run modal app list` shows only `clipforge` deployed.

## Owner steps
- Before: card 033 deployed; nothing else undeployed on `main`. `scripts/worktree.sh s5/servers`, open a session in `../clipForge-s5`, paste `Run card docs/cards/034-s5-servers.md`.
- At A: commit with the suggested message, `git push -u origin s5/servers`, `gh pr create --fill`, squash-merge when CI is green.
- Deploy and run (from `main`, in order, outside the blackout):
  1. **Pre-deploy check (#144, #145)**; `scripts/deploy.sh --dry-run`; `scripts/deploy.sh --reason "S5-4: media servers, weights functions, hello producer"`.
  2. **Weights** (CPU only, cents each): `uv run modal run src/clipforge/app.py::weights --model qwen3-tts-base`, then `--model faster-whisper-turbo`, `--model qwen-image-2512`, `--model qwen-image-2512-lightning`, `--model ace-step-1-5`; then `uv run modal run src/clipforge/app.py::weights --model qwen-image-2512 --prep` (about 15–25 min, ~$0.20); then `uv run modal run src/clipforge/app.py::weights --check`: every entry `ok`.
  3. `uv run modal run src/clipforge/app.py::doctor`: local, GPU and base-image filter checks ok.
  4. `uv run clipforge run --producer hello --param parts=4 --param label=s5-4-$(date +%s)`: `done` in about a minute; `uv run clipforge status <id>` shows four parts on `NVIDIA L4`, cost under $0.03; note `idle_before_s` per part from `metadata.json`.
  5. `uv run pytest -q -m gpu tests/media/test_impl_gpu.py`: three passes (about $0.30 with cold starts).
  6. Give the session the cold starts (`StageCost.cold_start_s`) for checkpoint B. If stills' is above 90 s, the follow-up deploy tests `snapshot = "gpu"` for stills and keeps the faster one.
  7. `uv run modal app list`: only `clipforge` deployed. Commit the deploy line in `docs/ops/deploys.md`, and tell the coordinator.
- **Rollback:** a revert deploy (`git revert` of the merge, `scripts/deploy.sh --dry-run`, `scripts/deploy.sh --reason "revert S5-4"`). Clips never call a server; the weights stay on the Volume, harmless.

## Hand-off
Write `docs/reports/034-s5-<YYYY-MM-DD>.md` from `docs/templates/handoff-report.md` at each checkpoint, with each task's status, the spend, the measurements and the reviewers' findings. Don't commit: the owner does. This closes S5's build (04's exit: clips through the registry, hello proving the GPU step pattern); remove the worktree after the merge (`scripts/worktree.sh --remove s5/servers`).
