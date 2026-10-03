# Studio HK: the hook library (design)

Date: 2026-10-02 · Card: [020](../../cards/020-hk-hooks-design.md) · Status: **approved by the owner section by section (2026-10-02), for review at checkpoint A.** Decision log #550–#579.

Builds on, and doesn't reopen: ADR-8 (cache keys), ADR-18 and ADR-20 (key words and the hook title card), ADR-31 and log #340 (the Timeline's one ASS overlay), ADR-42 (versioned setup, experiments), ADR-43 (derived `producer_version`), ADR-44 (one home per task), ADR-45 (notification budget), ADR-48 (autopilot), ADR-49 (the 5-item producer window), **ADR-50 (the hook library)**. Outline: the [S3 dashboard spec](2026-10-01-studio-s3-dashboard-design.md) §3.6, §7.3 (Hooks tab), §8.5, §8.7. Facts: [07](../../studio/07-channel-portfolio.md) (the hook in the first 3–5 s), the [X4 report](../../studio/spikes/x4-visuals-music.md) (the moving hook frame, rule 2; the title card on stories, rule 7), [S2 spec](2026-10-01-studio-s2-design.md) §3, §5.2–5.3 (review counting), [S3c spec](2026-09-30-studio-s3-workspaces-design.md) §3.1, §4.1–4.4.

## 0. Goal and scope

Hooks are the lever the owner most wants to improve (ADR-50). This card designs the library that lets every producer rotate hook patterns per item, records exactly which pattern and version shipped, and ranks patterns per account so the owner can move weights with evidence.

**In scope:**
- versioned hook patterns per account, shareable to the blueprint, with a seed library for each clips account;
- a frozen rotation per job, a deterministic weighted pick per clip, and a stamp on every item and in `metadata.json`;
- clip variants in the captions stage (one `keywords_v3` call), released behind a flag;
- the freeze during setup experiments, owner-set weights, ranking before and after S7, 👍/👎 on the dashboard;
- one interface that S6's story producer uses from its first video (first line, hook frame, title card);
- **re-rendering one item** with another pattern or title (G21 in the S3 dashboard spec, assigned to this build by the coordinator);
- admin routes, a CLI, an interim `/hooks?account=` page, and the `hook_weak` digest row.

**Out of scope:** the Hooks tab inside S3c's workspace (S3c builds it on these routes); S7's metrics pull (this design only says how hold rate and views join the ranking); story pattern seeds (S6 seeds them with its accounts); automatic weight changes (owner ruling, §4.3).

### 0.1 Owner rulings (2026-10-02, card 020 action 1)

| # | Question | Ruling |
|---|---|---|
| R1 | One prompt or two for clip variants | **One `keywords_v3` call** writes the caption key words, the variants, its ranking and the key word of the shipped line |
| R2 | How the shipped hook is chosen | **The weighted draw picks one pattern; the LLM writes 2–3 lines in that pattern and its best line ships.** Exposure follows the weights exactly, so per-pattern results aren't skewed by the LLM's taste. This reads ADR-50's "2–3 variants per item from approved patterns" as variants *of* the drawn pattern; ADR-50 doesn't change |
| R3 | Seed library | **5 patterns plus a control per clips account, at equal weight, approved by approving this spec** (§4.1) |
| R4 | Where 👍/👎 lives | **Dashboard only** (S3's Review page and the Hooks tab). Telegram's review cards stay approve/reject (#427) |
| R5 | The freeze | **A snapshot owned by the hooks service** (`hook_freezes`), opened and closed by S3c's experiment service through S3c's `HookFreezer` protocol (coordinator, 2026-10-02); library edits stay allowed and apply at release |
| R6 | Release against #439's bundling rule | **Behind `HOOK_VARIANTS` (default off), flipped on alone right after the build deploys**, accepting one 5-item window per clips account (about 15 reviews). Bundle only if another clips stage or prompt bump is due the same week |
| R7 | Who moves weights | **The owner, with suggestions.** Weights change only on a tap; the system ranks and suggests |
| R8 | Where the pick happens (the owner's change to §1) | **In the clip step, before captions**, from the job's frozen rotation, seeded by `source_hash`, `start`, `end` and the rotation's id. The chosen `pattern_id@version` is an explicit captions input in its cache key. Weights stay out of the cache |

Coordinator additions (2026-10-02): the re-render route (G21, §6); the landing order now includes S3's migration (§3.3); routes mount on `web` behind the bearer token until S3-1's `admin` endpoint exists (§7.1).

## 1. Contracts (`models.py`, rule 2)

```python
HookFit = Literal["clips", "story", "avatar"]
HookStatus = Literal["draft", "approved", "retired"]

class HookPatternData(Contract):          # the versioned body; an edit writes v+1
    name: str = Field(max_length=40)
    structure: str = Field(max_length=300)      # the instruction the LLM follows
    examples: dict[str, str] = {}               # language -> example line (each ≤ 120 chars)
    fits: list[HookFit]                         # which producers may draw it
    max_words: int = Field(default=10, ge=2, le=10)   # the title card shows at most 10
    frame_brief: str | None = Field(default=None, max_length=300)  # story: what frame 0 shows
    control: bool = False                       # ship the producer's own line unchanged

class HookPattern(Contract):
    id: str                                     # "hp_" + 8 base32 characters
    account_id: str | None                      # exactly one of account_id / blueprint_name
    blueprint_name: str | None
    status: HookStatus
    current_version: int

class HookPatternVersion(Contract):
    pattern_id: str; n: int; data: HookPatternData
    author: str; note: str | None; created_at: datetime

class RotationEntry(Contract):
    pattern_id: str; version: int; weight: float = Field(gt=0)
    data: HookPatternData                       # the version's body, so steps never read the DB

class HookRotation(Contract):                   # frozen on the job at create_job
    account_id: str
    entries: list[RotationEntry]
    frozen_by: str | None = None                # the experiment id when a freeze snapshot was used
    @property
    def id(self) -> str: ...                    # sha256 of the sorted (pattern_id, version, weight)[:16]

class HookPick(Contract):                       # what the clip step passes to captions
    pattern_id: str; version: int; data: HookPatternData

class HookVariants(LLMOutput):                  # shared reply sub-model (clips and story)
    variants: list[str] = Field(min_length=1, max_length=3)
    best: int

class HookResult(Contract):                     # stage output, cached with captions
    pattern_id: str | None                      # None: a manual title (re-render, §6)
    version: int | None
    variants: list[str] = []                    # as written, before cleaning
    chosen: int | None = None
    text: str                                   # the shipped line (the title card's text)
    fallback: bool = False                      # rule 5 failed twice: the producer's own line shipped
    manual: bool = False                        # a title given in a re-render

class HookStamp(Contract):                      # the item's record
    result: HookResult
    rotation_id: str | None
    weights: dict[str, float] = {}              # "<pattern_id>@<version>" -> weight, from the job's rotation
    frozen_by: str | None = None
```

Additive changes to existing contracts (all optional, so cached results and stored jobs still validate):
- `JobInput.hooks: HookRotation | None = None`, frozen by `service.create_job` (§2.1).
- `CaptionFiles.hook: HookResult | None = None`.
- `RenderedClip.hook: HookResult | None = None`, `PackagedClip.hook: HookStamp | None = None` (so the stamp lands in `metadata.json`).
- `ContentItem.hook_stamp: HookStamp | None = None`; `ContentItem.superseded_by: str | None = None`.
- `KeywordsReply` gains `variants: list[str] | None = None` and `best: int | None = None` for `keywords_v3`; its docstring is corrected from `keywords_v1` (§2.6).

## 2. Clip variants

### 2.1 Where each step happens

| Moment | Who | What |
|---|---|---|
| Job created | `service.create_job` | Resolves the account's rotation (§4.2) and freezes it as `JobInput.hooks`. No account, no database or a database error: `None`, and the job metadata records `hooks: "unavailable"` (best-effort, like S1's `jobs` row). An edit mid-job never changes a running job |
| Clip step, before captions | `pipeline/steps.clip_step` → `stages/runner.py` | `hooks.rotation.pick(job.input.hooks, seed)` with `seed = sha256(source_hash, f"{start:.3f}", f"{end:.3f}", rotation.id)`. Pure: retries, duplicated spawns and resume pick the same pattern. Returns a `HookPick` or `None` (empty rotation). Skipped while `HOOK_VARIANTS` is off (§2.5) |
| Captions | `stages/captions.run(ctx, spec, transcript, deps, pick)` | Writes the variants in the `keywords_v3` call (§2.3); returns `CaptionFiles` with `hook` |
| Render, package | unchanged stages | `RenderedClip.hook` and `PackagedClip.hook` carry the result; the Timeline contract doesn't change (the overlay's text changes, so render re-runs) |
| Enqueue | `posting/enqueue.items_for` | `ContentItem.hook_stamp = HookStamp(result, rotation.id, rotation weights, frozen_by)`; `ContentItem.title` = the shipped text, so the post copy matches the video. `ClipCandidate.title` keeps the highlights title |

Stage modules stay free of database and Modal code: the rotation arrives inside the job record (ADR-9, ADR-12).

### 2.2 Cache key (ADR-8)

- With the flag **off**, the captions key is exactly today's (`STAGE_VERSION` "3", `keywords: "keywords_v2:<model>"`), pinned by a test.
- With the flag **on**, `STAGE_VERSION` is "4", the prompt is `keywords_v3`, and the key gains `hook = "<pattern_id>@<version>:<sha256 of the version's data>[:16]"` or `"none"`. The pick is an input; the stamp's weights are not, because they are attached at enqueue from the job's own rotation (R8). Same moment and same pattern: a cache hit. Another pattern: only captions and render re-run.
- Highlights' cache is untouched: its `title` stays the source line for every account.

### 2.3 `prompts/keywords_v3.md`

A new file (rule 4), recorded in `prompts/metadata.json` (`released`, `model_default: claude-haiku-4-5`, notes "keywords_v2 plus 2–3 hook lines in the drawn pattern and the best one's key word (ADR-50)"). One Haiku call, with `{language}`, `{words}`, `{max_keywords}`, `{source_title}` and `{hook_task}`:
- **A non-control pattern:** `{hook_task}` (built by `hooks.variants.render_task`) gives the pattern's name, structure, the example for the language (or the first one), `max_words`, and asks for 2–3 lines in the clip's language, built from what is actually said in the clip, and for the best one. Reply: `{"keywords": [...], "variants": ["...", "..."], "best": i, "title_keyword": j}`, where `j` indexes the words of the best line.
- **The control, or no pick:** `{hook_task}` says "use the title as given"; the reply has `keywords_v2`'s shape and `title_keyword` indexes `{source_title}`.

### 2.4 Validation and fallback (rule 5)

- Each variant goes through `captions.title_words()` (ASS control characters stripped, uppercase, at most 10 words). A variant is invalid when it is empty after cleaning or longer than `max_words`; `best` must index a valid variant; `title_keyword` must be in range of the **cleaned** best line.
- An invalid reply is retried once with the error, as today. After two failures the clip ships the highlights title with plain white captions, and `HookResult.fallback = true` with the drawn pattern recorded. Fallback items are excluded from the pattern's rates, and the fallback rate is shown per pattern (a high one means the pattern is hard to write).
- The caption key words keep today's limits (`_limit`: one per line, one per 4 words).

### 2.5 The release flag (R6)

`Settings.hook_variants: bool = False` (`HOOK_VARIANTS`).
- **Off:** `captions.stage_version(settings) == "3"`, `captions.keywords_prompt(settings) == "keywords_v2"`, so `producer_version` is byte-identical to today's (pinned). Every item ships today's title, so the pick is skipped and the item is stamped with the account's **control** pattern (`HookResult(pattern_id=<control>, version=<its version in the rotation>, text=<highlights title>)`); with no rotation, no stamp. Stamps always say what shipped.
- **On:** "4", `keywords_v3`; `runner.producer_version` reads the stage version and prompt name through the same two functions, so the clips `producer_version` changes once, opening ADR-49's window of 5 items on each clips account (about 15 reviews across realtalk, founder.tapes and hombre).
- The owner flips it on alone right after HK-2 deploys, unless another clips stage or prompt bump is due the same week (then they ship together, #439).

### 2.6 The `keywords_v1` comment fix

The first code task corrects the comments and docstrings that still say `keywords_v1` while the code loads `keywords_v2`: `src/clipforge/stages/captions.py` (module docstring and `CaptionsDeps.prompt`), `src/clipforge/models.py` (`KeywordsReply`) and `tests/stages/test_captions.py` (~line 119).

### 2.7 Cost (rule 7)

The call is recorded under the captions stage, as today. `keywords_v2` costs about $0.0013 per clip (about 1.1K tokens in, 40 out). `keywords_v3` adds about 400 in and 150 out, about +$0.0012, so **about $0.0025 per clip item** all in. Splitting it into a separate "hooks" stage would split one call's tokens artificially; §10 proposes that S3's Costs label the line "captions (incl. hook variants)".

## 3. Data

### 3.1 Tables

| Table | Columns | One writer |
|---|---|---|
| `hook_patterns` | `id text PK`, `account_id FK NULL`, `blueprint_name text NULL`, `status text` (`draft`, `approved`, `retired`), `current_version int`, `control bool`, `created_at`, `updated_at`; check: exactly one of `account_id`, `blueprint_name` | `hooks/library.py` |
| `hook_pattern_versions` | `pattern_id FK`, `n int`, `data jsonb` (`HookPatternData`), `author text NOT NULL`, `note text NULL`, `created_at`; PK `(pattern_id, n)`; **append-only**: a trigger rejects UPDATE and DELETE (as S3c's `*_versions`) | `hooks/library.py` |
| `hook_weights` | `account_id FK`, `pattern_id FK`, `weight float NOT NULL CHECK (weight >= 0)`, `updated_by`, `updated_at`; PK `(account_id, pattern_id)` | `hooks/library.py` |
| `hook_freezes` | `id identity`, `account_id FK`, `experiment_id text`, `rotation jsonb` (`HookRotation`), `frozen_at`, `frozen_by` (actor), `released_at NULL`, `released_by NULL`; partial unique index on `account_id WHERE released_at IS NULL` | `hooks/library.py` |
| `hook_ratings` | `item_id PK FK content_items`, `rating smallint CHECK (rating IN (-1, 1))`, `actor`, `at` | `hooks/ratings.py` |
| `hook_events` | `id identity`, `at`, `actor`, `account_id NULL`, `pattern_id NULL`, `kind` (`seeded`, `created`, `version`, `approved`, `retired`, `shared`, `weight`, `frozen`, `released`, `rated`, `rerendered`), `data jsonb` (from → to, reason); **append-only** by trigger | `hooks/library.py`, `hooks/ratings.py`, `hooks/rerender.py` (each its own kinds) |

New columns on `content_items`: `hook_pattern_id text NULL`, `hook_version int NULL` (composite FK to `hook_pattern_versions`), `hook_weights jsonb NULL`, `hook_result jsonb NULL` (variants, chosen, fallback, manual, the rotation id, `frozen_by`), `superseded_by text NULL FK content_items`. Written once, at enqueue (the stamp) or by `hooks/rerender.py` (`superseded_by`); NULL for items made before HK.

Every `actor` and `author` column uses the S2 actor format (`telegram:`, `web:`, `session:`, `cli:`, `system:`; at most 80 characters) with the same check constraint. The seeds use `system:migration`.

### 3.2 Item records outside Postgres

- `metadata.json`: `PackagedClip.hook` (the full `HookStamp`).
- The Dict (`STATE_READS=dict`, until S1 Task 23): the posting item keeps today's fields; the stamp lives in Postgres and `metadata.json` only. `posting verify` compares neither the stamp nor `superseded_by`; the superseded item's reject is Dual-written (§6), so verify stays at 0.

### 3.3 The migration

- Expand-only, **the next number in landing order**: S2a's 0002 first, then whichever of the hooks, S3 and S3c migrations lands next, one at a time (S3 dashboard spec §8.7, log #438, #141; the coordinator added S3's on 2026-10-02). The number is assigned at landing (the next after `main`'s head), and the same change moves `EXPECTED_HEAD` in `src/clipforge/db/doctor.py`. A hooks migration waiting behind another rebases and renumbers.
- It doesn't repeat 0002's deferred items (`jobs.error`, `post_events.actor`, the pause actor). If, against the plan, it lands before S2a's 0002, it carries them (#438).
- Downgrade drops the new tables and columns. The round-trip and empty-autogenerate tests stay green.

## 4. The library, rotation, freeze and weights

### 4.1 The seed library (R3)

`clipforge hooks seed [--account <id>] [--dry-run]` writes, for each `clips` account without patterns, six approved patterns at weight 1.0, version 1, actor `system:migration`. Idempotent (an account with any pattern is skipped). Language of the example shown to the LLM: the account's.

| Name | Structure (given to the LLM) | Example EN | Example ES |
|---|---|---|---|
| **Highlight title** (control) | Ship the clip's own title unchanged | — | — |
| **Number + stakes** | Lead with a specific number from the clip and what it cost or won | `$40K GONE IN ONE WEEK` | `40 MIL PERDIDOS EN UNA SEMANA` |
| **Open question** | A question the clip answers, without giving the answer | `WHY DID HE WALK AWAY?` | `¿POR QUÉ LO DEJÓ TODO?` |
| **Bold claim** | The speaker's strongest claim, stated flatly | `COLLEGE IS A SCAM` | `LA UNIVERSIDAD ES UNA ESTAFA` |
| **Contrarian** | Name the common belief, then flip it | `EVERYONE SAYS SAVE. DON'T.` | `TODOS DICEN AHORRA. NO.` |
| **The moment when** | The turning point as a scene: "the day…", "the moment…" | `THE DAY I GOT FIRED` | `EL DÍA QUE ME DESPIDIERON` |

All six have `fits = ["clips"]`, `max_words = 8` (the highlights prompt's limit today), and `control = true` only for the first. The control ships about 1 item in 6 and is the baseline every other pattern is judged against. Approving this spec approves the six (R3); the owner edits them from the Hooks page or the CLI like any pattern.

### 4.2 Rotation (`hooks/rotation.py`, pure)

- `resolve(patterns, weights, open_freeze) -> HookRotation`: an open freeze's snapshot wins; otherwise the approved patterns whose `fits` include the producer, with weight > 0, at their **current** versions. Patterns shared to the account's blueprint are included with the account's own weight row (0 until the owner sets one).
- `pick(rotation, seed) -> HookPick | None`: a weighted draw from `int(seed, 16) / 2**256` over the entries in `(pattern_id, version)` order. `None` when the rotation is empty: the producer behaves as the control and stamps nothing.
- `hooks/library.py::rotation_for(account_id, producer, now) -> HookRotation` reads the tables and calls `resolve`; `service.create_job` calls it.

### 4.3 Weights (R7)

- Only an owner tap changes a weight: the Hooks page, `clipforge hooks weight <pattern> <weight> --account <id> --reason`, or `PUT /hooks/{id}/weight`. Each change writes a `weight` event (from → to, reason, actor).
- Approving a draft sets its weight to 1.0 unless one is given. Retiring sets it to 0 and keeps the history; a retired pattern can be approved again.
- The system **suggests** (§5): "likely worse than control" suggests halving or retiring; "likely better" suggests doubling. A suggestion is a button that pre-fills the change; nothing moves on its own.

### 4.4 Freeze during setup experiments (R5)

- **The contract is S3c's `HookFreezer` protocol** (card 018's plan; coordinator, 2026-10-02), which takes the caller's connection:
  ```python
  class HookFreezer(Protocol):
      def freeze(self, conn: Connection, account_id: str, experiment_id: str) -> None: ...
      def release(self, conn: Connection, account_id: str, experiment_id: str) -> None: ...
  ```
  S3c's experiment start, stop and decide (keep or revert) call it **inside their own transaction**, for every account in the experiment's scope. Until the hooks build, `runtime.build_deps` wires S3c's no-op.
- **The hooks build implements it** as `hooks/library.py::SqlHookFreezer` on `hook_freezes` (the one writer) and wires it in `runtime.build_deps` in place of the no-op. `freeze` stores the live rotation (as `resolve` would build it now) and `release` closes the open row; both run on the given connection, are idempotent, and write `frozen` and `released` events with actor `system:experiment` and the experiment id in `data` (the protocol carries no actor; the person who started or decided the experiment is on S3c's own records).
- **If the hooks build deploys after S3c-3** (experiments already running), `clipforge hooks seed` freezes each running experiment's accounts right after writing their patterns, through the same `SqlHookFreezer` and S3c's read of running experiments. That's the one-off that creates the library, so no account can rotate unfrozen during a running experiment. Before S3c-3 there is nothing to freeze, and the step reports "0 running experiments".
- While a freeze is open, `rotation_for` returns the snapshot. Edits, approvals, retirements and weight taps are still saved (the library is never blocked, ADR-50) and apply at release. The Hooks page shows ❄ and "changes apply when experiment <id> ends". So both sides of an experiment rotate hooks the same way, and the weights in force are on every item.
- An open freeze whose experiment is no longer `running` (a crash between the two writes) becomes a digest line once S3c exists; it is never released silently.

### 4.5 Sharing

`share(pattern_id, actor)` moves an account pattern's scope to its account's blueprint (`account_id` → NULL, `blueprint_name` set), keeping its id and versions. The other accounts on that blueprint (the EN/ES pairs, ADR-35) see it approved at weight 0. An edit by any of them writes the next version for all; each job freezes the version current at its creation.

## 5. Ranking (`hooks/stats.py`, pure, derived on read)

No cron and no stored scores: `GET /hooks/{id}/stats` and the Hooks page compute them from the items, verdicts, review events, ratings and (after S7) metrics.

**Per pattern** (versions pooled, with a per-version breakdown), compared with the account's **control**:

| Measure | Definition | From |
|---|---|---|
| Items | stamped items, excluding superseded and fallback | `content_items` |
| Fallback rate | fallback ÷ stamped | `hook_result` |
| Posted rate | posted on ≥ 1 platform ÷ decided (S3c §4.1) | verdicts, `posts` |
| Reject rate | rejected ÷ decided (S3c §4.1), excluding `superseded` | verdicts |
| Approval rate | approved ÷ counted review decisions (S2 §5.2: person actors only, R2) | `post_events` (`approved`, `reviewed`), from S2b |
| 👍 share | 👍 ÷ rated | `hook_ratings` |
| After S7: 3-second hold, views at 24 h | median with p25–p75, items past their maturity age (48 h) only | S7's metrics tables |

- **Verdicts** follow S3c §4.3: a 90% Wilson interval per rate, **too few items** below 10 decided on either side, then **likely better**, **no clear difference** or **likely worse** against the control. Continuous metrics compare p25–p75 ranges.
- **Weak** = likely worse than the control on the reject rate, the approval rate or the 👍 share, with ≥ 10 decided items each. `hooks.stats.weak(account_id) -> list[WeakPattern]` feeds the `hook_weak` "needs me" row (S3 §7.11) at **digest** level only (ADR-45), with a suggested weight.
- Settled only: an item still queued or undecided counts as pending, never as a failure.

**Ratings (R4):** `hooks/ratings.py::rate(item_id, rating, actor, now)` upserts `hook_ratings` (the latest wins) and writes a `rated` event. Only the dashboard calls it (`PUT /items/{id}/hook-rating`); Telegram doesn't change.

## 6. Re-rendering one item (G21)

The S3 Review page's "re-render" (and the Hooks page's "try this pattern on this item") call one service.

- **Route:** `POST /items/{id}/rerender` with `{"pattern": "<pattern_id>@<version>"}` or `{"title": "..."}`, and `?preview=true` for the cost line. The handler calls `hooks/rerender.py::request(item_id, choice, actor, now)` (Modal-free), which validates and spawns `rerender_step(job_id, clip_id, choice)` in `app.py`.
- **What runs:** only captions and render for the same `ClipSpec` (same source, start and end), from the cached transcript, highlights and reframe. A pattern runs `keywords_v3` with that pick; a title runs it in control mode with the given title as the source line (key words only), and the result has `manual = true` and `pattern_id = None`.
- **The new item:** id `<job_id>:<clip_id>r<N>` (N = 1, 2, …), a new stamp (the job's rotation weights, plus the actor in the `rerendered` event), the old item's platforms and its place in the queue (S2's planner keeps the slot; before S2, the assisted pick sees the new item with the old one's score and episode).
- **The old item:** `superseded_by` is set, and it leaves the queue through `posting/actions.reject(posting, ref, actor, now)` (Dual-written, so `posting verify` stays at 0) with no reason, plus a `superseded` `post_events` row. Superseded items are excluded from review counts (S2's windows and ladder), the reject rate and hook stats.
- **Refused** (409, with the reason) when any platform of the item is posted, handed off or in flight (`publishing:inflight:<ref>`), or when the item is already superseded. A missing source video is a `PermanentError` with "the source is gone".
- **Cost:** one captions call (about $0.0025) and one render (about $0.005–0.01 of CPU), shown by `preview` before the owner confirms; recorded on the job's costs like any clip.
- **S3's Review button** stays disabled until HK-2 ships (the route answers 404 before then).

## 7. Surfaces

### 7.1 Routes

| Route | What |
|---|---|
| `GET /accounts/{id}/hooks` | the library: pattern, version, status, scope, weight (❄ when frozen), items, rates with intervals, verdicts |
| `POST /hooks` | create a **draft** (also + Hook idea's target, S3 §1) |
| `PUT /hooks/{id}` | a new version (`data`, `note`) |
| `POST /hooks/{id}/approve`, `/retire`, `/share` | status and scope changes |
| `PUT /hooks/{id}/weight` | `{account_id, weight, reason}` |
| `GET /hooks/{id}/stats` | §5 for one pattern, with versions |
| `PUT /items/{id}/hook-rating` | `{rating: 1 | -1}` |
| `POST /items/{id}/rerender` | §6 |

They mount on S3-1's **`admin`** endpoint when it exists. If the hooks build lands first, they mount on **`web` behind the bearer token** (as S1's `/accounts` and `/sources` routes do today) and move to `admin` with S3-1 (coordinator, 2026-10-02). Every write takes an actor; errors answer "Store unavailable, nothing changed" like `posting/actions`.

### 7.2 CLI

`clipforge hooks list|show|add|edit|approve|retire|share|weight|seed|stats`, thin clients of the routes (ADR-2), actor `cli:<os user>`.

### 7.3 Pages and links

- **Interim page** `/hooks?account=<id>` in `web/`: the library table, ❄ and the freeze notice, the approval rate per pattern as a dot with its 90% interval and direct labels (plus a table view), Edit (v+1), Approve, Retire, Share to blueprint, Weight with the suggestion pre-filled, and the recent items with 👍/👎.
- **The Hooks tab** at `/accounts/<id>?tab=hooks` in S3c's workspace replaces it; `/hooks?account=<id>` then redirects there. Both paths join the link contract (S3 §7.10), so cards 018 and 019 can link them now.
- **Digest:** the `hook_weak` row ("realtalk: 'Contrarian' is likely worse than the control on rejects, 4 of 12 → set weight 0.5?") links to `/hooks?account=<id>` (later the tab). Never instant.

## 8. Story hooks (S6) on the same interface

X4 found that the story's hook is a beat, not a caption: frame 0 is a striking image that moves from the start, and the first sentence and the first image are one beat (X4 rule 2); the clip producer's captions, title card included, run on stories too (rule 7). One pattern therefore describes the hook beat, and each producer renders it with the media it has:

| Producer | What the drawn pattern produces |
|---|---|
| clips | the title card's text (§2) |
| story (S6) | the script's **first line** (spoken), the **hook frame** brief from `frame_brief` for the shot planner's frame 0, and the same line on the title card |
| avatar (S8) | the script's first line |

- **One library, one draw, one stamp per item.** A pattern's `fits` says which producers may draw it; story patterns are seeded by S6 with its accounts.
- **The shared interface** (`hooks/variants.py`): `render_task(pick, language, n=3) -> str` (the prompt block), `HookVariants` (the reply sub-model each producer embeds in its own versioned prompt's reply), and `settle(reply: HookVariants | None, fallback_text, pick) -> HookResult` (cleaning, rule 5's fallback). Rotation and stamping are `hooks/rotation.py` and `HookStamp`, as for clips.
- **S6's use:** its `create_job` freezes a rotation for `story`; its script step picks with `seed = sha256(brief hash, rotation.id)`, puts `render_task` into its script prompt, writes the best opening as the first line (07: in the first 3–5 s, never "welcome back"), passes `frame_brief` to the shot plan, and stamps the item. The fallback is the script's own first line. About 2K tokens in and 300 out more than a script without hooks: **about $0.0035 per story item**.

## 9. Build, tests, safety, rollback, cost

### 9.1 Three deployable parts (one build card, a checkpoint per part)

| Part | Contents | Owner steps | The owner sees |
|---|---|---|---|
| **HK-1** data and library (flag off; clip output unchanged) | the `keywords_v1` comment fix first; contracts; the migration (numbered at landing, `EXPECTED_HEAD`); `hooks/library.py` (with `SqlHookFreezer`, wired in `runtime.build_deps`), `rotation.py`; `hooks seed` (freezing running experiments, §4.4); `JobInput.hooks` at create; control stamps at enqueue and in `metadata.json`; routes and CLI | migrate (`DATABASE_URL_UNPOOLED`, the runbook's way), `scripts/deploy.sh --dry-run`, deploy, `clipforge hooks seed`, then one clip job: its item shows `hook_pattern_id` = the control | `clipforge hooks list --account realtalk-clips-en` shows six patterns |
| **HK-2** variants | `keywords_v3` and `metadata.json`; the flag; the pick in the clip step; `HookResult` through captions, render, package; `ContentItem.title` = the shipped text; `stats.py`, `ratings.py`, `weak()`; re-render | deploy; set `HOOK_VARIANTS=true` (docs/ops/secrets.md's add-only procedure) and redeploy; review the 5-item windows | the first clip with a rewritten title card, its stamp and its variants in `metadata.json` |
| **HK-3** interim page | `/hooks?account=` in `web/` | after S3's dashboard build has the admin client; otherwise it folds into S3c's Hooks tab | the page on the phone and the laptop |

### 9.2 Tests

- Versions and events are append-only (UPDATE and DELETE rejected); a pattern edit writes v+1 and leaves v intact.
- `pick` is deterministic for a seed and follows the weights (a χ² check over 6,000 seeds); an empty rotation returns `None`.
- Captions: the same pattern is a cache hit; another pattern re-runs captions only; with the flag off the key and `producer_version` are byte-identical to today's (pinned values).
- Rule 5: one retry with the error, then the highlights title with `fallback = true`; `title_keyword` is checked against the cleaned best line; a variant over `max_words` is invalid.
- Every new clip item is stamped; the stamp's text equals the title card's text; its weights are the job's rotation's.
- During a freeze, edits and weight taps are saved but the rotation is the snapshot until release.
- `SqlHookFreezer` writes on the caller's connection: when the caller's transaction rolls back, no freeze row or event remains; `freeze` and `release` are idempotent; `hooks seed` freezes the accounts of experiments already running.
- Stats: Wilson intervals, the 10-item floor, the verdict labels, and the superseded and fallback exclusions; `weak()` needs ≥ 10 decided items.
- Re-render: refused when posted, handed off, in flight or already superseded; the old item leaves the queue with `posting verify` at 0; the new item keeps the slot; cost recorded.
- Routes: actors validated, 503 without the token, the "Store unavailable" path.
- Cost recorded for every call. DB tests use the `db` fixture and fail, never skip, without Postgres. The LLM is mocked.

### 9.3 Safety

- Pattern text and LLM lines go through `title_words()` before the ASS file, so neither can inject styling (the #340 overlay path).
- Field lengths are capped in `HookPatternData`; pattern ids are validated before any query.
- No secrets in patterns, stamps or logs (rule 8).

### 9.4 Rollback

- **The variants:** set `HOOK_VARIANTS=false` and redeploy. The old captions keys still hit, `producer_version` returns to today's, and stamps go back to the control.
- **The build:** a revert deploy. The migration is expand-only; items keep their stamps; nothing reads the new columns after the revert.

### 9.5 Cost

| What | Per item | Notes |
|---|---|---|
| Clip variants | about $0.0025 (about $0.0012 more than today's captions call) | Haiku 4.5 at $1/M in, $5/M out |
| Story variants (S6) | about $0.0035 | inside the script call |
| Re-render | about $0.0025 + $0.005–0.01 CPU | only when the owner asks |
| Monthly, 03's scenario 2 (about 1,000 items) | about $3 | |

Owner attention: 👍/👎 is optional (about 0 minutes); weights are a few taps a week, prompted by the digest's `hook_weak` row.

## 10. Proposed changes to other documents

### 10.1 04 (roadmap), HK section (this card edits it at checkpoint B)

The HK list gains: the seed library, the `HOOK_VARIANTS` flag and its one-time window, the freeze snapshot called by S3c, owner-set weights with suggestions, re-render (G21), the interim page, and the three parts HK-1 to HK-3. Exit unchanged.

### 10.2 08 (this card edits it at checkpoint B)

§2c: the Hooks tab's home and the interim `/hooks?account=` page; 👍/👎 is dashboard-only (no Telegram home); `hook_weak` is a digest row; the new link paths.

### 10.3 05

No new ADR: the design stays within ADR-50. The freeze is a snapshot table instead of the outline's `frozen_by_experiment` column, and the variants are written in the drawn pattern (R2); both are readings of ADR-50, not changes to it.

### 10.4 The S2 spec and plan (for card 014/015's owner, via the coordinator)

- §5.2's counted decisions exclude items with a `superseded` event.
- The actor check already allows `system:`; nothing else changes.

### 10.5 The S3 dashboard spec and plan (card 019)

- §8.5: "a 'hooks' stage in Results → Costs" becomes "captions (incl. hook variants)" (§2.7).
- §7.5 Review: the re-render button calls `POST /items/{id}/rerender` (disabled until HK-2) and 👍/👎 calls `PUT /items/{id}/hook-rating`.
- §7.10: add `/hooks?account=<id>` and `/accounts/<id>?tab=hooks`.
- §8.7: the landing order includes S3's migration (coordinator, 2026-10-02).
- S3-1 moves the hooks routes from `web` to `admin` if HK landed first.

### 10.6 The S3c spec and plan (card 018)

- §2.6 and §5: S3c defines the `HookFreezer` protocol (`freeze(conn, account_id, experiment_id)`, `release(conn, account_id, experiment_id)`), calls it in experiment start, stop and decide inside their own transaction for every account in scope, and wires a no-op in `runtime.build_deps` until the hooks build replaces it with `SqlHookFreezer` (§4.4). Card 018's plan already carries this (coordinator, 2026-10-02).
- §2.5: the Hooks tab is built on §7.1's routes; `/hooks?account=` redirects to it.
- §4.1: hook metrics stay on the Hooks tab, not in the experiment metric registry (already proposed by the S3 spec §10.3).
- An open freeze whose experiment isn't running becomes a digest line ("hooks frozen by a finished experiment").

### 10.7 S6 (card to be written)

S6's story producer uses §8's interface from its first version and seeds story patterns for its accounts.
