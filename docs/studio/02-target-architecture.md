# 02: Target architecture

This file extends the existing design (`docs/ARCHITECTURE.md`, ADR-1…46) and doesn't replace it. The rules in CLAUDE.md all still hold:
- stages are pure and resumable
- contracts live in `models.py`
- prompts are versioned files
- LLM output is JSON-validated
- cost is logged
- no secrets in code
- no evasion features

## 1. The big picture

```
                 ┌──────────── Next.js dashboard (Vercel Pro, Auth.js, hey-api client) ───────────┐
                 │  accounts · queue/calendar · submit · review · stats · money · costs            │
                 └───────────────────────────────┬───────────────────────────────────────────────────┘
 Telegram (phone) ──webhook──┐                    │ HTTPS (bearer + Modal proxy auth)
 CLI / local fetch ─HTTPS────┼──► Modal web (FastAPI): jobs · accounts · items · posts · stats · /go/<slug>
                             │           │                    │
                             │           ▼                    ▼
                             │   PRODUCERS (step chains)   Postgres (Neon): accounts, items, posts,
                             │   clips │ story │ band │     metrics, links, clicks, costs, budgets
                             │   avatar │ dub               ▲
                             │           │                  │
                             │   MEDIA SERVERS (modal.Cls on GPUs, weights on Volume, snapshots)
                             │   whisper(L4) · tts(L4) · image(L40S) · talking-head(H100) · music(L4) · broll(H100)
                             │           │
                             │           ▼
                             │   Timeline → render (CPU, ffmpeg+libass) → ContentItem + policy gate
                             │           │
                             │           ▼
                             └── DISTRIBUTION: review tiers (Telegram) → Publisher (Upload-Post API)
                                         media via signed Volume links; webhooks → posts table
                 dispatcher cron (1 cron): sweeper · posting slots · analytics pull · digests · budgets
```

The design rests on four separations:
1. **Producers vs distribution.** Every producer ends in a `ContentItem`. Distribution never knows how a video was made.
2. **Timeline vs renderer.** Every producer describes its video as a `Timeline`, and one renderer turns any Timeline into an mp4.
3. **Stage logic vs Modal.** Stages stay Modal-free. Modal code lives only in the Modal layer (today `app.py`; proposed later as a `modal_app/` package).
4. **Hot state vs durable state.** Modal Dict holds only short-lived step state. Postgres holds everything durable. **Dict entries expire after 7 days of inactivity.** ADR-24 (a keep-alive read plus a Volume snapshot) is the stopgap for the ADR-23 queue. Postgres replaces it in S1, for the queue **and** for the `job:*` records that `rebuild` and the overview scan (a `jobs` table written by `package_step` and backfilled from each job's `metadata.json`). The cron doesn't retire: it became `posting_daily` (ADR-46), and only its Dict touch goes once both have moved.

## 2. Core contracts (new, in `models.py`)

These are sketches. The spec for each sub-project fixes the fields.

```python
class Account(Contract):            # one brand, e.g. realtalk.clipsdaily
    id: str; handle: str; blueprint: str; blueprint_version: int
    kind: Literal["clips","story","band","avatar","model"]    # = blueprint.category (ADR-39)
    language: Literal["en","es"]; niche: str
    platforms: dict[Platform, PlatformProfile]   # enabled, length rules, cadence, caption template, link
    review_tier: Literal["review","sample","auto"]
    persona_id: str | None                        # voice (+ face for avatar)
    brand: BrandKit                               # caption preset, fonts, colors, CTA, bio link
    monthly_budget_usd: float
    paired_account_id: str | None                 # EN<->ES partner for translated winners

class Blueprint(Contract):          # blueprints/<name>.toml until S3c, then database versions (ADR-42; see 07)
    name: str; version: int; category: Literal["clips","story","band","avatar","model"]
    niche: str; pillars: list[str]; series: list[SeriesFormat]   # recurring formats to rotate
    voice_brief: str; visual_style: str; platform_defaults: dict[Platform, PlatformProfile]
    money: list[str]; compliance: ComplianceProfile               # required tags, banned claims, sources needed
    prompts: dict[str, str]                                        # prompt names per step (prompts/ files)

class Persona(Contract):            # synthetic identity, never a real person
    id: str; voice_ref_path: str; voice_design_prompt: str
    face_lora_path: str | None; face_ref_paths: list[str]; style_notes: str

class AssetSource(Contract):        # one per asset in a Timeline: licensing is data
    kind: Literal["source_video","generated","stock","commons","promo","music_generated"]
    license: str; attribution: str | None; url: str | None; model: str | None

class Timeline(Contract):           # what plays when; the one input to render (built in S4, 2026-10-01; loudness_lufs = -14.0)
    width: int = 1080; height: int = 1920; fps: int; duration_s: float
    visual: list[VisualSegment]     # VideoSegment (source | broll | talking_head; crop | cover | blur) | StillSegment (+ken burns)
    audio: list[AudioTrack]         # source | narration | music (ducked); two-pass loudness to -14 LUFS (ADR-47)
    overlay: Subtitles | None       # one ASS file: captions and the hook title card (no separate title_card)
    assets: list[AssetSource]       # licensing data for the policy gate; not part of the render cache key

class ContentItem(Contract):        # what distribution consumes (replaces clip-bound PostItem)
    id: str; account_id: str; producer: str; producer_version: str
    language: str; media_kind: Literal["video","carousel","image"] = "video"
    video_path: str | None; image_paths: list[str] = []; duration: float | None
    copy: dict[Platform, PostCopy]  # caption/title/description/hashtags per platform
    ai_disclosure: bool; sponsored: bool; affiliate_link_id: str | None
    suggested_sound: str | None; credits: list[str]; assets: list[AssetSource]
    score: float; cost_usd: float; parent_item_id: str | None   # for dubs
```

The podcast-clips producer wraps today's `RenderedClip` and `PostItem` into a `ContentItem`. The existing clip stages keep their contracts.

## 3. Producers (job types)

Each producer is a step chain with the same machinery as ADR-12: spawn-next, fan-out and claim, retries, sweeper, resume, and `cached_stage` (ADR-8). What changes is that **the step list is data**: a `Pipeline` registry maps a job kind to its steps. `dispatch()` and `resume()` read the registry instead of a hard-coded chain.

| Producer | Steps (GPU in brackets) |
|---|---|
| `clips` | ingest → transcribe [L4] → highlights → clip×N (reframe → captions → render) → package → items |
| `story` | brief → script (LLM, quality tier) → pre-check → tts [L4] → align [L4] → shot plan (LLM) → images×N [L40S] (+ optional b-roll [H100]) → music [L4] → timeline → captions → render → gate → item |
| `band` | research (MusicBrainz/Wikidata/Wikipedia) → asset sourcing (Commons/promo, license check) → script → tts → align → art×N [L40S] → timeline → render → gate → item (music-free, `suggested_sound`) |
| `avatar` | brief (offer + link) → script → pre-check (claims) → tts → align → talking head [H100, **presenter segments only**] + b-roll [L40S/H100] → timeline → render → gate → item |
| `dub` | winner item → translate (LLM, per-sentence timing budget) → tts (target persona) → align → re-time timeline (avatar: re-run talking head) → render → gate → item for the paired account |
| `persona` (one-off) | design voice (VoiceDesign) → reference clip → face images → LoRA training [H100] → persona record |

**Avatar cost control:** a talking head costs ~$0.35–0.55 per 30 s on an H100 (estimate). The presenter appears only in the hook and the CTA (about 6–10 s), with b-roll in between. That brings an avatar video to about $0.15–0.30.

## 4. Media servers on Modal

- Each model is a `modal.Cls` with `@modal.enter` loading weights from a **Volume** (`clipforge-models`), plus memory snapshots (GPU memory snapshots are still alpha) to shorten cold starts. Throughput models use `@modal.batched`.
- **A GPU step runs inside its model's class**, e.g. `TTS.run_step(job_id, item_id)`. The step gets a warm model, and no CPU container sits waiting on a remote call, which keeps ADR-12's no-idle-waiting rule.
- Stage logic stays Modal-free. It talks to protocols in `media/`, such as `SpeechSynth`, `ImageGen`, `TalkingHead`, `MusicGen` and `Aligner`, and tests use fakes.
- A **model registry** (`media/registry.toml`) records the model id, pinned revision, license (code, weights, dependencies), GPU and Volume path. A test fails when a registered model's license isn't on the allowlist (see 03), which blocks non-commercial models such as InsightFace packs, FLUX.1-dev and Qwen-Image 2.1.
- The Whisper image stays baked in as it is today (ADR-11).

## 5b. Judgments (the `Judge` protocol)

Decision points don't need generated text. They need a typed answer with a probability. So they go through a `Judge` protocol with three methods:
- `choice(state, options)`
- `score(state, levels)`
- `noul(state, statement)`

Each returns a value, a probability distribution and a confidence.

**Implementations:**
- `JevJudge`: TypeSafe Jev, early access, ~$0.04 per M tokens, calibrated.
- `ClaudeJudge`: Haiku with JSON output. Its confidence is self-reported and less calibrated.

Which one runs is set per decision in config, and spike X5 decides the defaults.

**Users of the Judge:**
- the policy gate's claim checks;
- review routing (auto-post above a threshold per account tier, human review in the middle band);
- hook and title variant ranking;
- reject-reason prediction;
- topic and pillar tagging;
- near-duplicate story checks.

Thresholds live in config and **scale with the cost of a wrong action**. Sponsored or affiliate items always need a higher confidence.

Every call is written to the **decision ledger**, and lanes, fail-closed rules and audit sampling follow 08 §1.

## 5. Distribution

- **Queue:** `posts` rows in Postgres (one per item × platform), replacing the `post:*` keys in the Dict. The status rules from ADR-23 carry over.
- **Scheduler:** one **dispatcher cron** every 5 minutes (Modal Starter allows only 5 crons). It handles:
  - slots per account and platform, based on cadence;
  - the sweeper;
  - pulling analytics;
  - daily digests;
  - budget checks.
- **Review:** the account's tier decides what happens:
  - `review`: send the item to Telegram and wait for a tap;
  - `sample`: auto-post, and send ~10% to Telegram for a look;
  - `auto`: post.

  Telegram buttons: ✅ approve, ✏️ fix copy, ⏭ skip, 🗑 reject with a reason. **Superseded by ADR-54 (2026-10-05):** review happens only on the dashboard's Review page; Telegram sends one "N items need review → Open" notification and has no decision buttons.
- **Publisher:**
  - The `Publisher` protocol has an `UploadPostPublisher` (primary) and an `AssistedPublisher` (Telegram manual post, as today). *ADR-54 (2026-10-05) drops `AssistedPublisher`: a final failure is an alert and a failure row.*
  - It maps `ai_disclosure` to TikTok `is_aigc`, YouTube `containsSyntheticMedia`, Instagram `is_ai_generated` and Facebook `facebook_is_ai_generated`.
  - Signed webhooks from Upload-Post update the `posts` rows.
  - Official APIs (YouTube Data, Instagram Graph) can be added later as more publishers behind the same protocol.
- **Media hosting (ADR-28):** the posting API and the dashboard fetch rendered mp4s through signed, expiring links to the Volume (ADR-13's mechanism). Cloudflare R2 (long, unguessable keys, free egress) comes in only if those links prove unreliable.
- **Policy gate:** a pure function, `gate(item, account) -> list[Violation]`, plus one cheap LLM check for banned claims. It runs before publish in every tier.

## 6. Measurement

- **Analytics pull** (dispatcher, daily): Upload-Post analytics per post and account, plus the YouTube Analytics API where it's connected. Results go to `post_metrics_daily` and `account_metrics_daily`.
- **Tracking links:**
  - `GET /go/<slug>` on the Modal web app looks up a `links` row, logs a click (item, platform, time, coarse country), and returns a 302 to the affiliate URL with a sub-id.
  - It is **not hosted on Vercel Hobby**, which forbids affiliate use.
  - Sales come in from programs with APIs (ClickBank, Hotmart) or from CSV imports (Skool, Amazon, TikTok Shop).
- **Monetization progress** per account and program uses thresholds stored in a `programs` table, so the owner can edit them.
- **Winners:** a daily job flags the top decile per account after 7 days. It can queue `dub` jobs, and it feeds the Phase 5 ranker (ADR-4).
- **Cost:** every stage already logs cost (rule 7). Costs roll up per item and per account, and each account's monthly budget is **enforced before a job starts**.

## 7. Data (Postgres on Neon)

- **Tables:**
  - `accounts`, `personas`, `platform_connections` (Upload-Post profile ids, never tokens in plain text), `sources` (channels.toml moves here)
  - `jobs` (a durable mirror of job summaries), `content_items`, `assets`, `posts`, `post_events`
  - `post_metrics_daily`, `account_metrics_daily`
  - `links`, `clicks`, `conversions`
  - `costs`, `budgets`, `programs`
- **Access:** SQLAlchemy 2 + psycopg 3 from Modal through Neon's pooled endpoint. Migrations use Alembic.
- **The dashboard never touches the database directly.** It goes through the FastAPI API (ADR-2). The typed client is generated from an exported OpenAPI file (the docs routes stay off).

## 8. Dashboard (Next.js on Vercel)

- **Hosting:** Vercel **Pro**, because Hobby forbids commercial use.
- **Auth:** Auth.js with one allow-listed owner.
- **Calls to Modal:** server-side route handlers call a **second** Modal endpoint, `admin` (`requires_proxy_auth=True` plus the API bearer token), that serves only the dashboard routes. The public `web` endpoint can't use proxy auth: Telegram and Upload-Post webhooks, signed download links and `/go` can't send Modal's proxy headers.
- **Pages:**
  - accounts and personas (create, profile editor)
  - queue and calendar across accounts
  - review inbox
  - submit (clip a video, story brief, band, avatar offer)
  - item preview (from a signed Volume link)
  - stats
  - money (programs' progress, clicks, sales)
  - costs and budgets
- **Live updates:** polling every 2–5 s with TanStack Query. No SSE for now.

## 9. Local helper (the only local piece)

`clipforge fetch <url> --channel <c>` runs yt-dlp on the owner's machine and saves into `videos/<channel>/`. It needs Deno (yt-dlp's JS runtime) and the bgutil PO-token plugin. The existing `clipforge clip` flow (ADR-22) then submits the files. yoinks is fine for manual one-off downloads, but it has no scriptable mode yet. Only permitted sources are downloaded (docs/SOURCING.md).

## 10. Repo layout (proposed; `db/`, `accounts/` and `alembic/` are built in S1, `web/` has the S3a shell)

```
src/clipforge/
  models.py            # + Account, Persona, AssetSource, Timeline, ContentItem, ...
  db/                  # built (S1): engine, tables, repositories; alembic/ at repo root
  accounts/            # built (S1): blueprint loading, account service; later profiles, brand kits, budgets
  judge/               # Judge protocol + jev.py + claude.py + ledger (decisions table, lanes, audit)
  desk/                # inbound triage (after S7): sources, questions, guards, draft queue
  funnel/              # later: bio pages data, email capture, sequences, sales import
  notion_mirror/       # one-way docs + weekly report sync to Notion
  research/            # trend jobs: xAI X Search, YouTube mostPopular/comments
  producers/           # registry.py + clips/ story/ band/ avatar/ dub/ persona/
  media/               # protocols (SpeechSynth, ImageGen, TalkingHead, MusicGen, Aligner) + registry.toml
  stages/timeline.py   # Timeline builders (clips first); render stays stages/render.py (S4 spec §3)
  policy/              # gate, claim checks, disclosure mapping
  publish/             # Publisher protocol, upload_post.py, assisted.py (Telegram)
  analytics/           # pulls, winners, programs
  tracking/            # /go redirect, click logging, conversion import (not `links/`: `links.py` already holds the signed zip links)
  stages/, pipeline/, posting/, bot/, api/  # existing; posting/ migrates to db + publish/
  app.py -> modal_app/ # Modal layer only (functions, Cls media servers, dispatcher cron, web)
web/                   # Next.js dashboard (own package.json, deployed to Vercel)
blueprints/            # <name>.toml per channel concept (07); database versions from S3c (ADR-42)
```

New accounts are created from blueprints:

```
clipforge account create --blueprint <name> --lang en|es --handle <h>
```

Today (S1) this creates the account row only. Spawning the persona job is the target (S8). See 07.
