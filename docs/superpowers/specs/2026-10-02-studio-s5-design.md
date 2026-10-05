# S5: media servers and producer registry, design

Date: 2026-10-02 · Card: [021](../../cards/021-s5-media-design.md) · Branch: `s5d/design` · Status: **approved section by section 2026-10-02** (owner), written for review at checkpoint A
Implements ADR-30 (accepted) on top of ADR-12 and ADR-31. Proposes ADR-52 (§10). Action card: docs/studio/06 §D "S5"; roadmap: docs/studio/04 "S5".

## 1. Goal, scope and success criteria

S5 builds what every generative producer needs, so that S6 (the story producer) only writes its own steps:
- Modal-free `media/` protocols with fakes, and a license-gated `media/registry.toml`;
- `modal.Cls` media servers for **narration** (Qwen3-TTS + the aligner, one server), **stills** (Qwen-Image-2512 + Lightning) and **music** (ACE-Step 1.5), with weights on the `clipforge-models` Volume;
- a **pipeline registry**: per-producer step lists drive `dispatch`, `resume` and the sweeper through one engine; clips move onto it unchanged;
- `app.py` split into a `modal_app/` package (still the only Modal layer);
- LLM tracing in Langfuse, off until keys exist;
- the renderer additions X4 asked for (crossfades, a duck depth, captions from narration timings), without changing clip output;
- a no-op **hello** producer that proves the GPU step pattern end to end.

**Exit (04):** the clip producer runs through the registry with identical behaviour (cache keys, outputs and `producer_version` unchanged), the hello producer runs end to end on Modal, and a registry test fails on a banned license.

**Owner rulings in this session (2026-10-02, log #580–#589):**

| Question | Ruling |
|---|---|
| Which servers | Narrator (TTS + aligner), stills, music. **B-roll (Wan2.2 A14B) moves to S6**, at its first use, on the pattern S5 proves |
| TTS and aligner | **One Narrator server**: one L4 holds Qwen3-TTS and faster-whisper; one step synthesizes, transcribes, runs X1's guard and writes word timings |
| Renderer additions | **In S5**, as optional Timeline fields whose defaults reproduce today's clip output exactly and stay out of the render cache key; bump `render.STAGE_VERSION` only if clip output actually changes (§8). Story values come from the producer's settings |
| Grouping GPU work | **Per item, warm window**: one item per server call; S6 submits an account's day of items together; capped containers keep them on one warm container |
| `app.py` split | **First task of S5's build, its own checkpoint**, a pure move |
| Langfuse | **Hosted (Cloud Hobby), behind `LLMClient`, off unless keys exist**; metadata only |
| Measurement | **Yes**: a ~$1.50 probe of memory-snapshot cold starts (§5.4); spent ~$1.2 |
| Registry shape | **Data registry with one engine** (§6) |
| Section 1 changes | A narration failing its guard twice fails the item with an ops alert (no "review"); full cache-key inputs per stage; GPU seconds and `ctx.report` in every new stage; Kokoro only as a model-level fallback per account |
| Coordinator note | `scaledown_window` per server in the registry, sized from the gap between items plus a margin (60–120 s); idle-tail cost next to cold-start cost |
| Coordinator review of the written spec (2026-10-03, log #591–#596) | The split is its own card after card 014 is deployed (§7.1); clips' `producer_version` frozen at `clips:4c44b731` (§6.4); the loudness-label fix deferred (§8.2); queued and running bounds from a registry batch cap (§5.2); the bed level relative to the narration (§8.1); crossfades on real frames first, inputs normalized (§8.2); the warm-window assumption measured at S5-4 (§5.2) |

Out of scope: the story producer and its steps (S6), b-roll and RIFE (S6), talking heads (S8, after X2), the Judge (S6), Kokoro serving (only if an account needs it), the bulk LLM router (ADR-32, deferred), database tables (none).

## 2. Shape

```
                      producers/registry.py  (Modal-free: step lists, handlers, input models, versions)
                                │
 Modal layer (app.py entry + modal_app/)       pipeline/engine.py (Modal-free: guard, hand-off, fan-out,
   CPU step functions  ──spawn──►               fan-in, failure, resume, sweep; from today's steps.py)
   servers: Narrator · Stills · Music · HelloGpu        │
     └── run_step(job_id, part_id) ─ dispatch ─────────┘
                                │
                     stages/narrate.py · stills.py · music.py   (Modal-free, cached, ADR-8)
                                │
                        media/protocols.py (Tts, Aligner, ImageGen, MusicGen) ← fakes in tests
```

Rules carried over: stages are pure and resumable (CLAUDE.md rule 1), contracts change in `models.py` first (rule 2), every long stage reports progress (rule 3), prompts stay files (rule 4), cost is logged (rule 7), only the Modal layer imports `modal`.

## 3. `media/` protocols and the stages that use them

### 3.1 Protocols (`media/protocols.py`)

Contracts live in `models.py` (rule 2). Every path is relative to `JOBS_ROOT` (ADR-8, ADR-13).

```python
class VoiceRef(Contract):            # a persona's synthetic voice: a reference clip + its exact transcript (X1)
    persona_id: str; language: Literal["en", "es"]
    ref_path: str                    # models Volume: voices/<persona_id>/ref_<lang>.wav
    ref_text: str; ref_hash: str     # sha256 of the clip; part of narrate's cache key

class SpeechChunk(Contract): wav_path: str; sample_rate: int; seconds: float
class AlignedText(Contract): words: list[Word]; wer: float      # words snapped to the known script
class StyleLock(Contract): model_id: str; suffix: str; negative: str = ""   # one per video and account (X4 rule 3)
class StillPrompt(Contract): line_index: int; prompt: str
class StillOut(Contract): line_index: int; path: str; width: int; height: int; seed: int
class BedPrompt(Contract): mood: str; duration_s: float; seed: int
class BedOut(Contract): path: str; seconds: float; lufs: float   # normalized at generation (X4 rule 8)

class Tts(Protocol):
    def synthesize(self, text: str, voice: VoiceRef, seed: int, max_new_tokens: int) -> SpeechChunk: ...
class Aligner(Protocol):
    def align(self, wav_path: str, script: str, language: str) -> AlignedText: ...
class ImageGen(Protocol):
    def generate(self, prompts: list[StillPrompt], style: StyleLock, width: int, height: int, seed: int) -> list[StillOut]: ...
class MusicGen(Protocol):
    def generate(self, prompt: BedPrompt) -> BedOut: ...
```

`media/fakes.py` gives deterministic fakes for fast tests: speech as a sine tone of `words / 2.7` seconds (a flag makes it run away or drop a sentence), solid-color PNGs, a pink-noise bed. A fake aligner returns the script words with even timings and a configurable WER.

### 3.2 Stages

| Stage | Input | Output | Cache key (ADR-8; never `job_id`, rank or ids) |
|---|---|---|---|
| `narrate` | script lines (spoken text and display text per line), `VoiceRef`, language, base seed | `Narration`: wav, per-line start/end, display words with times, guard stats (attempts, WERs, durations), integrated loudness `lufs` (for the bed level, §8.1) | spoken text of every line, display text, language, `voice.ref_hash`, base seed, the TTS and aligner model revisions, `narrate.STAGE_VERSION` (covers the chunking rules and the guard thresholds) |
| `stills` | `StillPrompt[]`, `StyleLock`, size, base seed | `StillOut[]` | model id and revision, the style lock (suffix and negative prompt), each prompt, width, height, seed, `stills.STAGE_VERSION` |
| `music` | `BedPrompt` | `BedOut` | mood, duration, seed, model revision, `music.STAGE_VERSION` |

**Narrate and X1's guard** (log #72; one step, one transcription):
- Chunk by script line (X4 rule 6: one narration line per cut).
- Per chunk: `max_new_tokens = ceil(1.5 × words / 2.0 × codec_fps)` (`codec_fps` read from the model config, about 12.5), synthesize, transcribe with word timestamps, then keep the chunk only if its length is within 0.6–1.5 × `words / 2.7` s and its WER against the line is at most 15%.
- A rejected chunk is retried once with a new seed (`base seed + attempt`). A second failure raises `PermanentError("narration failed its guard on line N: <reason>")`: the item fails with a clear reason and an ops alert (ADR-45), and S6 can queue the script again. A failed narration leaves nothing to review.
- Never another model's voice inside one item. **Kokoro is X1's model-level fallback**: an account switches to it only if Qwen3-TTS proves unusable for that account, never per line or per item, so one video never mixes voices.
- Word timings: the transcription's words are snapped to the known script (spoken form), then mapped to the line's display form (digits, X4's "fifteen-foot" case) for captions.

**Every new stage** records GPU seconds, GPU type and USD in the job metadata through `ctx.record_cost` (rule 7; §7) and calls `ctx.report` per line (narrate), per image (stills) or per bed (music) (rule 3).

S5 builds and tests these stages with fakes; S6 is the first producer to call them.

## 4. `media/registry.toml`

```toml
[allowlist]
allowed = ["Apache-2.0", "MIT", "BSD-2-Clause", "BSD-3-Clause", "CC0-1.0", "CC-BY-4.0"]
conditional = ["GPL-3.0"]            # server-side only, never distributed (03; log #67): needs `condition`
review = ["OpenRAIL", "OpenRAIL++", "Llama", "community"]   # needs `owner_ruling = "#NNN"`
banned = ["AGPL-3.0", "CC-BY-NC-4.0", "CC-BY-NC-SA-4.0", "non-commercial", "unlicensed"]

[model.qwen3-tts-base]
repo = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
revision = "<full 40-char sha>"
license_weights = "Apache-2.0"; license_code = "Apache-2.0"
dependencies = [{ name = "qwen-tts", license = "Apache-2.0" }]
server = "narrator"; volume_path = "hf/hub"
```

Server settings live in the same file, one table per server:

```toml
[server.narrator]
models = ["qwen3-tts-base", "faster-whisper-turbo"]
gpu = "L4"; memory_mib = 16384
snapshot = "cpu"                     # "none" | "cpu" | "gpu" (§5.4)
scaledown_window_s = 90              # the gap between items in a batch plus a margin (§5.3)
max_containers = 1
max_batch_items = 6                  # S6's planner submits at most this many items at once (§5.2)
item_s = 300                         # warm upper bound per item; queue_s = max_batch_items × item_s
```

Registered in S5: `qwen3-tts-base`, `faster-whisper-turbo` (the Narrator's Volume copy; the transcribe image keeps its baked copy, ADR-11), `qwen-image-2512` (`25468b98e3276ca6700de15c6628e51b7de54a26`, resolved by this card's probe), `qwen-image-2512-lightning` (`a52649c9d0f6e1a248bff13f0df33bb8a2abdb52`, file `Qwen-Image-2512-Lightning-8steps-V1.0-bf16.safetensors`), `ace-step-1.5` (X4's `19671f40`, code tag `v0.1.6`), and `hello` (no weights). Kokoro, Z-Image and the Wan models are registered by the card that first serves them.

`media/registry.py` loads and validates the file into pydantic models. `modal_app` builds each server's image, GPU, memory, Volume mount, snapshot flags, window and container cap **from it**, so code and registry can't drift.

**Tests** (fast):
- every license (weights, code, each dependency) is in `allowed`, or in `conditional` with a `condition`, or in `review` with an `owner_ruling`; anything in `banned` or unknown fails, and a fixture entry with FLUX.1-dev's non-commercial license proves the test fails;
- every `revision` is a full 40-character SHA;
- every server's `models` exist, and every server class in `modal_app` has a registry entry (the check reads the class map the Modal layer exports, without starting Modal).

## 5. Media servers

### 5.1 The servers

| | Narrator | Stills | Music | HelloGpu |
|---|---|---|---|---|
| Model | Qwen3-TTS 1.7B Base (bf16, SDPA) + faster-whisper large-v3-turbo (fp16) | Qwen-Image-2512 + Lightning 8-step, fused, transformer in FP8 storage, 928x1664, 8 steps | ACE-Step 1.5 turbo, DiT only (no "thinking") | none |
| GPU / VRAM (measured) | L4 / **4.4 GiB** for both models | L40S / **40.9 GiB** (64 GiB RAM) | L4 / 13.1 GiB (X4) | L4 |
| Snapshot | **cpu** (imports) | **none**, with prepared weights (§5.4); `gpu` is a flag | cpu (imports) | cpu |
| `@modal.batched` | no (X1's guard) | no | no | no |
| `max_containers` | 1 | 1 | 1 | 1 |
| `scaledown_window_s` | 90 | 90 | 60 | 2 |

**Step methods inside the class (ADR-12).** Each server has one method, `run_step(job_id, part_id)`, that calls the engine's `dispatch` (§6) with `Deps` whose stages hold the warm model. The spawner spawns `Narrator().run_step` directly, so no CPU container ever waits on a GPU call, and a GPU container never waits on another. One GPU per container, one input at a time (no `@modal.concurrent`). `retries` and timeouts are as for today's steps (`MAX_ATTEMPTS = 3`).

**Why no `@modal.batched`** (a deviation from 04's wording): `@modal.batched` groups many small concurrent calls into one; our calls carry one item each, and batching inside an item is the stage's business (stills run in sequence: 40.9 GiB leaves no room for a second image). Revisit if S6 shows many small concurrent calls.

**Volumes.** `clipforge-models` is mounted **read-only** (`.read_only()`) in every server; only the weight functions (§5.5) write to it. `clipforge-jobs` is mounted as in today's steps, with `reload()` before and `commit()` after each step (the engine does both).

### 5.2 Warm window and container cap

S6 submits an account's day of items together. Without a cap, Modal would start one container per waiting call, each paying the cold start. With `max_containers = 1`, the items queue on one warm container, and the gap between two calls is only the chain's hand-off latency (a CPU step finishing and spawning the next). So `scaledown_window_s` is the hand-off gap plus a margin: **90 s** for the Narrator and stills, 60 s for music (bank jobs only), as the coordinator asked (60–120 s, not a flat 5–10 min). It is a registry setting per server, so S6 can tune it from measured gaps. The cap also keeps S5's servers inside Starter's 10-GPU limit.

**The warm-window assumption, stated:** with the cap, queued calls run back to back on one container, so the idle gap between two of them is about 0, plus the chain's hand-off (a CPU step finishing and spawning the next) when an item's next GPU call depends on a CPU step in between. The window only has to cover that hand-off. S5's servers checkpoint measures it: the hello run with 4 parts records each call's idle gap on the container (`HelloResult.idle_before_s`), and the owner step records the numbers before S6 relies on them.

**Queued is not stalled** (coordinator's review): the registry enforces a batch cap per server, `max_batch_items` (stills 6, Narrator 6, music 4, hello 4), and S6's planner never submits more than that per server at once. Each server step's `queue_s = max_batch_items × item_s` (`item_s`: the server's warm upper bound per item, a registry value). The engine records which step a job (or part) is waiting for at hand-off (`Job.waiting_for`, or the part's `pending` status), and the sweeper uses two bounds: **queued** (handed off, not started) fails after `queue_s + 5 min` from the hand-off; **running** (the step started: `engine.start` or the part set `running`) fails after `timeout_s + 5 min` from the start, as today.

### 5.3 Cost per server (rates: L4 $0.80/h, L40S $1.95/h; memory included where it matters)

| Server | Cold start | Idle tail (window) | Warm unit |
|---|---|---|---|
| Narrator | 22–30 s with a CPU snapshot (measured) → **~$0.006** | 90 s → **~$0.020** | **$0.033 per 60 s** of narration (X1, unbatched) |
| Stills | ~70–85 s estimated with prepared weights (131–174 s measured today; 64 s with a GPU snapshot) → **~$0.04** | 90 s → **~$0.049** | **$0.0041 per image** (X4) |
| Music | ~115 s (X4; a CPU snapshot only trims the imports) → **~$0.026** | 60 s → **~$0.013** | **$0.0031 per 60 s bed** (X4) |
| HelloGpu | ~20 s → ~$0.004 | 2 s → ~$0 | ~$0.001 a run |

Per account and day, one batch costs about $0.03 of Narrator overhead and $0.09 of stills overhead (cold start plus tail). Music is generated only for the account's bed bank (X4, log #472), so its overhead is near zero per month.

### 5.4 Memory snapshots: measured (this card's probe, 2026-10-02)

Probe app `clipforge-s5-probe` (code in `scratch/s5d/`), deployed so snapshots persist; `scaledown_window=2` and a 45 s gap forced a new container per call. "Cold start" is the round trip minus the work itself; Modal's GPU scheduling made single rounds noisy (one plain Narrator round took 119 s for the same work as a 25 s one).

| Server | No snapshot | CPU snapshot (imports in `snap=True`) | GPU snapshot (restore) | Making a snapshot |
|---|---|---|---|---|
| Narrator (Qwen3-TTS + faster-whisper, L4) | 25–62 s (one 119 s outlier); imports 10–13 s, TTS load 6–7 s, whisper load 2 s | **22–30 s** | **18–19 s** | 90–150 s, twice after a deploy |
| Qwen-Image-2512 + Lightning (L40S, FP8 storage) | **131–174 s**: read 11–18 s, **LoRA load and fuse 60 s**, FP8 cast 20 s, to GPU 10 s | — | **64 s** | 270–500 s, at least twice after a deploy |

Also measured: the first TTS generation in a container took 18–31 s for 10 s of speech (RTF 1.8–3.0, X1 measured 2.5), the same with a GPU snapshot, so snapshots don't hide warm-up. Whisper on that chunk took 1.2–1.6 s.

**Choices:**
- **Narrator: CPU snapshot.** It is stable (not alpha) and gets most of the gain; a GPU snapshot saves about 5 s more.
- **Stills: prepared weights, no snapshot.** A one-off prep function (§5.5) stores the transformer with the Lightning LoRA already fused, removing the 60 s fuse from every cold start (estimated 70–85 s). The GPU snapshot (64 s) is kept as the registry flag `snapshot = "gpu"`, turned on only if the build measures it beating prepared weights: making a GPU snapshot of this server costs $0.15–0.27, two or three times after each deploy, about as much as a cold start.
- **Music: CPU snapshot** (imports), as for the Narrator; not measured here.
- flash-attn for Qwen3-TTS (X1's open item) stays a build-card experiment behind a flag; it needs a wheel matching torch 2.10.

### 5.5 Weights and the Volume

Layout of `clipforge-models`:
```
hf/hub/                          HF cache at pinned full SHAs: Qwen3-TTS Base (+ VoiceDesign for S6 personas), Qwen-Image-2512,
                                 the Lightning LoRA, ACE-Step 1.5 (TTS and Qwen-Image are already there)
whisper/                         faster-whisper large-v3-turbo (already there)
prepared/<model_id>/<rev>-p<N>/  derived weights, e.g. the LoRA-fused Qwen-Image transformer (bf16, ~41 GB)
voices/<persona_id>/             ref_<lang>.wav + ref_<lang>.txt per persona (S6 writes them; refs/x1/ stays as the test voice)
x2/                              card 005's ~227 GB: not S5's; the owner decides (STATUS item 8)
```

Functions (`modal_app/weights.py`, CPU only, run by the owner):
- `download_weights(model_id)`: `snapshot_download` at the registry's full SHA (only the listed files, e.g. one LoRA file), writes `MANIFEST.json` (repo, SHA, files, bytes) and commits.
- `prepare_weights(model_id)`: runs the entry's recipe (`prep = "fuse_lora"`, version `p1`) on a CPU container with ~80 GiB RAM, writes to a temporary directory and renames it into place, so a crash never leaves half a model.
- The local entrypoint `uv run modal run src/clipforge/app.py::weights --model <id> [--prep]` spawns and polls (long `.remote()` calls drop from the owner's WSL). `weights --check` lists what each entry expects and what is on the Volume. `weights prune` (dry run unless `--apply`) lists revisions that no entry references; nothing is deleted automatically.

At startup a server sets `HF_HUB_OFFLINE=1`, checks that each model's `MANIFEST.json` matches the registry's revision and prep version, and fails loudly ("weights missing: run `weights --model X`") if not. A server never downloads.

None of S5's models is gated, so S5 needs **no Hugging Face token** (the card's owner step falls away). Downloads cost cents of CPU. S5's footprint is about 120 GB (Qwen-Image ~58, the fused transformer ~41, TTS ~9, ACE-Step ~10, whisper ~1.6); the owner checks Volume storage pricing for that and for X2's 227 GB.

## 6. The pipeline registry and one engine

### 6.1 Contracts (additive; old Dict records and API clients read as before)

- `JobInput.producer: str = "clips"` and `JobInput.params: dict[str, Any] | None = None`. For `clips`, today's validator applies (exactly one source). For any other producer: no source, `permission` must be `own`, and `params` is validated by the producer's input model in `service.create_job` (`HelloParams` here, `StoryParams` in S6).
- `Job.producer: str = "clips"`, and `Job.waiting_for: str | None = None` (the step id handed off to and not yet started; set by the engine's hand-off, cleared by `engine.start`; the sweeper's "queued" bound, §5.2).
- `StageName` gains `narrate`, `stills`, `music`, `hello`.
- `outputs`, `clip_ids`, `ClipState` and `job:<id>:clip:<part>` keep their names: a fan-out unit is still a "clip" record. The naming debt is noted and goes only with an API change.
- No migration: `jobs.input` is JSON and already carries the producer; `content_items.producer` exists since S1.

### 6.2 The registry (`producers/registry.py`, Modal-free)

```python
@dataclass(frozen=True)
class StepDef:
    name: str
    shape: Literal["single", "fanout", "part", "fanin"]
    runner: str                 # "cpu:<function>" or "server:<server>"; modal_app binds it
    stage: StageName            # what job.stage shows and failures are reported under
    timeout_s: int
    queue_s: int = 0            # worst wait behind the server's container cap

@dataclass(frozen=True)
class Producer:
    name: str
    steps: list[StepDef]
    input_model: type[BaseModel] | None
    version: Callable[[Settings], str]          # producer_version (ADR-43)
    handlers: Mapping[str, StepHandler]         # step name -> body
```

`clips`: `ingest` (single, `cpu:ingest_step`) → `transcribe` (single, `cpu:transcribe_step`, the whisper image) → `highlights` (fanout) → `clip` (part) → `package` (fanin). These are exactly today's step names, Modal function names and timeouts, so attempt keys (`job:<id>:attempts:<step>`), the `spawn:<step>` claims and the functions themselves are unchanged, and **jobs in flight across the deploy finish normally**.

### 6.3 The engine (`pipeline/engine.py`, from `steps.py`)

- Generic: `_guarded` (Volume reload, attempts, `PermanentError`, retries), `_handoff` (claim, then spawn), the fan-out (write the part specs, create the part records set-if-absent, spawn each part), the fan-in claim (`package` today: the claim name becomes the fanin step's name), `fail_job` with ops alerts, `record_job`, the posting hook (clips only).
- Per producer: one handler per step. **The clip handlers are today's step bodies, moved without edits.**
- `dispatch(deps, step, job_id, part_id)` reads the job's producer, finds the step and runs it.
- `resume` walks the producer's steps: the first single or fanout step without an output; otherwise the unfinished parts; otherwise the fan-in.
- `sweep` uses two bounds (§5.2): a job with `waiting_for` set (or a part still `pending`) fails after `queue_s + STALL_MARGIN_S` from the hand-off; a started step fails after `timeout_s + STALL_MARGIN_S` from its start (found from `job.stage`, as today).
- Step ids are unique across producers: clips keep their bare names (`ingest` … `package`), every other producer's steps are `<producer>.<step>` (`hello.prepare`). So `Spawner.spawn(step, job_id, part_id)` and `dispatch(deps, step, job_id, part_id)` keep today's signatures (and every chain test keeps its calls); the registry resolves a step id to its producer and `StepDef`. `modal_app` binds each step's `runner` to a Modal function or a server's `run_step` (the plan, 2026-10-03, settled this detail; it was `spawn(producer, step, …)` in the approved section). `create_job` spawns the producer's first step. `Deps.version` comes from the producer, so clips keep `clips:<today's hash>`.

### 6.4 Proving clips are unchanged

- Today's tests for the steps, resume and the sweeper run unchanged against the engine.
- A golden test runs a whole clips job with fake stages and compares, before and after the refactor: the Dict keys written, the spawn sequence, `outputs`, and the `metadata.json` fields.
- **`producer_version` stays exactly `clips:4c44b731`** (today's value with the default models, computed 2026-10-03). The facts behind it become per producer: clips hash a frozen list of today's 7 stages (ingest, transcribe, highlights, reframe, captions, render, package) and their versions, never the new `narrate`, `stills` or `music` stages, so adding a stage for another producer never moves clips' version or opens an ADR-49 window. A pinned test asserts the literal `clips:4c44b731` with default settings; the stage modules and cache keys aren't touched.

### 6.5 The hello producer

- `prepare` (fanout into 2 parts, CPU) → `gpu` (part, `server:hello`: CUDA init, a fixed matmul, writes the GPU name, a checksum and its GPU seconds) → `finish` (fanin, CPU: `metadata.json` with costs, status `done`).
- No posting and no `ContentItem`. `producer_version = "hello:<hash>"`.
- Run with `uv run clipforge run --producer hello` (or `POST /jobs {"producer": "hello", "permission": "own"}`). Resume and the sweeper are tested on it like clips. About $0.01 a run.

## 7. The `modal_app/` split, cost, errors and tracing

### 7.1 The split (the build's first checkpoint, a pure move)
- `src/clipforge/modal_app/`: `__init__.py` (`app`), `resources.py` (Volumes, Dict, secret), `images.py` (the base and whisper images, and the server images from the registry), `pipeline.py` (step functions and the spawner binding), `servers.py`, `crons.py`, `web.py`, `weights.py`, `entrypoints.py` (`doctor`, `gpu_doctor`, `smoke`, `db_doctor`, `weights`).
- `app.py` stays as a short deploy entry (`from clipforge.modal_app import app` plus the entrypoints), so `modal run src/clipforge/app.py::doctor`, `scripts/deploy.sh`, CI and the docs don't change. The rule "only `app.py` imports modal" becomes "only `app.py` and `modal_app/`", enforced by a test.
- Function names and settings are identical, so deploying the split changes nothing live.
- **In a container** `modal deploy` mounts `app.py` alone at `/root/app.py`; it imports `clipforge.modal_app` from the package every image already mounts (`add_local_python_source("clipforge")`), never through a relative path. `_repo_root` moves to `modal_app/images.py` and counts three parents from there (`/` in a container). No image builder imports the app (`run_function` stays unused).
- **Everything the split touches:**
  - `tests/test_app.py`: the boundary test (`test_only_app_imports_modal`, line 66) becomes `tests/test_modal_boundary.py`; the container-path tests (lines 72–78: `_repo_root`, `run_function`) read `modal_app/images.py`;
  - S3's plan Task 2 tests that read `src/clipforge/app.py` for the `admin` function read the module that defines `web`/`admin` (`modal_app/web.py`);
  - `CLAUDE.md` ("app.py … the only modal importer", the layout), `docs/ARCHITECTURE.md` ("`app.py` is the only Modal module"), the `new-stage` skill (`.claude/skills/new-stage`), the S2/S3 cards' "only `app.py` imports `modal`" lines;
  - `scripts/deploy.sh` and CI keep `src/clipforge/app.py` as the entry; nothing to change there except comments that call it the only Modal module.
- **Landing (coordinator's review, #144, #145):** the split conflicts with every S2a and S3 card that edits `app.py`, so it is **its own code card**, landed between two deployed cards: **right after card 014 (S2a) is deployed, and before card 015 or 022 starts**. It moves whatever `app.py` holds at that moment (S2a's `dispatcher` included), verbatim.

### 7.2 Cost (rule 7)
- Each server step records `StageCost(stage, gpu_s, gpu_type, usd_estimate)` for its GPU work. `StageCost` gains `cold_start_s: float | None = None`, set on a container's first call, so S7 can see the cold-start share per item.
- `config.Prices.gpu_per_second` gains L40S ($1.95/h) and H100 ($3.95/h); L4 is checked against $0.80/h.
- The idle tail isn't per job; it shows in the monthly `modal billing` against the registry's windows (S7 compares).

### 7.3 Errors (ADR-15)
- **Permanent** (fail the item, ops alert): the narration guard failing twice; weights missing or a manifest mismatch; invalid producer params.
- **Transient** (retried twice, then a clean failure): CUDA out-of-memory, ffmpeg errors, Volume lag.
- A container whose `enter` fails is retried by Modal; the sweeper is the backstop. Messages are sanitized as today (`sanitize.clean`, `redact`).

### 7.4 Langfuse
- `llm.py` gains `TracingLLMClient`, which wraps any `LLMClient`; the protocol is unchanged.
- Per call: name `prompt_name@version`, model, input and output tokens, USD, latency, and job, clip and stage ids. **No prompt or completion text** unless `LANGFUSE_CAPTURE_IO=true` (off; a later owner choice).
- It flushes in a `finally` at the end of each step, capped at 2 s, because a serverless container can freeze before a background export runs. A tracing error is logged and never fails a call.
- Off unless `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` and `LANGFUSE_HOST` are in `clipforge-secrets` (added by the `docs/ops/secrets.md` procedure, after card 010). A clips job makes about 20 calls, so Hobby's 50k units cover about 2,000 jobs a month.

## 8. Renderer additions

### 8.1 Contract (`models.py` first)

```python
class Crossfade(Contract):
    duration_s: float = Field(0.4, gt=0, le=1.0)

VideoSegment.transition_in: Crossfade | None = None   # the same on StillSegment; not allowed on the first segment
AudioTrack.duck_db: float | None = None               # music only: extra attenuation while the voice speaks;
                                                      # None = today's sidechain duck

class ProducedStyle(Contract):                        # a producer's settings (S6 tunes them; no renderer code)
    bed_under_voice_db: float = 16.0   # X4 rule 8: the bed's static level, this far under the narration
    duck_db: float = 6.0               # extra attenuation while a line is spoken (on top of the static level)
    crossfade_s: float = 0.4           # X4: the owner's pick in e2e3 (log #474)
```

X4 wants the bed "about 16 dB under the voice" **before** ducking (coordinator's review), so the level is relative, not an attenuation: the `narrate` stage measures its narration's integrated loudness (`Narration.lufs`), the `music` stage normalizes every bed to -20 LUFS with a 1 s fade in and 2 s fade out (`BedOut.lufs`), and the producer sets the music track's `gain_db = (narration.lufs - bed_under_voice_db) - bed.lufs`. `duck_db` then dips it further under each spoken line. The final two-pass loudness (ADR-47) moves both together.

### 8.2 Graph (`render_graph.py`)
- **Crossfade, centered on the cut**, so cuts, narration and captions keep their times. Each neighbour is extended by d/2 into the fade: **with real footage where the media has spare frames** (a video segment's `in_s` can start d/2 earlier, or its media runs d/2 past the out point; a still or Ken Burns segment simply holds or keeps moving), and with cloned frames (`tpad … start_mode/stop_mode=clone`) **only as the fallback** when the media has none (e2e1's freeze complaint). Before `xfade`, every part is normalized (`fps=<tl.fps>`, `settb=AVTB`, `format=yuv420p`, `setsar=1`), because ffmpeg 5.1 rejects mismatched inputs. The parts are joined with `xfade=transition=fade:duration=d:offset=…`. With no `transition_in` in the Timeline, today's `concat` graph is built unchanged.
- **`duck_db`:** a deterministic gain envelope instead of the level-dependent compressor: the music drops by `duck_db` over the union of the narration tracks' spans, with 150 ms ramps (one `volume=eval=frame` expression). The producer places one narration track per line (X4 rule 6), so pauses between lines let the bed come back. With `duck_db=None`, today's `sidechaincompress` runs. Beds are loudness-normalized once by the `music` stage (X4 rule 8), not in the renderer.
- **S4's deferred minors:** `-pattern_type none` on still inputs (a `%` in a path); short b-roll padded with a cloned last frame up to 0.5 s, beyond that still a `PermanentError`. **The loudness-mode label boundary stays deferred** (coordinator's review): fixing it would change `RenderedVideo.loudness` for clips under the same key with `STAGE_VERSION` still 4. The 1 ms string rounding is fixed only if the golden clip strings don't move; otherwise it stays deferred.
- `doctor` gains a filter check that runs **inside the Modal base image** (`xfade`, `tpad`, `sidechaincompress`, `zoompan`, `loudnorm`, `amix normalize`), closing S4's "the filter check doesn't run inside the Modal image".

### 8.3 Cache key and `render.STAGE_VERSION`
- `render.key()` drops `transition_in` and `duck_db` when they are `None`, so every existing clip Timeline keeps its key byte for byte. A pinned test records today's keys for the center, blur and tracked fixtures; the S4 golden graph strings stay as they are.
- Every existing key renders exactly what it rendered before; the new behaviour exists only for Timelines that set the new fields (and stills or short b-roll), and no such Timeline has been rendered yet. ADR-8 requires a bump when a key's output changes, and none does.
- **So `render.STAGE_VERSION` stays "4"**: no `producer_version` change and no ADR-49 window. If any golden or pinned test moves during the build, the card stops, bumps to "5" and records the ADR-49 window (5 items per account, enforced from S2).

### 8.4 Captions for produced Timelines
`captions.for_words(ctx, words, title, deps) -> Subtitles` reuses `chunk_words`, `pick_keywords` (`keywords_v2`) and `build_ass`, so the style can't drift from clips. Its input is the narration's display words (snapped to the script, X4). Its own cache key: stage `captions`, `kind: "words"`, the words, the title, the prompt version, the model and `captions.STAGE_VERSION`; the clip captions key is untouched.

### 8.5 ffmpeg 5.1
The render tests for crossfades, padding and the envelope also run in a `debian:bookworm` container (ffmpeg 5.1, the Modal image's), as S4 did, before any deploy.

## 9. Tests, rollout, rollback and cost

### 9.1 Tests (fast unless marked)
- The registry: licenses, full SHAs, the FLUX.1-dev failing fixture, server ↔ registry mapping. The boundary test (only `app.py` and `modal_app/` import `modal`).
- The guard with fake TTS: a runaway is capped by `max_new_tokens`, a dropped sentence is caught by the WER, a retry uses a new seed, a second failure is permanent with an ops alert.
- Stage cache keys: each input listed in §3.2 changes the key; ids and ranks don't.
- The engine: today's step, resume and sweep tests unchanged; the clips golden run; the hello run with fakes, including resume and a sweep with `queue_s`.
- Render: pinned clip keys, golden graphs, crossfade, envelope, `%` in a still path, short b-roll; the same tests in bookworm.
- Langfuse: the wrapper with a fake exporter (no text sent, an exporter error doesn't fail the call).
- `@pytest.mark.gpu`: one real call per server on Modal (run by the owner at the servers' checkpoint).

### 9.2 Build checkpoints (each deploys alone, after S1's rollout and outside the blackout, only through `scripts/deploy.sh`)
Every checkpoint is a code card deployed with its owner steps done before the next code card merges (#144), taking its turn with the S2 and S3 cards (#145). S5 has **no Neon migration**. `JobInput.producer`/`params` change the API contract, so S5-2 regenerates `web/openapi.json` (`uv run python scripts/export_openapi.py`) and the client (`npm --prefix web run gen`).
1. **The `modal_app/` split** (its own card, right after card 014 is deployed and before card 015 or 022 starts, §7.1). Deploying changes nothing live; `smoke`.
2. **Registry and engine, clips on it.** `smoke`, then one real channel job.
3. **`media/`, the three stages, the renderer additions.** No live change; bookworm render tests.
4. **Weight functions, servers and hello.** Owner: `weights --model` for each entry, `--prep` for Qwen-Image, `doctor`, deploy, `uv run clipforge run --producer hello`, the gpu-marked tests.
5. **Langfuse**, once the keys are in the secret (after card 010).

### 9.3 Rollback
Revert the checkpoint's PR. Clips never call a server. Reverting the engine restores `steps.py`; step names, function names and Dict keys are unchanged, so jobs in flight survive either direction. Weights left on the Volume are harmless.

### 9.4 Monthly cost
- S5's way of running adds about $0.03 (Narrator) and $0.09 (stills) of cold start plus idle tail per account per day: about **$7 a month** in 03's scenario 1 (2 story accounts) and about **$35 a month** in scenario 2 (9 accounts with stills, 13 with narration), inside 03's "+30% cold starts" line.
- The build's own runs cost about $3 (downloads, prep, hello, the gpu tests). Langfuse is $0. Volume storage is the owner's check (§5.5).

### 9.5 Safety
No new routes or secrets beyond the optional Langfuse keys. Producer params are validated against the producer's model before a job exists. Server paths resolve through `JobContext.path`, and every contract path is relative (ADR-13). The models Volume is read-only in servers. The registry test blocks non-commercial models before any code can load them.

## 10. Proposed ADR-52: media servers and the producer registry

Draft in docs/studio/05 (the next free number is ADR-52, per 05's header). Refines ADR-12 and ADR-30:
- every producer is a list of steps in a Modal-free registry, run by one engine (guard, hand-off, fan-out, fan-in, resume, sweep);
- a GPU step runs inside its media server's class as `run_step`, one item per call, with `max_containers` capped so a batch of items reuses one warm container; `scaledown_window` per server, sized from the gap between items plus a margin;
- snapshots are chosen per server by measurement (CPU snapshots by default; GPU snapshots, alpha, only where a measurement shows they pay);
- derived weights (fused LoRAs, converted precisions) are prepared once on the Volume with a manifest that servers check at startup; servers never download;
- no `@modal.batched` until there are many small concurrent calls.

## 11. Proposed changes to other documents

Edited by this card at checkpoint B (in scope): **03** (§5.4's measured numbers), **04** (the S5 section: b-roll moves to S6, the renderer additions land in S5, the Narrator replaces the separate aligner), **05** (ADR-52).

For the coordinator (out of this card's scope):
- **02 §4:** "throughput models use `@modal.batched`" → per-item step methods with capped warm containers (§5.1); snapshots per server by measurement; the Narrator is TTS + aligner in one class. **02 §3:** the story row's `tts → align` is one `narrate` step. **02 §10:** `producers/registry.py` + `pipeline/engine.py`; `app.py` + `modal_app/`.
- **04 S6 and 06's S6 card:** S6 builds the b-roll server (Wan2.2 A14B, bf16 copies prepared on the Volume, X4) on S5's pattern; story Timelines use `ProducedStyle` and `captions.for_words`; narration goes through the `narrate` stage; Kokoro is served only if an account switches to it; "RIFE" stays optional (X4).
- **06's S5 card:** owner steps lose the Hugging Face token (§5.5); add the weight downloads and the hello run.
- **S6 (04, 06, its spec):** the planner submits at most `max_batch_items` items per server at once (§5.2), and story Timelines set the bed level from `bed_under_voice_db` (§8.1).
- **The S3 plan, Task 2:** its tests that read `src/clipforge/app.py` for the `admin` function read the module that defines it (`modal_app/web.py`) once the split has landed (§7.1).
- **The S2 and S3 cards, `CLAUDE.md`, `docs/ARCHITECTURE.md`, the `new-stage` skill:** "only `app.py` imports `modal`" → "only `app.py` and `modal_app/`" when the split lands (§7.1).
- **The coordinator's card list:** the split is a card of its own between card 014's deploy and card 015 or 022 (§7.1).
- **The S4 spec:** a historical note that S5 closed the deferred minors (§8.2), or the ones it deferred.
- **CLAUDE.md layout and ARCHITECTURE:** at the build, not now (`modal_app/`, `producers/`, `media/`).
