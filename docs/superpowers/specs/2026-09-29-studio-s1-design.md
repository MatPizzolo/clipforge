# Studio S1: foundations (design)

Date: 2026-09-29 · Status: approved (spec review 2026-09-29); amended 2026-09-29: sources move to the database (option B, §6.3)
Card: docs/studio/06 §D "S1", docs/studio/04 "S1". Binding: ADR-14, ADR-15, ADR-23, ADR-24, ADR-25, ADR-26, ADR-35. Background: 02 §2, §5, §7, §10; 07 (blueprint model, clip accounts).

## 1. Goal and scope

Move durable state to Neon Postgres and make the studio multi-account, without changing how posting behaves.

- **Postgres:** SQLAlchemy 2 (Core) + psycopg 3 + Alembic, on Neon's pooled endpoint.
- **Contracts:** `Account`, `PlatformProfile`, `PostingSchedule`, `BrandKit`, `Blueprint`, `SeriesFormat`, `ComplianceProfile`, `Persona`, `AssetSource`, `Source`, `SourcePermission`, `CampaignRules`, `SourceEvent`, `ContentItem`, `ClipOrigin`.
- **Posting queue:** `post:*` Dict keys become `content_items` / `posts` / `sends` rows. The ADR-23 status rules stay in `posting/queue.py`, unchanged in substance.
- **Migration:** writes go to both stores and a setting picks which one is read (approach A), with a one-off import, a `jobs` backfill and a daily verify.
- **Posting per account:** each account has its own slots, chat, time zone, hashtags and pause.
- **Blueprints:** three clip blueprints plus `clipforge account create|edit|list`.
- **Sources (option B, owner decision 2026-09-29):** the database is the only place sources are edited, starting in S1, through `clipforge source add|edit|list|show` and bearer API routes that the S3 dashboard will reuse. A source is a business record: credit, creator handles, a full permission record (type, granted when and by whom, evidence link, platforms covered, monetization, translation, expiry, restrictions), campaign terms, notes, and a change history (`source_events`). `channels.toml` is imported once (`clipforge source import-toml`) and then no longer read. `clipforge clip` only maps `videos/<source-id>/` to a source. Enqueue and the tick hold clips from a source that isn't active, whose permission has expired, or that doesn't cover the platform.
- **Tap fixes:** the two deferred from S0's final review.
- **CI:** a Postgres service for tests, and `alembic upgrade head` before `modal deploy`.

**Done when:**
- posting works as it does today, with Postgres as the store reads come from;
- 3 accounts are defined from blueprints;
- the fast tests, ruff and mypy are green.

**Out of scope:**
- `ContentItem.copy` (per-platform captions): S2. Until then, captions are still built at send time (`posting/captions.py`).
- The `personas` table (S8); the `Persona` contract is added now.
- `budgets` (S7; `accounts.monthly_budget_usd` holds the limit until enforcement) and the dispatcher's task markers (S7).
- Review tiers in action, the publisher, the policy gate (S2), the dashboard (S3), posted-URL capture (S2/S3), the persona job (S8).
- **Retiring ADR-24** (card step 9): specified here (§9.3). It runs as a separate final checkpoint after at least 7 days with Postgres as the store reads come from.

**Session ownership** (shared folder, no git repo yet): this work owns `src/`, `tests/`, `alembic/`, `alembic.ini`, `blueprints/`, `pyproject.toml`/`uv.lock` (new dependencies) and the S1 docs. The owner approved one edit outside that: `.github/workflows/ci.yml`. It never touches `web/` or `scripts/export_openapi.py` (S3a).

**Owner decisions (2026-09-29):**
- Handles are test placeholders: editable, never an identity key.
- Posting serves every account, each on its own schedule.
- ~~Sources are edited in `channels.toml` until S3~~ (superseded the same day by option B): sources live only in the database from S1 on, edited with `clipforge source add|edit` and later the S3 Sources page. `channels.toml` is imported once and then ignored, and the folder name is the source id.
- Three blueprints, one per account.
- Tests use Postgres through Docker Desktop.
- S1 edits CI.

## 2. Contracts (`models.py`)

Contracts come first, then the producers and consumers (CLAUDE.md rule 2).

```python
class PlatformProfile(Contract):
    enabled: bool = True
    handle: str | None = None          # editable label; never a key
    min_len: float | None = None       # seconds; None = the ClipOptions default
    max_len: float | None = None
    hashtags: list[str] = []           # without "#"
    # no cadence: PostingSchedule.slots is the only timing source until S2

class PostingSchedule(Contract):
    chat_id: int | None = None         # None = posting off for this account
    timezone: str = "America/New_York" # validated with ZoneInfo
    slots: list[str] = []              # "HH:MM", normalized like POSTING_SLOTS today
    hashtags: list[str] = []           # account-wide, added to every platform's copy

class BrandKit(Contract):
    caption_preset: str = "default"
    cta: str | None = None
    bio_link: str | None = None

class Account(Contract):
    id: str                            # slug, [a-z0-9][a-z0-9-]{0,39}; stable, never a handle
    blueprint: str
    blueprint_version: int
    kind: Literal["clips", "story", "band", "avatar", "model"]   # = blueprint.category; model = ADR-39
    language: Literal["en", "es"]
    niche: str
    platforms: dict[Platform, PlatformProfile]
    review_tier: Literal["review", "sample", "auto"] = "review"
    persona_id: str | None = None
    paired_account_id: str | None = None
    monthly_budget_usd: float = 0.0
    brand: BrandKit = BrandKit()
    posting: PostingSchedule = PostingSchedule()
    # no `paused`: that is runtime state in posting_state (§3), so editing an
    # account can never pause or un-pause its queue

class SeriesFormat(Contract):
    name: str
    description: str

class ComplianceProfile(Contract):
    require_credit: bool = False
    required_tags: list[str] = []
    disclosures: list[Literal["ai", "sponsored"]] = []
    banned_claims: list[str] = []      # categories, e.g. "buy-x", "health", "finance-advice"

class Blueprint(Contract):
    name: str
    version: int
    category: Literal["clips", "story", "band", "avatar", "model"]
    languages: list[Literal["en", "es"]]
    niche: str
    pillars: list[str]
    series: list[SeriesFormat] = []
    voice_brief: str = ""
    visual_style: str = ""
    money: list[str] = []
    compliance: ComplianceProfile = ComplianceProfile()
    platform_defaults: dict[Platform, PlatformProfile]
    prompts: dict[str, str] = {}       # step -> prompt name, e.g. highlights = "highlights_v1"

class Persona(Contract):               # contract only; the table arrives in S8
    id: str
    voice_ref_path: str | None = None
    voice_design_prompt: str = ""
    face_lora_path: str | None = None
    face_ref_paths: list[str] = []
    style_notes: str = ""

class AssetSource(Contract):
    kind: Literal["source_video", "generated", "stock", "commons", "promo", "music_generated"]
    license: str                       # for source_video: the Permission value
    attribution: str | None = None
    url: str | None = None
    model: str | None = None

class SourcePermission(Contract):
    """The legal basis for posting a source's content (a business record, not config)."""
    type: Permission                   # own | creator_agreement | clipping_program | cc_by | public_domain
    granted_at: date | None = None
    granted_by: str | None = None      # who granted it (name and role)
    evidence_url: AnyHttpUrl | None = None   # link to the stored agreement; never the file itself
    platforms: list[Platform] = Field(default_factory=lambda: list(Platform))  # platforms covered
    monetization_allowed: bool | None = None  # None = not recorded yet
    translation_allowed: bool | None = None
    expires_at: datetime | None = None # None = no expiry
    restrictions: str = ""             # e.g. "no clips about X"

class CampaignRules(Contract):
    url: AnyHttpUrl | None = None      # the campaign page
    rules: str = ""
    required_tags: list[str] = []      # without "#"
    required_links: list[AnyHttpUrl] = []
    deadline: datetime | None = None
    sponsored: bool = True             # paid campaigns are disclosed (#ad)
    rate_per_1k: float | None = None   # USD per 1,000 views
    submission_url: AnyHttpUrl | None = None  # where posted links are submitted

class Source(Contract):
    id: str                            # = the folder name under videos/; a slug, never changes
    account_id: str                    # one account per source for now
    kind: Literal["channel", "campaign", "own"] = "channel"
    status: Literal["active", "paused", "ended"] = "active"
    credit_name: str                   # the credit text in captions, e.g. "Billy Garton Jr."
    creator_handles: dict[Platform, str] = {}   # for @mentions (used from S2's copy)
    url: AnyHttpUrl | None = None      # the creator's page
    permission: SourcePermission
    campaign: CampaignRules | None = None   # required iff kind == "campaign"
    notes: str = ""
    # validators: campaign iff kind == "campaign"; kind == "own" iff permission.type == own

class SourceEvent(Contract):
    """One change to a source (source_events): who, when, before and after."""
    source_id: str
    at: datetime
    actor: str                         # "cli:<os user>", "import-toml", later the dashboard user
    action: Literal["created", "updated", "imported"]
    before: dict[str, object] | None   # the Source JSON before (None when created)
    after: dict[str, object]

class ClipOrigin(Contract):
    job_id: str
    clip_id: str
    source_hash: str
    start: float
    end: float
    episode: str
    episode_finished_at: datetime

class ContentItem(Contract):
    id: str                            # "<job_id>:<clip_id>" for clips (keeps Telegram buttons valid)
    account_id: str
    source_id: str | None
    producer: str = "clips"
    producer_version: str
    language: str
    media_kind: Literal["video", "carousel", "image"] = "video"
    video_path: str | None             # relative to JOBS_ROOT
    image_paths: list[str] = []
    duration: float | None
    title: str
    hook: str
    score: float
    credits: list[str]
    assets: list[AssetSource]
    ai_disclosure: bool = False
    sponsored: bool = False
    cost_usd: float = 0.0
    parent_item_id: str | None = None
    clip: ClipOrigin | None = None
    queued_at: datetime
    # `copy: dict[Platform, PostCopy]` arrives in S2
```

- **`PostItem` is removed** (ADR-25). `PostRecord.item` becomes a `ContentItem`, and `PostRecord` otherwise keeps its shape: sends, posted per platform, verdict, unavailable.
- **`queue.py` changes only field paths, plus one generalization.** "Same video" reads `item.clip.source_hash` (or `item.id` for non-clip items). "Same channel" reads `item.source_id`. Priority and freshness read `item.score` and `item.clip.episode_finished_at`.
- **The generalization:** `PostRecord` gains `platforms: list[Platform]`, the platforms the item is due on (its `posts` rows). "Posted everywhere" becomes `set(posted) ⊇ set(platforms)` instead of `len(posted) == len(Platform)`, so adding `facebook` to `Platform` (§6.1) can't stop existing clips from reaching `POSTED`.
  - Imported and Dict items get `platforms = [tiktok, instagram, youtube]`, which gives exactly today's result.
  - Any other rule change would need its own ADR.
- **Account comes from the source.** `ChannelRef` stays on `JobInput` unchanged: a job's account comes from its source (`sources.account_id`), so no second `account_id` can disagree with it. The item copies `account_id` when it is queued, so moving a source to another account later doesn't move clips already queued.
- **`PostingOverview`** keeps its current fields (filled with account #1's numbers) and gains `accounts: list[AccountPosting]`, each with `account_id`, `channels`, `waiting`, `days_left`, `per_day`, `next_slot`, `paused` and `held` (clips waiting but held by their source: paused or ended, permission expired or no longer covering the item's platforms, or a campaign past its deadline). The S3a dashboard client keeps working.
- **API contract rule (from S3a):** the dashboard parses `GET /posting` (`PostingOverview`, including `ChannelProgress`) and `GET /jobs/{id}` (`JobView`) with zod schemas generated from today's API. So both responses stay **additive**: fields can be added, but never renamed, removed or retyped.
  - A pinning test fixes today's field names and types for `PostingOverview`, `ChannelProgress` and `JobView` (their JSON schemas as of 2026-09-29), and fails on any rename, removal or type change.
  - If a change can't be additive, stop and tell the owner, and in the same checkpoint run `uv run python scripts/export_openapi.py` so `web/openapi.json` matches. This session runs the script, but never edits it.
- **`STATE_READS`** (`Settings.state_reads: Literal["dict", "postgres"] = "dict"`) and **`Settings.database_url: SecretStr | None`**.
- **`POSTING_*` settings** are read only in `STATE_READS=dict` mode, and once to seed account #1 (`--posting-from-env`). In `postgres` mode, schedules come only from `accounts.posting`. So a rollback to `dict` still has a schedule.

## 3. Data (Postgres on Neon)

SQLAlchemy Core `Table`s in `db/tables.py`, created by Alembic migration `0001_initial`. Timestamps are `timestamptz`. jsonb holds validated contract parts.

| Table | Key | Columns | Writer(s) |
|---|---|---|---|
| `accounts` | `id` | blueprint, blueprint_version, kind, language, niche, review_tier, persona_id (text, no FK until S8), paired_account_id → accounts, monthly_budget_usd, platforms jsonb, brand jsonb, posting jsonb, created_at, updated_at | account create/edit |
| `posting_state` | `account_id` → accounts | paused bool, changed_at | `/pause`, `/go` only |
| `sources` | `id` | account_id → accounts, kind, status, credit_name, creator_handles jsonb, url, permission jsonb, campaign jsonb, notes, created_at, updated_at | `source add` / `source edit` / `source import-toml` (through the API), each with a `source_events` row in the same transaction |
| `source_events` | `id` (identity) | source_id → sources, at, actor, action, before jsonb, after jsonb | the same writers; append-only |
| `jobs` | `job_id` | source_id → sources (null for non-channel jobs), status, source_label, input jsonb, created_at, updated_at, finished_at, cost_usd, metadata_path | job create, `package_step`, failure path, sweeper; backfill |
| `content_items` | `id` | account_id, source_id, job_id → jobs, producer, producer_version, language, media_kind, video_path, image_paths jsonb, duration, title, hook, score, credits jsonb, ai_disclosure, sponsored, cost_usd, parent_item_id → content_items, clip_id, source_hash, start_s, end_s, episode, episode_finished_at, queued_at, unavailable_at, verdict_kind, verdict_at, verdict_reason | enqueue (row); sender (`unavailable_at`); webhook (`verdict_*`) |
| `assets` | `id` (identity) | item_id → content_items, kind, license, attribution, url, model | enqueue |
| `posts` | (`item_id`, `platform`) | posted_at (null = not posted), external_id, url | enqueue (one row per enabled platform); ✅ toggles `posted_at` |
| `sends` | (`item_id`, `n`) | at, slot, chat_id, message_id, video_message_id | sender (`INSERT … ON CONFLICT DO NOTHING`) |
| `post_events` | `id` (identity) | item_id, platform, kind (`sent`, `posted`, `unposted`, `skipped`, `rejected`, `reason`, `unavailable`), at, data jsonb | append-only, by the same writers |
| `costs` | `id` (identity) | job_id → jobs, stage, clip_id, wall_s, gpu_s, gpu_type, llm_model, llm_input_tokens, llm_output_tokens, llm_calls, usd, cached | `package_step`; backfill |

**Indexes:**
- `content_items (account_id)`
- `content_items (source_hash)`
- `jobs (source_id, status)`
- `costs (job_id)`

**Rules:**
- **One writer per column group** (ADR-14 carried over). Each `UPDATE` sets only its own columns, so the sender and the webhook never overwrite each other. A set-if-absent claim becomes `INSERT … ON CONFLICT DO NOTHING` (returning whether a row was inserted).
- **The status is still derived, never stored:** the repository rebuilds `PostRecord`s from rows, and `queue.status()` decides.
- **Slot and reminder claims stay on the Dict** (ADR-26: claims stay hot). They are now keyed per account: `posting:slot:<account>:<iso>` and `posting:reminded:<account>:<iso>`.
- **Invalid jsonb** or a row that fails validation is logged and skipped, as `_build` does today.

**Migrations:**
- `alembic/` and `alembic.ini` at the repo root. `env.py` uses `DATABASE_URL_UNPOOLED` when it is set (Neon recommends the direct connection for DDL), otherwise `DATABASE_URL`. `target_metadata` is `db.tables.metadata`.
- Commands: `uv run alembic upgrade head` locally. In CI, the deploy job runs it before `modal deploy` (§8).

## 4. The `db/` package and the Modal layer

`src/clipforge/db/` is Modal-free and never imported by `stages/`:
- **`engine.py`:** `make_engine(url)` returns an engine with:
  - psycopg 3 (`postgresql+psycopg://`);
  - `pool_size=2`, `max_overflow=2`, `pool_pre_ping=True`;
  - `connect_args={"prepare_threshold": None, "connect_timeout": 10}`, because Neon's PgBouncer runs in transaction mode and scale-to-zero wake-up takes about 0.5–1 s.
  - One engine per container, created lazily. The URL never appears in a `repr`, log line or error message: `redact(exc)` maps driver errors to a short class name plus message, with the host and credentials removed.
- **`tables.py`:** the metadata above.
- **Repositories**, each taking and returning contracts:
  - `accounts.py`: accounts plus `posting_state`;
  - `sources.py`;
  - `jobs.py`: job summaries plus backfill;
  - `costs.py`;
  - `posting.py`: `SqlPostingRepo`.

**Modal layer:**
- `app.py` stays the only Modal importer.
- `runtime.build_deps` adds `db: Database | None` to `Deps`, built from `Settings.database_url`.
- Functions that use it: `web`, `package_step`, `posting_tick`, `posting_keepalive` and `sweeper`. The other steps, including the GPU `transcribe_step`, never open a connection.
- No new Modal function and no new cron (the Starter plan allows 5 crons).
- `posting_tick`'s timeout covers one upload per account (§5.2).
- If `DATABASE_URL` is missing while `STATE_READS=postgres`, the posting and account routes answer 503 with that reason (the same pattern as a missing secret today), and the tick logs "database not configured".

## 5. Posting flow

### 5.1 Repositories and the double write (approach A)

```python
class PostingRepo(Protocol):
    def add(self, item: ContentItem, platforms: list[Platform]) -> bool: ...
    def get(self, ref: str) -> PostRecord | None: ...
    def records(self, account_id: str) -> list[PostRecord]: ...
    def records_for_source(self, source_hash: str) -> list[PostRecord]: ...
    def add_send(self, ref: str, send: PostSend) -> bool: ...
    def mark_unavailable(self, ref: str) -> None: ...
    def toggle_posted(self, ref: str, platform: Platform, at: datetime) -> bool: ...
    def set_verdict(self, ref: str, verdict: PostVerdict) -> None: ...
    def set_reason(self, ref: str, reason: RejectReason) -> bool: ...
    def paused(self, account_id: str) -> bool: ...
    def set_paused(self, account_id: str, on: bool) -> None: ...
```

- **`SqlPostingRepo`:** the rows in §3. `get(ref)` is three indexed queries (the item, its posts, its sends); it never scans. Each write also appends a `post_events` row in the same transaction.
- **`DictPostingRepo`:** today's `PostingStore`, adapted to the protocol. It serves only account #1:
  - `records(other)` returns `[]`;
  - `paused` uses `posting:paused`;
  - it stores `ContentItem`s by mapping them to and from the old `PostItem` JSON, so plan C's keys stay readable.
- **`DualPostingRepo(primary, mirror)`:**
  - The primary is the store `STATE_READS` names, and all reads go to it.
  - Writes go to the primary first; if the primary fails, the call raises. The mirror is written after, and a mirror failure is logged and counted.
  - When the primary refuses a set-if-absent write (a duplicate `add` or `add_send`), the mirror isn't written.
  - The Dict side accepts only account #1's items.
  - Flipping `STATE_READS` swaps the roles.
- **`PostingClaims`** (Dict): `claim_slot(account, slot)`, `release_slot(account, slot)`, `claim_reminder(account, at)`.

### 5.2 The tick (`posting_tick`, still one cron every 5 min)

For each account with `posting.chat_id` set, in id order:
1. Skip it if paused (`posting_state`).
2. Find `current_slot(account.posting, now)`. `slots.py` takes a `PostingSchedule` instead of `Settings`.
3. Load `records(account)`, leaving out **held** items: their source is paused or ended, its permission has expired or no longer covers every platform the item is due on, or its campaign's deadline has passed (`sources.source_problem` and `sources.uncovered`, §6.3). Held items stay queued and come back if the source is fixed.
4. Apply the pause-after-2-unanswered rule per account (one reminder per oldest unanswered send).
5. Claim the slot, then `pick_next` → deliver. On `SendFailed` or a DB error, release this account's slot and continue with the next account.

- Accounts are served one after another. If the function times out partway through, the accounts not yet served are picked up by the next tick, still inside the 30-minute slot window.
- The timeout becomes `UPLOAD_TIMEOUT_S × number of accounts with posting on`, capped at 900 s.
- The video caption starts with the account id, so clips from accounts that share one chat can be told apart.

### 5.3 Taps and commands

- **Button data is unchanged** (`p:tt:<job>:<clip>`, …). The account comes from the item. A tap counts only from that account's `posting.chat_id`.
- **Deferred fix 1:** a tap reads only its own clip (`get(ref)`).
- **Deferred fix 2:** after any state change, the buttons are redrawn on the text message of *every* send of the clip (`sends.message_id`), not only the tapped one. Each failed edit is logged on its own.
- **A stale button** (not in the current keyboard) still changes nothing and redraws.
- **`/next [account]`, `/pause [account]` and `/go [account]`:** without an argument they apply to every account with posting on (`/next` sends one clip per account). An unknown account gets the list of known ids.
- **`/status`** shows one block per account.

### 5.4 Enqueue and rebuild

- **`package_step`** (still before saving `DONE`, still never failing the job):
  1. upsert the `jobs` row and its `costs` rows;
  2. look up the source (`job.input.channel.slug`) and its account;
  3. **gate on the source** (`sources.source_problem(source, now)`): if it isn't `active` or its permission has expired, queue nothing and log why (the job is still `done`; `rebuild` queues it once the source is fixed);
  4. the item's platforms are the account's enabled platforms **that the permission covers**. Uncovered ones are logged; if none is left, queue nothing and log why;
  5. build `ContentItem`s with:
     - `credits = [source.credit_name]`;
     - `assets = [AssetSource(kind="source_video", license=source.permission.type, attribution=source.credit_name, url=source.url)]`;
     - `sponsored = source.campaign.sponsored` for campaigns;
     - `producer_version` = the git SHA;
  6. add each item with one `posts` row per platform from step 4, unless `overlaps(item, records_for_source(source_hash))`.
  - If the source row is missing: log a warning, skip, and leave it for `rebuild`.
- **`rebuild`** reads `DONE` jobs from `jobs` that have a `source_id`, and their clips from each job's `metadata.json` (`PackagedClip` has start, end, score, title, hook and video). So it no longer depends on `job:*` or clip Dict keys that can expire. A job whose files are gone is skipped, as today.
- **`posting_overview`** reads `jobs` and `records(account)` per account.

### 5.5 Import, backfill, verify

All three run on Modal (only Modal can read the Dict and the Volume), behind bearer-token routes, and are called from the CLI:
- **`clipforge posting import [--dry-run]`** → `POST /posting/import`:
  1. read every `post:*` key;
  2. fill in any key missing from the Dict from the newest readable keep-alive snapshot, in memory only (the Dict is never written);
  3. group them with the existing `_build`;
  4. map each `PostItem` to a `ContentItem`, with the account taken from its source;
  5. insert items, posts (one row each for TikTok, Instagram and YouTube, the platforms plan C posted to), sends, verdicts and `unavailable_at` with `ON CONFLICT DO NOTHING`;
  6. make `posting:paused` account #1's `posting_state`.
  - The report gives counts by status on each side, the refs whose source has no row, and the refs that failed.
  - A dry run writes nothing, and a re-run inserts nothing new.
- **`clipforge jobs backfill [--dry-run]`** → `POST /jobs/backfill`:
  - Each `/jobs/*/output/metadata.json` becomes a `jobs` row (`DONE`) plus its `costs` rows.
  - The `job:*` Dict keys fill in jobs that have no `metadata.json` (queued, running or failed).
  - Existing rows are updated only when the source is newer (`updated_at`).
- **`clipforge posting verify`** → `GET /posting/verify`:
  - Compares the Dict and Postgres for account #1, per clip: presence, status, number of sends, posted platforms, and verdict kind/reason.
  - Returns the counts and the first 50 differences.
  - `posting_keepalive` runs it daily and logs a summary line, with each difference at `WARNING`.

## 6. Accounts, blueprints and sources

### 6.1 Blueprints

- **Files:** `blueprints/<name>.toml` are loaded by `accounts/blueprints.py` (`load_blueprint(name)`, `list_blueprints()`) into `Blueprint`. They are packaged with the app like `prompts/`.
- **Versioning:** each file has a `version`, bumped on any meaningful change so the diff is reviewable. An account records the version it was created from. S1 always loads the current file.
- **The three files** come from 07, section A, all `category = "clips"`. All three enable **all four platforms** (TikTok, Instagram, YouTube, Facebook), per 01's rule "post every video to every platform an account has enabled" (owner decision 2026-09-29, 09 §4 A1, 10 #52). The primary platform stays as in 09 (TikTok for all three). It only shapes the format, so it's a comment in each file, not a field:
  - `realtalk-clips` (`languages = ["en"]`):
    - pillars: discipline, dating, money mindset, faith;
    - primary TikTok;
    - money: creator deal, CRP, Skool affiliate;
    - compliance: `require_credit = true`.
  - `founder-tapes` (`["en"]`):
    - pillars: origin stories, sales tactics, hiring, money lessons;
    - primary TikTok;
    - money: Whop business and finance campaigns, CRP;
    - compliance: `require_credit`, `banned_claims = ["buy-x"]`.
  - `hombre-en-construccion` (`["es"]`):
    - pillars: disciplina, relaciones, dinero, fe;
    - primary TikTok;
    - money: CRP (US and MX), Spanish-language host retainers;
    - compliance: `require_credit`.
  - Series formats: two or three per file, taken from the pillars. The 07 text lists none for clips, so each is marked `# draft: owner edits` in the file, and the owner rewrites them later.
- **Facebook:** `Platform` gains `facebook`.
  - Account #1 (realtalk) enables it too. Its clips queued before S1, and those queued in `STATE_READS=dict` mode, keep TikTok, Instagram and YouTube. Clips queued after the switch get a Facebook button.
  - The ✅ buttons and copy blocks follow the item's `platforms`, not a fixed list of three. Callback action `fb` joins `tt`/`ig`/`yt`.
  - Until S2's per-platform copy, the Facebook block reuses the TikTok caption.
- **Test:** every file loads, each `prompts` value names an existing `prompts/<name>.md`, and each `platform_defaults` key is a `Platform`.

### 6.2 Accounts

- **`clipforge account create --blueprint <b> --lang <l> --handle <h> [--id <slug>] [--posting-from-env]`** → `POST /accounts`:
  - `--id` defaults to `<blueprint>-<lang>`, e.g. `realtalk-clips-en`.
  - `--lang` must be one of the blueprint's `languages`.
  - `--handle` sets the same handle on every platform the blueprint enables.
  - `review_tier = "review"`.
  - `--posting-from-env` copies the server's `POSTING_*` settings into `posting` (used once, for account #1). Other accounts start with `posting.chat_id = None` (off).
  - A `posting_state` row (not paused) is created in the same transaction.
- **`clipforge account edit <id> [--handle <platform>=<h> …] [--chat <id>] [--slots 9:00,12:00] [--timezone <tz>] [--hashtags a,b] [--review-tier …]`** → `PATCH /accounts/{id}`:
  - The input is validated like the `POSTING_*` settings are today (`8:00` becomes `08:00`, `#tag` becomes `tag`). An invalid value is a 400 with the reason.
  - A rename is one update, with no data migration.
- **`clipforge account list`** → `GET /accounts`, plus **`GET /accounts/{id}`**.
- The service functions live in `accounts/service.py`, so the S3 `admin` endpoint can call the same functions later (ADR-38).
- **The three accounts:**
  - `realtalk-clips-en` (handle `realtalk.clipsdaily`, `--posting-from-env`, account #1);
  - `founder-tapes-en` (`founder.tapes`);
  - `hombre-en-construccion-es` (`hombre.en.construccion`).
  - All handles are placeholders for now.

### 6.3 Sources (option B: the database is the only copy)

- **Where sources live:** the `sources` table, from S1 on. Sources are edited only through the API: the CLI now, and the S3 Sources page later, calling the same routes. `channels.toml` stops being an editing surface.
  - Why: the file sits in `videos/`, which `.gitignore` excludes, so permission records had no backup and no history. Keeping the file and the database in sync would mean two sources of truth, and a sync S3 would have to delete again.
- **The folder name is the source id.** `videos/<source-id>/` holds that source's videos, and that mapping is the only local configuration left.
- **Routes** (bearer token; an `X-Clipforge-Actor` header names who made the change, default `api`; the CLI sends `cli:<os user>`):
  - `POST /sources` creates a source: 201. It answers 409 if the id exists and 400 for an unknown account or an invalid record.
  - `PUT /sources/{id}` replaces an existing source (edit): 404 if missing, 400 if the body's id differs.
  - `GET /sources` (list), `GET /sources/{id}` (one), `GET /sources/{id}/events` (history, newest first), `GET /sources/{id}/submissions`.
  - Every create or replace writes one `source_events` row in the same transaction: actor, time, action, and the record before and after. There is no delete: a source ends with `status = "ended"`.
- **CLI:**
  - **`clipforge source add <id> --account <a> --credit "<name>" --permission <type>`**, with optional flags:
    - `--kind channel|campaign|own`, `--url`;
    - `--handle <platform>=<h>` (repeatable);
    - `--granted-at YYYY-MM-DD`, `--granted-by`, `--evidence-url`;
    - `--platforms tiktok,instagram,...` (default: all four);
    - `--monetization yes|no`, `--translation yes|no`;
    - `--expires YYYY-MM-DD`, `--restrictions`, `--notes`;
    - campaign flags: `--rules`, `--tag` (repeatable), `--link` (repeatable), `--deadline`, `--rate-per-1k`, `--submission-url`, `--not-sponsored`.
  - **`clipforge source edit <id>`**: the same flags, all optional, plus `--status active|paused|ended` and `--no-expiry`. It reads the source, applies the changes, and `PUT`s it back.
  - **`clipforge source list`**: id, account, kind, status, permission type, expiry. It warns (`⚠ expires in N days`) when a permission expires within 14 days, and flags expired ones.
  - **`clipforge source show <id>`**: the full record, any permission fields not recorded yet (`granted_at`, `evidence_url`, monetization, translation), and the event history.
  - **`clipforge source submissions <id>`**: a campaign's posted clips.
  - **`clipforge source import-toml [--folder videos] [--account <id>] [--dry-run]`**: the one-off import.
    - Each `[slug]` entry becomes a source: `name` becomes `credit_name`; `url` and `permission` become `permission.type`, with `platforms` set to all four and the other permission fields not recorded.
    - The account comes from the entry's `account` key or from `--account`; a source with neither is reported and skipped.
    - Existing ids are skipped, never overwritten. The action is `imported` and the actor `import-toml`.
    - The report lists created, skipped and failed sources, plus each source's missing permission fields, to fill with `source edit`.
- **`clipforge clip`** no longer reads `channels.toml`:
  - it loads the sources through `GET /sources`;
  - a video in `videos/<id>/` belongs to source `<id>`, and its `JobInput` gets `channel = ChannelRef(slug=id, name=credit_name)`, `source_credit = credit_name` and `permission = permission.type`;
  - **a folder with no source** stops the command before any upload, with the fix:

    ```
    videos/billy-garton/: no source "billy-garton".
    Add it with:
        clipforge source add billy-garton --account <account> --credit "<credit name>" --permission <type>
    or, once, import videos/channels.toml with: clipforge source import-toml --account <account>
    ```
  - **a source that isn't active or whose permission has expired**: its new videos are skipped with a warning naming the reason (nothing is uploaded for it). The other folders continue.
  - **`videos/channels.toml` still present**: one warning, `videos/channels.toml is no longer read; sources live in the database (clipforge source list). Delete it after checking the import.`
  - an unreachable API stops the command before any upload.
- **Hold rules** (`clipforge/sources.py`, pure, also used by the S2 gate):
  - `source_problem(source, now) -> str | None` returns:
    - `"source paused"` or `"source ended"` when the status isn't active;
    - `"permission expired <date>"` after `permission.expires_at`;
    - `"campaign ended <date>"` after a campaign's `deadline`.
  - `uncovered(source, platforms) -> list[Platform]` gives the platforms the permission doesn't cover.
  - Enqueue (§5.4) and the tick (§5.2) both use these. A held clip is never sent, and `/status` counts it under `held`.
- **Campaign sources** (e.g. Whop Content Rewards) use `kind = "campaign"`, `permission.type = clipping_program` and the `CampaignRules` fields. What S1 does with them:
  - their items get `sponsored` set;
  - at send time the captions add `required_tags`, `required_links`, and `#ad` when sponsored;
  - after `deadline` their items are held (above);
  - `rate_per_1k` and `submission_url` are stored for S7's money page and for submitting links.
  - Posted URLs are captured in S2 or S3.
- **One account per source for now.** Sharing a source across accounts waits for a real case.
- **Creator handles** are stored now; captions start using them for @mentions with S2's per-platform copy.

## 7. Error paths (ADR-15 style)

| Where | On a database error |
|---|---|
| `package_step` (jobs/costs rows, enqueue) | Logged, never fails the job. `metadata.json` stays the durable record; `jobs backfill` and `posting rebuild` repair it (both idempotent). |
| Job create (API) | The job is created in the Dict as today, and the `jobs` row is best-effort (backfill repairs it). |
| `posting_tick` | That account's slot claim is released and the error logged. The other accounts continue, and the next tick retries within the window. |
| Tap (primary write fails) | Answered "Couldn't save, tap again", with nothing half-written (one transaction). The Telegram `update_id` claim means the user must tap again. |
| Tap (mirror write fails) | Logged and counted. `verify` shows the difference. |
| API routes | 503 `database unavailable`, sanitized (no URL, host or role). |
| import / backfill / rebuild | Per row: log, count, continue. The report lists the failures. |
| Invalid stored row or jsonb | Logged and skipped. |

## 8. Cost, security, CI

- **Cost:** no new stage, GPU or LLM call (rule 7 has nothing new to log).
  - Neon's free plan covers S1.
  - Query latency, including the scale-to-zero wake-up, is measured and recorded in docs/studio/03.
  - Modal spend this session is test deploys plus import and verify runs, under the card's **$3** limit. Every deploy waits for the owner's OK.
- **Security:**
  - `database_url` is a `SecretStr`, and the engine never logs its URL. Driver errors are redacted before they reach logs or responses.
  - Queries use bound parameters only.
  - Every new route requires the bearer token.
  - Account and source ids match the slug regex, handles match `[A-Za-z0-9._]{1,30}`, and job ids pass `is_job_id`.
  - One Neon role for now. A least-privilege app role is noted for S3.
  - `.env` and `.neon` are git-ignored.
- **CI** (`.github/workflows/ci.yml`):
  - The check job gets a `postgres:17` service container and sets `TEST_DATABASE_URL`.
  - The deploy job runs `uv run alembic upgrade head` with the GitHub secret `DATABASE_URL_UNPOOLED` before `modal deploy`.

## 9. Tests, rollout, rollback

### 9.1 Tests

- **Database fixture:**
  - When `TEST_DATABASE_URL` is set (CI), the tests use it. Otherwise they start a `postgres:17` container with testcontainers (Docker Desktop's WSL integration).
  - The schema is migrated once per session, and tables are truncated between tests.
  - With neither available, the DB tests **fail** with "start Docker Desktop (WSL integration) or set TEST_DATABASE_URL". They never skip silently.
  - They are part of the fast suite. CLAUDE.md will say that the fast tests now need Docker, which matters for the S0 and S3a sessions too.
- **Queue rules kept:**
  - `tests/posting/test_queue.py` runs unchanged, apart from the new field paths.
  - One shared `PostingRepo` test suite runs against `DictPostingRepo`, `SqlPostingRepo` and `DualPostingRepo`, both ways round.
  - The `bot/posting` tests are parametrized over the Dict and Sql repos.
  - A clip queued on TikTok, Instagram and YouTube with all three marked still reads `POSTED` after its account enables `facebook`.
- **API contract pin:** `PostingOverview`, `ChannelProgress` and `JobView` keep today's field names and types (§2).
- **The `clipforge clip` error** for a folder with no source names the folder and the exact `clipforge source add` / `source import-toml` commands.
- **Migrations:** upgrade → downgrade → upgrade on an empty database, and the Alembic autogenerate diff against `tables.py` is empty.
- **Import, backfill, verify:**
  - Dict keys plus a snapshot fixture give the expected rows.
  - A re-run is a no-op, and a dry run writes nothing.
  - Backfill works from a sample `metadata.json`.
  - Verify reports a planted difference.
- **Multi-account:**
  - two accounts with their own chats and slots each send at their own slot;
  - a pause of one doesn't affect the other;
  - a tap from the wrong chat changes nothing.
- **Tap fixes:**
  - the Sql `get()` runs only id-filtered queries (checked with a statement spy). The Dict repo keeps plan C's filtered scan until it retires (§9.3);
  - a tap redraws the buttons of every send's message.
- **Blueprints, accounts, sources:**
  - all three files load;
  - `account create` with an unknown language fails;
  - edits normalize slots and hashtags;
  - a campaign's tags, links and `#ad` show up in captions;
  - **sources:** create and edit each write a `source_events` row with before and after; a duplicate id is 409; an unknown account is 400;
  - **hold rules:** a paused or ended source, an expired permission, a campaign past its deadline, and a permission that no longer covers a platform the item is due on each hold the item at the tick (not sent, counted as `held`); at enqueue, an expired or inactive source queues nothing, and an uncovered platform gets no `posts` row (with every platform uncovered, nothing is queued);
  - **`clipforge clip`:** a folder with no source stops before any upload with the exact fix; an inactive or expired source's videos are skipped; a leftover `channels.toml` gives the "no longer read" warning;
  - **`source import-toml`:** a dry run writes nothing; a re-run skips existing ids; missing permission fields are reported.
- **The DB layer** has no Modal import (the existing import-boundary test covers it).

### 9.2 Rollout

Rollout starts after S0's deploy, and every deploy waits for the owner's OK.
1. **Owner:**
   - turn on Docker Desktop's WSL integration;
   - add the GitHub secret `DATABASE_URL_UNPOOLED`;
   - put `STATE_READS=dict` in `clipforge-secrets` (the default, written down so it's visible).
2. `uv run alembic upgrade head` against Neon.
3. Deploy. The Dict is the primary and Postgres the mirror.
4. `clipforge account create` × 3 (account #1 with `--posting-from-env`).
5. `clipforge source import-toml --account realtalk-clips-en --dry-run`, then without `--dry-run`. `clipforge source show billy-garton`, then fill the permission record with `clipforge source edit billy-garton --granted-at … --granted-by … --evidence-url … --monetization yes|no --translation yes|no` (the owner has these facts). Then delete `videos/channels.toml`.
6. `clipforge posting import --dry-run`, check the counts, then run the real import. Then `clipforge jobs backfill`.
7. `clipforge posting verify` must report 0 differences.
8. Set `STATE_READS=postgres` in the secret and redeploy (new containers read it). Watch a day of real slots and taps. The daily verify keeps running.
9. **Final checkpoint, after ≥ 7 days with a clean verify every day** (§9.3).

### 9.3 Retiring ADR-24 (final checkpoint, a later session)

- Remove the Dict mirror, `DictPostingRepo`, `DualPostingRepo`, `STATE_READS` and the `POSTING_*` settings.
- Remove `posting_keepalive` and its snapshots, `restore` (`POST /posting/restore`, `clipforge status --restore`), and `posting import` / `verify`.
- `job:*` keys stay in-flight state only.
- ADR-24 is marked "Superseded by ADR-26 (retired <date>)".

### 9.4 Rollback

- Set `STATE_READS=dict` and redeploy. The Dict has stayed current for account #1 through the double write, and the other accounts pause until the flag goes back.
- Rolling the code back to plan C (`modal app rollback`) also works, for the same reason.
- Postgres data is kept either way, and flipping back needs a `verify` first.

## 10. Layout and docs

```
src/clipforge/
  db/          engine.py tables.py accounts.py sources.py (with source_events) jobs.py costs.py posting.py
  sources.py   hold rules: source_problem, uncovered (pure)
  accounts/    blueprints.py service.py
  posting/     repo.py (protocol, DictPostingRepo, DualPostingRepo, PostingClaims), migrate.py (import, verify)
alembic/       env.py versions/0001_initial.py      alembic.ini
blueprints/    realtalk-clips.toml founder-tapes.toml hombre-en-construccion.toml
```

- **New dependencies:**
  - `sqlalchemy>=2` (MIT), `alembic` (MIT), and for dev `testcontainers[postgres]` (Apache-2.0): all on 03's allowlist.
  - `psycopg[binary]>=3.2` (LGPL-3.0): approved at spec review (2026-09-29). It is an unmodified library dependency, which LGPL allows, and 03's allowlist section now says so ("Libraries: LGPL used unmodified as a dependency is allowed").
- **Docs to update:**
  - docs/ARCHITECTURE.md (state, posting per account, `db/`, new commands);
  - CLAUDE.md (layout, commands, fast tests need Docker);
  - docs/DECISIONS.md: **ADR-41**, "S1 migration: double write with a read switch, per-account posting schedules, `posting_state` as runtime state". ADR-40 is already a draft in 05.
  - docs/studio/03 (Neon numbers);
  - docs/studio/04 and ROADMAP.md (ticks);
  - a note for the S3a session about `GET /posting`'s added `accounts` field.
