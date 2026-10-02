# Studio S2: publishing and autopilot (design)

Date: 2026-10-01 · Card: [011](../../cards/011-s2-design.md) · Status:
- §1–§9 approved by the owner section by section at checkpoint A (2026-10-01).
- Revised the same day after the coordinator's review ("approve with changes": 2 blocking, 9 should-fix, the minors, and 5 owner rulings, §0.1).
- Revised again after the coordinator's re-review (2026-10-02: the re-send window, the brake repair, the Dict markers, the retry check). **Approved by the coordinator with these changes in**; the plan follows (checkpoint B).
- Decision log #440–#459.

**What S2 is.** S2 is the step that replaces the owner's hand posting with publishing through Upload-Post, reviewed where it pays off. founder.tapes and hombre.en.construccion launch on it (ADR-48, #428). [04's S2 list](../../studio/04-roadmap.md) is the source. Every item in that list maps to a section here (§10).

**What it builds on, without reopening:**
- ADR-13: signed links.
- ADR-14: one writer per key.
- ADR-23: queue status rules.
- ADR-26 and ADR-41: Postgres as the store; Dual writes and `STATE_READS` for rollback.
- ADR-28: Upload-Post behind a `Publisher` protocol.
- ADR-29: review tiers and the gate.
- ADR-43: the derived `producer_version`.
- ADR-44 and ADR-45: one home per task; the notification budget.
- ADR-46: the daily reconcile.
- ADR-48 and ADR-49: autopilot; the producer-version window.
- The [S3 dashboard spec](2026-10-01-studio-s3-dashboard-design.md) §2, §4, §7.11, §8.1, §8.4, §8.6 and §8.7.
- 08 §2b and §2c.

**The code it starts from:** S1 as merged (`alembic/versions/0001`, `db/`, `posting/`, `bot/posting.py`, `ops.py`, `app.py`). Card 010's rollout is assumed finished before S2's build: production runs with `STATE_READS=postgres` and **Dual writes still on**. The Dict mirror retires only at S1 Task 23, and S2 keeps it current until then (§3.1).

**Upload-Post facts.** These were checked on 2026-10-01 in the official docs: [upload-video](https://docs.upload-post.com/api/upload-video), [schedule-posts](https://docs.upload-post.com/api/schedule-posts), [upload-status](https://docs.upload-post.com/api/upload-status), [upload-history](https://docs.upload-post.com/api/upload-history), [webhooks](https://docs.upload-post.com/api/webhooks), [user-profiles](https://docs.upload-post.com/api/user-profiles), [pricing-and-limits](https://docs.upload-post.com/resources/pricing-and-limits) and [rate-limits](https://docs.upload-post.com/guides/rate-limits). The ones the design depends on:
- **Upload:** `POST /api/upload` with `Authorization: Apikey <key>`. The `video` field may be a URL. Fields:
  - `user` (the profile) and `platform[]`;
  - per-platform titles and descriptions (`tiktok_title`, `instagram_title`, `youtube_title`/`youtube_description`, `facebook_title`/`facebook_description`);
  - `facebook_page_id`, required for Facebook;
  - the AI flags `is_aigc`, `is_ai_generated` (Instagram), `containsSyntheticMedia` and `facebook_is_ai_generated`;
  - `scheduled_date` with `timezone`, `async_upload`, `request_id`;
  - `Idempotency-Key` (a repeated key returns the existing job; **how long a key is kept is not documented**);
  - `disable_inbox_fallback`. Without it, TikTok can put the post in drafts and still report success.
- **Scheduled posts:** list with `GET /api/uploadposts/schedule?profile_username=`; cancel with `DELETE /api/uploadposts/schedule/<job_id>`.
- **Status:** `GET /api/uploadposts/status?request_id=|job_id=`, with an overall state (`not_found` among them) and per-platform states. History: `GET /api/uploadposts/history?request_id=|job_id=|external_id=`, with `platform_post_id`, `post_url` and `error_message`.
- **Webhooks:**
  - Events: `upload_completed` (one per platform, success or failure), `social_account_disconnected`, `social_account_reauth_required` and `social_account_connected`.
  - Signature: `X-Upload-Post-Signature: sha256=<hex>` over `"<X-Upload-Post-Timestamp>.<raw body>"`. Deliveries older than 5 minutes are rejected.
  - De-duplication: `X-Upload-Post-Delivery` is unique per delivery.
  - Payloads carry `job_id` but not `request_id`.
  - After 5 failed deliveries the channel pauses for 30 minutes, and deliveries skipped then are never retried.
  - **No strike or takedown event is documented.**
- **Profiles:** one profile = one account across platforms. Basic is $24/month for 5 profiles; Professional is $50 for 25. **Basic's API rate limit is not in the rate-limit table.**
- **Hard caps per connected account per 24 h:** TikTok 15, Instagram 50, YouTube 10, Facebook 25 (429 when exceeded).

## 0. Decisions

| # | Question | Answer (owner, 2026-10-01) |
|---|---|---|
| Q1 | O4, the Upload-Post plan | **Basic ($24, 5 profiles) now; upgrade to Professional when the 6th account is created** (S8). One profile per account, on all four platforms. Monthly until S2 proves out, then yearly |
| Q2 | Order inside S2 | **Rails first, then the publisher:** S2a (rails, assisted flow unchanged), S2b (Upload-Post for realtalk on Hands-on), S2c (the rest of autopilot, digest, links, the two launches). §1 |
| Q3 | The review lane before S3's Review page | **A morning batch, then 2 h cards:** at 09:00 one review card per undecided item in the plan's horizon; anything still undecided gets its card 2 h before its slot. A bridge behind `REVIEW_BATCH=on`, an exception to #427 that ends when S3's Review page ships. §7.1 |
| Q4 | The digest | **One message at 09:00, then the cards.** Anomalies first; lines with nothing to say are left out. §7.2 |
| Q5 | Accounts with Publish off | **Today's assisted flow, where sending is the review.** The gate still holds failing items. The fallback reuses the same card for the failed platforms only. §6.6 |
| Q6 | When an approved item goes to Upload-Post | **30 minutes before its slot,** with `scheduled_date = slot`. A late approval goes at once. §4, §6 |
| Q7 | Where publishing state lives | **Approach A: on the `posts` rows** (one per item × platform), with the claim as a conditional update. A separate `publications` table (B) and Dict state (C) were rejected. §3 |

### 0.1 Owner rulings at the coordinator's review (2026-10-01)

| # | Ruling | Here |
|---|---|---|
| R1 | The 09:00 review batch is exempt from ADR-45's 20-an-hour cap: it counts as one delivery, with paced sends (amends #442) | §7.1 |
| R2 | Assisted ✅ taps don't count toward the ladder or the producer-version window: a ✅ means "posted", not "reviewed". Counting starts at S2b | §5.2, §5.5 |
| R3 | Planning and the digest run in the owner's time zone for every account | §4.2, §7.2 |
| R4 | ADR-33 is accepted as tracking links only; conversion import becomes draft ADR-51 | §11.2, §11.3 |
| R5 | S2b's build is blocked until one real Upload-Post call confirms the idempotency-key retention and Basic's rate limit; the results go in the S2 build's report. Re-review (2026-10-02): a third check, that a scheduled async upload is visible by `request_id` within seconds; until R5 confirms keys are kept at least 10 minutes, crash recovery never re-sends (`RECOVERY_WINDOW_S=0`) | §1, §6.3, §9 |
| R6 | Re-review (2026-10-02): assisted-card taps (✅, ⏭ and 🗑) don't count toward the ladder, the spot checks or the producer window; only review-card decisions count, from S2b on (confirms the reading of R2) | §5.2, §5.5 |

## 1. Shape and build order

S2 ships as three steps. Each is deployable and usable on its own.

**S2a: rails.** Production behaves exactly as today, on the dispatcher.
- Migration 0002 (§3), including the deferred items of S3 §8.7.
- The dispatcher replaces `posting_tick` (§4) and takes over the ops-alert flush.
- The brake: Dict keys `brake:<scope>` (§6.7), through `posting/actions.py`.
- The autopilot service with every account on Hands-on (§5.4).
- The policy gate v1 (§5.1) and the routing and window computation (§5.2). They are computed but not used yet: with no connected profile, every account stays assisted (§1.1).
- The `clipforge autopilot` CLI and its admin API routes.

**S2b: publishing for realtalk.** **Its build starts only after ruling R5's real call** (§9).
- The `Publisher` protocol, `UploadPostPublisher` and `AssistedPublisher` (§6).
- Media links, the webhook and the publish reconcile.
- The slot plan, the review cards (the 09:00 batch and the 2 h cards), hand-off 30 minutes before the slot, the claim, crash recovery, and the fallback for failed platforms only.
- `clipforge publisher check`.
- **Exit:** realtalk publishes through Upload-Post on Hands-on, with every item approved by the owner in Telegram.

**S2c: autopilot and measurement.**
- The `sample` and `auto` dials, spot checks, the ladder (suggest, then the owner promotes) and automatic demotions (§5).
- The 09:00 digest (§7.2), the `publish_failed` and `publisher_disconnected` rows and alerts (§7.3), and tracking links (§7.4).
- founder.tapes and hombre are created (O3), each with one permitted source clipped, their profiles connected, and they start Hands-on.
- **Exit:** 04's S2 exit (§9).

### 1.1 What "Publish on" means before a profile is connected

ADR-48's presets all have Publish on, and controls never block each other: each says what it waits on.
- An account whose `accounts.publisher` is empty shows **"Publish: on, waiting for a connected profile"** and runs the assisted flow (§6.6).
- Connecting the profile is an explicit owner step (§9). That step turns publishing on for that account.
- Publish **off** is an override that keeps the assisted flow even when a profile is connected.
- Any change to the Publish switch or to `accounts.publisher` rewrites the account's `posting:schedule:<account>` copy (the accounts service, its one writer), because the dispatcher reads the publish path from that copy (§4.1).

### 1.2 New modules (all Modal-free; `app.py` stays the only Modal importer)

| Module | Holds | Writes |
|---|---|---|
| `publishing/protocol.py` | the `Publisher` protocol and helpers for its contracts | — |
| `publishing/upload_post.py` | `UploadPostPublisher` over httpx (no SDK, so one fake transport tests it) | — |
| `publishing/assisted.py` | `AssistedPublisher`: wraps today's `bot/posting.py` delivery for a platform subset | through `posting/` as today |
| `publishing/media.py` | signed per-item media links | — |
| `publishing/state.py` | **the one writer of the `posts` publish columns** and of both Dict publishing keys: every transition of §6.2 | `posts` (publish columns), `post_events`, `publishing:inflight:<ref>`, `publish:last_handoff` |
| `publishing/handoff.py` | the hand-off sequence (claim, publish, record, brake re-check) | through `state.py` |
| `publishing/webhook.py` | signature check, delivery idempotency, event handling | `webhook_deliveries`; posts through `state.py` |
| `publishing/reconcile.py` | crash recovery, retries, status and history polling, unmatched deliveries | through `state.py` |
| `review/routing.py` | pure routing: gate, sponsored, windows, dial, spot checks | — |
| `review/service.py` | approve, reject and copy edits, with an actor (the S3 routes call it too) | `content_items` review columns |
| `review/cards.py` | Telegram review cards and their callbacks (`r:` prefix) | `review_messages` |
| `policy/gate.py` | the pure gate | — |
| `accounts/autopilot.py` | presets and history | **`autopilot`, `autopilot_events`** |
| `accounts/ladder.py` | pure ladder criteria over counted stats | — |
| `dispatch/tasks.py` | the task registry and markers | `dispatch:*` claims |
| `dispatch/plan.py` | **the one writer of `slot_plans`**: planning, and the slot transitions that hand-off and review ask for | `slot_plans` |
| `dispatch/digest.py` | the digest | — |
| `tracking.py` | tracking links and click logging (`links.py` stays the zip-link module) | `links`, `clicks` |

`app.py` changes:
- the `dispatcher` cron replaces `posting_tick`;
- a spawned `dispatch_task(name, key)` function is added for slow tasks;
- `web` gains `POST /webhooks/upload-post`, `GET /media/{item_id}.mp4` and `GET /go/{slug}`, plus admin routes (bearer token) for autopilot, links and review: `GET /admin/review?account=`, `POST /admin/review/{item}/approve|reject`, `PUT /admin/review/{item}/copy`. With those routes, S3 only adds the pages.

## 2. Contracts (`models.py`, rule 2)

```python
class PostCopy(Contract):
    title: str | None = None          # YouTube/Facebook titles; None elsewhere
    text: str                         # caption or description
    hashtags: list[str] = []          # without "#"
    links: list[str] = []

# ContentItem gains:
    copy: dict[Platform, PostCopy] | None = None   # None: built by posting/captions.py; S3 edits write it

ReviewDial = Literal["review", "sample", "auto"]
Preset = Literal["hands_on", "supervised", "autopilot", "custom"]   # custom: a control overridden

class Autopilot(Contract):
    account_id: str
    preset: Preset = "hands_on"
    produce: bool = False
    review_dial: ReviewDial = "review"
    publish: bool = True
    scale: bool = False
    runway_days: int = 7
    batch_line_usd: float = 2.0
    monthly_cap_usd: float                # seeded from accounts.monthly_budget_usd, else the type default (S3 §2.6)
    updated_by: str
    updated_at: datetime

def hands_on(account: Account) -> Autopilot: ...   # what a missing row reads as (§5.4)

class AutopilotEvent(Contract):
    account_id: str; at: datetime; actor: str
    field: str; from_value: str | None; to_value: str; reason: str | None

class Criterion(Contract):
    name: str; value: float; target: float; met: bool

class LadderStatus(Contract):
    account_id: str; rung: Preset; next_rung: Preset | None
    criteria: list[Criterion]; ready: bool

ReviewReason = Literal["dial", "spot_check", "format_window", "producer_window",
                       "dub_window", "gate", "sponsored"]

class Violation(Contract):
    code: Literal["missing_ai_label", "missing_ad", "missing_credit", "license_unrecorded",
                  "cross_account_duplicate", "source_held"]
    platform: Platform | None = None
    message: str

class GateResult(Contract):
    violations: list[Violation] = []

class Routing(Contract):
    lane: Literal["review", "auto"]
    reasons: list[ReviewReason]
    dial: ReviewDial
    window: str | None = None             # e.g. "producer:clips:3f2a…:2/5"
    gate: GateResult

class PublisherProfile(Contract):
    profile: str                          # the Upload-Post profile username
    facebook_page_id: str | None = None
    disconnected: dict[Platform, datetime] = {}

# Account gains:
    publisher: PublisherProfile | None = None   # None: not connected; assisted only

PublishState = Literal["pending", "claimed", "scheduled", "retrying", "published",
                       "failed", "fallback", "cancelled"]

class PublishRequest(Contract):
    item_id: str; profile: str; platforms: list[Platform]
    media_url: str; copy: dict[Platform, PostCopy]
    scheduled_for: datetime | None; timezone: str
    ai_disclosure: bool; sponsored: bool
    facebook_page_id: str | None
    key: str                              # sent as Idempotency-Key and request_id (§6.2)

class PublishReceipt(Contract):
    job_id: str | None; request_id: str
    accepted: list[Platform]; rejected: dict[Platform, str]   # platform -> error code

class PlatformResult(Contract):
    platform: Platform
    state: Literal["pending", "published", "failed", "retryable"]
    external_id: str | None = None; url: str | None = None; error: str | None = None

class Lookup(Contract):                   # what Upload-Post knows about a key or a job
    found: bool                           # False: status not_found and no history row
    job_id: str | None = None
    results: list[PlatformResult] = []

class Publisher(Protocol):
    def publish(self, req: PublishRequest) -> PublishReceipt: ...
    def lookup(self, *, request_id: str | None = None, job_id: str | None = None) -> Lookup: ...
    def cancel(self, job_id: str) -> bool: ...
    def scheduled(self, profile: str) -> list[str]: ...   # job ids, for the brake without Neon

class SlotPlan(Contract):
    account_id: str; slot: datetime; item_id: str | None
    state: Literal["planned", "approved", "handed_off", "done", "empty", "missed"]

class Brake(Contract):
    scope: str                            # "all" or an account id
    on: bool                              # /go writes on=False; the key is never deleted
    at: datetime; actor: str; reason: str | None = None

class Link(Contract):
    slug: str; target_url: AnyHttpUrl; account_id: str
    item_id: str | None = None; platform: Platform | None = None
    kind: Literal["bio", "campaign", "affiliate"]; sub_param: str = "subid"

class Click(Contract):
    slug: str; at: datetime; platform: Platform | None
    sub_id: str; country: str | None = None
```

- `PostRecord` gains `publish: dict[Platform, PublishState]` (default `pending`).
- `PostStatus` derivation in `posting/queue.py` doesn't change. `posted_at` stays the only "posted" fact, so an Upload-Post success and a ✅ tap mean the same thing. Both are written through the same `PostingRepo.set_posted` (§3.1).
- `Lookup` merges `status` and `history`, so crash recovery and reconcile ask one question: "does Upload-Post know this key or job?" (§6.3).
- The actor format (`posting/actions.ACTOR`) gains `system:[a-z][a-z-]{0,39}`. That form is for changes nobody tapped:
  - `system:autopilot` (auto-lane approval);
  - `system:demotion`;
  - `system:upload-post` (webhook and reconcile results);
  - `system:daily` (`posting_daily`'s pause repair);
  - `system:migration` (the seed rows).

  Promotions carry the owner's actor (S3 §8.4).

## 3. Data: migration 0002

One expand-only migration. Its number is the next after the head on `main`: 0002 if S2 lands first. If the hooks card's or S3c's migration lands first, S2 takes the next number and drops the deferred items that migration already carries (S3 §8.7). The same change moves `EXPECTED_HEAD` in `db/doctor.py`.

**The deferred items (S3 §8.7):**
- `jobs.error text NULL`.
- `post_events.actor text NULL`, with a check constraint for the actor format (including `system:`, at most 80 characters), backfilled from `data->>'actor'`. From then on, `db/posting._event` writes the column. `data.actor` stays for old rows only.
- `posting_state.changed_by text NULL` and `posting_state.reason text NULL`. `actions.pause` writes them.

**New columns:**

| Table | Columns | One writer |
|---|---|---|
| `accounts` | `publisher jsonb NULL` (`PublisherProfile`) | the accounts service (edit). The webhook changes only the `disconnected` map, by calling that service |
| `content_items` | `copy jsonb NULL`, `review_lane text NULL`, `review_reasons jsonb NULL`, `review_dial text NULL`, `review_window text NULL`, `gate jsonb NULL`, `approved_at timestamptz NULL`, `approved_by text NULL` | `review/service.py`: the routing stamp at plan time, the approval, and the copy edit. Rejection keeps using the existing `verdict_*` columns through `posting/actions.py` |
| `posts` | `publisher text NULL` (`upload_post`, `assisted`), `state text NOT NULL DEFAULT 'pending'`, `claimed_at`, `scheduled_for`, `handed_off_at timestamptz NULL`, `request_id text NULL` (the hashed key, §6.2), `upload_job_id text NULL`, `attempts int NOT NULL DEFAULT 0`, `error text NULL`, `copy jsonb NULL` (frozen at hand-off); indexes `(state, scheduled_for)` and `(upload_job_id)` | **`publishing/state.py`**, through forward-only conditional updates (§6.2). The existing `external_id` holds the platform's post id and `url` its link (set with the publish state); `posted_at` keeps its writer, `PostingRepo.set_posted` (§3.1) |

`accounts.review_tier` stays, but nothing reads it after S2: `autopilot.review_dial` is the source (ADR-48). S3c's spec already moves the tier out of its "rules" class.

**New tables:**
- `autopilot(account_id PK FK, preset, produce, review_dial, publish, scale, runway_days, batch_line_usd, monthly_cap_usd, updated_by, updated_at)`.
  - The migration seeds one Hands-on row per existing account, actor `system:migration`. `monthly_cap_usd` comes from `accounts.monthly_budget_usd` when that is above 0, else the type default (S3 §2.6: clips $5, story $10, band $10, model $10, avatar $20).
  - Account create inserts the row in the same transaction.
  - Readers treat a missing row as Hands-on (`hands_on(account)`), so an account created by code without the row, or a rollback, can never read as more automatic than Hands-on.
- `autopilot_events(id identity, account_id, at, actor, field, from_value, to_value, reason)`, append-only: a trigger rejects UPDATE and DELETE, like S3c's `*_versions`.
- `slot_plans(account_id, slot timestamptz, item_id NULL FK, state, planned_at, updated_at)`, primary key `(account_id, slot)`. **The one writer is `dispatch/plan.py`**: hand-off and the review service ask it to move a slot (`mark_handed_off`, `mark_approved`, `free`), and never write the table themselves.
- `review_messages(item_id, chat_id, message_id, video_message_id, at, kind)`, with primary key `(chat_id, message_id)`.
  - Every review card and every fallback card is recorded here, so a decision on any surface redraws all of them.
  - Today's `sends` table can't hold them: a `sends` row makes the item's derived status `sent`.
- `webhook_deliveries(delivery_id PK, event, received_at, payload jsonb, processed_at NULL)`. The replay guard (§6.4). Kept 30 days, pruned by `posting_daily`.
- `links(slug PK, target_url, account_id FK, item_id NULL, platform NULL, kind, sub_param, created_at, created_by)` and `clicks(id identity, slug FK, at, platform NULL, sub_id, country NULL)`, indexed on `(slug, at)`. No IP address or user agent is stored.

### 3.1 Modes: S2 keeps the Dict current until S1 Task 23

S2 assumes ADR-41's Dual writes stay on until S1 Task 23. S2 is **not** Postgres-only for anything the Dict already holds:
- **"Posted" goes through the PostingRepo.** When the webhook or reconcile learns that a platform published, `publishing/state.py` records `published` (with `external_id` and `url`), then calls `posting.repo.set_posted(ref, platform, True, at, actor="system:upload-post")`. That is the same Dual write a ✅ tap uses: the primary (Postgres) sets `posted_at` and its event, and the mirror writes the Dict's `post:<ref>:posted:<platform>`. `posting verify` therefore stays at 0 differences while Upload-Post posts.
- **Two Dict publishing keys, both written only by `publishing/state.py`** (one writer, ADR-14):
  - **`publishing:inflight:<ref>`, per item.** It is set when a platform of the item is first claimed. It is deleted only when **every** platform the item was claimed on has reached `published`, `fallback` or `cancelled`. A row in `failed` or `retrying` keeps it, because Upload-Post may still publish it until the fallback check settles it. In `dict` mode (the rollback), the assisted pick (`_tick_account` and `/next`) excludes every item that has the key, so an item Upload-Post may still publish can't also go to the phone. Reconcile rewrites a missing one from the rows.
  - **`publish:last_handoff`, fleet-wide.** The UTC time of the last hand-off. It is never deleted, only overwritten by each hand-off. Reconcile is due while it is under 26 hours old (§4.3).
  - **`posting_daily`'s keep-alive touch doesn't read either key, and needn't.** The per-item marker lives as long as its item is unsettled: minutes to a few hours, at worst about a day. That's far under the 7-day expiry, and while a marker exists, reconcile runs and rewrites it from the rows. The fleet key is rewritten at every hand-off, and once it's older than 26 hours nothing depends on it: the daily reconcile run covers the rest from the rows.
- **What stays Postgres-only:** the publish columns, the slot plan, review stamps, autopilot, links and clicks. With `STATE_READS=dict`, the dispatcher runs today's assisted tick only, with the exclusion above; planning, cards and hand-off don't run. The webhook and reconcile keep running while Neon is up, so posts already handed off still reach `posted`.
- **At S1 Task 23** (the Dict writes retire), the in-flight markers and the Dict side of `set_posted` go with them; nothing else in S2 changes.

## 4. The dispatcher (ADR-27) and the slot plan

### 4.1 The cron

`dispatcher` runs every 5 minutes (`*/5`, the same slot as `posting_tick`) and replaces it. That keeps 3 crons: `sweeper`, `dispatcher` and `posting_daily`. Each tick:
1. `ops.flush(now)`: the alert fold, as the old tick did.
2. Reads **only the Dict**: `brake:*`, `posting:outage`, the `posting:schedule:*` copies (which gain the account's publish path, `upload_post` or `assisted`, and its profile; §1.1, §6.7), `publish:last_handoff` (the time of the last hand-off, §3.1) and the task markers. The schedules come from `Posting.all_schedules()` (`posting/backend.py`): the Dict copies in `postgres` mode, and the env account's `POSTING_*` schedule in `dict` mode with no `DATABASE_URL` (production today). `posting_tick`'s `posting.problem` alert ("Posting is off: …") and its outage guard are kept, unchanged.
3. Works out what is due from those reads alone. **Postgres is opened only when a task is due**, so Neon can still scale to zero between due times.
4. Runs each due task within its budget. A slow task (the morning batch of review cards, the digest) is spawned as `dispatch_task(name, key)`, and the tick moves on.

A task is `Task(name, due(now, schedules, markers) -> list[key], run(ctx, key), budget_s)`, registered in `dispatch/tasks.py`. A due key is claimed set-if-absent as `dispatch:<name>:<key>` before it runs, so overlapping ticks run it once. A run that raises releases its claim, so the next tick retries it, and raises an ops alert (kind `dispatch`, subject the task name).

### 4.2 Per-slot phases (accounts publishing through Upload-Post)

**Planning runs in the owner's time zone for every account** (R3; `OWNER_TIMEZONE`, else the posting time zone): once a day at 08:50 owner time. Each account's slots keep their own time zone. The plan's horizon runs from now to **the next plan plus 2.5 h** (about 26.5 h), so every slot has its item and review card before the next morning's batch.

For each account whose schedule copy says `upload_post`:

| Phase | Due | What it does (through `dispatch/plan.py` for slot changes) |
|---|---|---|
| `plan` | daily at 08:50 owner time (key `plan:<date>`, all accounts) | Assigns every slot in the horizon that has no plan yet. Picks with `queue.pick_next` repeatedly, skipping items already planned, held items (`sources.hold_reason(...)`, a function, returns a reason) and items with a Dict in-flight marker. Routes each item (§5.2) and stamps the routing through the review service. Auto-lane items are approved by `system:autopilot`. Writes `slot_plans` (`planned` or `approved`; `empty` if nothing is eligible) |
| `card` | S − 2 h | If the slot's item is unapproved and has no 2 h card yet: send its review card (outside quiet hours, §7.1). If the slot is `empty`, or its item was rejected: plan a replacement now (a review-lane replacement gets its card at once) |
| `handoff` | S − 30 min | If the item is approved: hand it off with `scheduled_date = S` (§6.2). If not: substitute an approved, unplanned item (there are any only on `sample`/`auto`); otherwise mark the slot `missed` and leave the item in the lane, planned first next time |

- **A late approval,** between S − 30 min and S + 30 min (today's `SLOT_WINDOW`), hands off at once. It still sends `scheduled_date = S` while S is in the future, and no `scheduled_date` once S has passed. After S + 30 min the slot is `missed`, and the approved item leads the next plan.
- **An account on the assisted path** (Publish off, or no connected profile) runs today's `_tick_account` at S, unchanged: the pause rule (`PAUSE_AFTER`), the outage guard, the #202 slot guard and the claim. It has no plan and no review cards: sending is the review (Q5).
- **The gate still runs on the assisted path:** with `GATE_ENFORCE` on, an item with violations is held, never sent, and shows in the digest. In S2a the setting is off (the default): violations are only logged and stamped, so the live assisted flow can't change at the deploy. Items imported from the Dict could otherwise be held, for `license_unrecorded` without a source or `missing_credit`. The owner turns it on in S2b, once `clipforge policy dry-run` reports "0 items would be held" (plan Task 8).

### 4.3 Fleet tasks

| Task | Due | Notes |
|---|---|---|
| `digest` | 09:00 owner time (`digest:<date>`) | Spawned. Sends the digest (§7.2), then the review cards for the undecided review-lane items in the plan's horizon (§7.1), paced |
| `publish_reconcile` | every 15 min while `publish:last_handoff` is under 26 h old; once a day regardless (which covers rows still in flight after that) | Runs crash recovery for rows stuck in `claimed` (§6.3), the retry check and deliberate retries for rows in `retrying` (§6.2), status lookups for rows still `scheduled` 10 min after their slot, the fallback check (§6.6), and the unmatched webhook deliveries (§6.4). The daily run also reads history for the last 2 days, catching deliveries dropped during Upload-Post's 30-minute pauses. It rewrites missing per-item markers from the rows. Its writes go through `state.py` |
| alert fold | every tick | `ops.flush`, moved from the tick |
| (later) queue filler, analytics pull, program checks, weekly report | daily/weekly | S6, S7 and S3b register their tasks here; no new cron |

### 4.4 Never sending a slot twice (the #202 guard, extended)

**Three guards each stop a second claim on their own:**
1. `slot_plans` primary key `(account_id, slot)`: one plan per slot.
2. Hand-off asks `plan.py` to move the slot `approved → handed_off` with a conditional update; a second runner finds nothing to move and stops.
3. Each platform is claimed only from `pending` (`publisher IS NULL`), or, for a deliberate retry, from `retrying` (§6.2). **Nothing ever re-claims a row in `claimed`.**

**A fourth guard covers the one window those three can't: a crash between the HTTP call and recording its receipt.**
- The row stays `claimed` with its stored key.
- Crash recovery (§6.3) first asks Upload-Post whether it knows that key.
- It re-sends with the **same** key only if Upload-Post has no job and the claim is recent; otherwise it records what Upload-Post knows, or a final failure.

The key alone isn't relied on, because Upload-Post doesn't document how long it keeps one (R5 measures it).

A lost or renamed Dict claim, a retried tick or a redeploy mid-hand-off is stopped by guards 1–3. A crash after the call is handled by guard 4 together with recovery's lookup. The runbook's deploy blackout (#108) stays as it is for the assisted path.

**Load on Neon:** about 3 wake-ups per slot plus one plan a day. At 4 slots that's about 13 wake-ups per account per day, plus about one webhook per post and any bio-link clicks (§7.4).

## 5. Routing, the gate, windows and the ladder

### 5.1 The policy gate v1 (`policy/gate.py`, pure)

`gate(item, account, source, copy, others) -> GateResult`. It runs at plan time and again at hand-off, so a copy edit or a permission change in between is caught. `others` holds the planned and posted items of other accounts that share the item's `source_hash`, read by the caller.

| Code | Fails when |
|---|---|
| `missing_ai_label` | an asset is `generated` or `music_generated` and `item.ai_disclosure` is false (the publisher maps the flag to every platform's field, §6.2) |
| `missing_ad` | the item is sponsored and a platform's copy lacks `#ad` |
| `missing_credit` | the blueprint's compliance profile has `require_credit`, or the source is a `channel`, and a platform's copy doesn't name `source.credit_name` |
| `license_unrecorded` | an asset has no license. A `source_video` asset is checked against the source's **current** permission, not its stamped string, so items imported from the Dict (stamped `unrecorded`) pass when their source has a recorded permission |
| `cross_account_duplicate` | another account has planned or posted a clip of the same `source_hash` with IoU > 0.5 |
| `source_held` | the function `sources.hold_reason(source, platforms, now)` returns a reason (an expired or narrowed permission); the item isn't planned at all, as today |

The gate never edits anything. Any violation sends the item to the review lane, and the card shows each violation in plain words. The banned-claims check comes with the Judge in S6.

### 5.2 Routing (`review/routing.py`, pure)

`route(item, autopilot, gate_result, window_counts, spot_state, account_age) -> Routing` records **every** reason that applies; any one reason sends the item to `review`.
1. **gate:** at least one violation.
2. **sponsored:** a sponsored item in the account's first 30 days (counted from its first post). Brand-deal items go to review always, once S13 adds that flag.
3. **Windows** (ADR-48, ADR-49).
   - **What counts (R2):** items of the account decided **through `review/service.py` by a person**: approved or rejected by an actor that isn't `system:`. Assisted-card taps (✅, ⏭ and 🗑 on posting cards) don't count, because a ✅ means "posted", not "reviewed". Counting therefore starts at S2b, the first step with review cards.
   - `producer_window`: fewer than 5 counted decisions with the item's `producer_version`. Legacy `plan-c` items count as their own version.
   - `format_window`: the item was made under an account version with `format_changed`, and fewer than 10 counted decisions exist under it. This reads S3c's `account_versions`; until that table exists, the window is always closed.
   - `dub_window`: `parent_item_id` belongs to the account's paired account, and fewer than 10 dubs in the pair have counted decisions (S10 produces dubs; the rule is built and tested now).
4. **dial:** `review` sends every item to review; `auto` sends none. On `sample`, an item is a **spot check** when either:
   - 9 or more auto-routed items have passed since the account's last spot check; or
   - fewer than 3 spot checks fall in the last 7 days, and the last one was at least 24 h ago.

   This is deterministic, so tests can replay it, and it gives at least 1 in 10 and at least 3 a week (S3 §2.4).

The stamp on the item (`review_lane`, `review_reasons`, `review_dial`, `review_window`, `gate`) plus a `routed` `post_events` row make every result attributable (S3 §8.4: the dial and window in force).

### 5.3 The review service (`review/service.py`)

- `approve(ref, actor, now)`:
  1. sets `approved_at` and `approved_by` and writes an `approved` event;
  2. asks `plan.py` to move the item's slot to `approved`;
  3. redraws every card.

  A late approval hands off at once (§4.2).
- `reject(ref, reason | None, actor, now)`:
  1. the existing `posting/actions.reject` and `set_reason` (the same verdict columns, Dual-written as today), plus a `reviewed` event marking it a review decision for counting (R2);
  2. asks `plan.py` to free the item's slot for replanning;
  3. redraws every card.

  If the item was a spot check, demotion is checked inline (§5.5).
- `queue(account)` for `GET /admin/review?account=`: the review lane with reasons, due times and gate answers.
- `set_copy(ref, copy, actor)` for `PUT /admin/review/{item}/copy`, which writes `content_items.copy`. Copy edits are the dashboard's (ADR-44); S3 adds the page.
- Approve and reject refuse an item already decided, and return who decided it and when: "Approved by telegram:… at 09:04" (S3 §7.2).
- Every call is wrapped like `posting/actions._store`: a database error answers "Store unavailable, nothing changed".

### 5.4 The autopilot service (`accounts/autopilot.py`, the one writer)

- `get(account_id)`, which returns `hands_on(account)` when the row is missing, and `history(account_id)`.
- `set(account_id, field, value, actor, reason)` and `apply_preset(account_id, preset, actor, reason)`.
  - Each write updates `autopilot` and appends one `autopilot_events` row per changed field, in one transaction.
  - A single override turns the preset into `custom`, shown as "Hands-on, with Publish off".
- **Any owner change to the Review dial needs a reason** (S3 §8.4), in either direction. The system writes its own reasons (demotions).
- A change to `publish` asks the accounts service to rewrite `posting:schedule:<account>` (§1.1).
- `waiting_on(account_id) -> dict[str, str]` gives the one-line "waiting on" per control, e.g. "Publish: on, waiting for a connected profile", "Produce: off (the queue filler arrives in S6)", "Scale: no paired account".
- Produce and Scale are stored but have no effect until S6 (the filler) and S10 (dubs).

### 5.5 The ladder and demotions (`accounts/ladder.py`, pure over counted stats)

All counts use R2's rule (§5.2): only decisions through the review service count, from S2b on.

| Move | Criteria |
|---|---|
| Hands-on → Supervised | ≥ 30 days since the first post, ≥ 50 counted approvals, < 10% rejected among the last 50 counted decisions, no gate failure in 14 days |
| Supervised → Autopilot | ≥ 30 days on Supervised (from `autopilot_events`), ≥ 12 spot checks with ≤ 1 rejected, no gate failure or strike in 30 days, runway ≥ 14 days |
| Demotion, one step (automatic) | 2 rejects among the last 5 spot checks; actor `system:demotion`, reason "2 rejects in the last 5 spot checks" |
| Demotion to Hands-on (automatic) | a strike; actor `system:demotion`, reason "strike on <platform>" |

- **Runway** in S2 is a simple version: eligible queued items ÷ slots per day. S3 replaces it with §3.3's runway (unclipped material included).
- **Strikes:** Upload-Post documents no strike event, so `record_strike(account, platform, actor)` is called by `clipforge autopilot strike` in S2, and by S3's manual entry later.
- **Promotions are always the owner's.** A ready promotion is a digest line. Until S3's one tap exists, the owner promotes with `clipforge autopilot promote <account>` (actor `cli:<user>`; the reason is generated: "promotion suggested by the ladder: 34 days on Supervised, 13 spot checks, 0 rejected"). The admin route `POST /admin/accounts/{id}/autopilot/promote` is the same call, with `web:<login>`. Telegram gets no promote button (#427).

## 6. Publishing

### 6.1 Media links (`publishing/media.py`)

`GET /media/{item_id}.mp4?exp=&sig=` on `web`:
- **Signature:** `sig = HMAC(DOWNLOAD_SIGNING_KEY, "media:{item_id}:{exp}")`. The `media:` prefix keeps a zip-link signature from ever verifying here, and the reverse.
- **TTL:** 24 h (`MEDIA_LINK_TTL_S`), which covers Upload-Post's background fetch and its retries.
- **Serving:** it serves the item's `video_path` with range support, after validating the item id (the `<job_id>:<clip_id>` form, `jobs.is_job_id`) and checking that the resolved path stays inside `/jobs`.
- **Errors:** a missing key answers 503; a bad or expired signature answers 403; a missing file answers 404. Media is never served without a signature.

### 6.2 The state machine and hand-off (`publishing/state.py`, `publishing/handoff.py`)

Per `posts` row (item × platform). Every move is a forward-only conditional update in `state.py`, with a `post_events` row in the same transaction.

```
pending ─claim─► claimed ─publish accepted─► scheduled ─webhook / lookup: published─► published ─► set_posted (Dual)
                   │ │                          │
                   │ │                          └─ webhook / lookup: retryable ─► retrying
                   │ └─ retryable error ─► retrying ─retry claim (attempts+1, new key)─► claimed
                   │                          └─ attempts = 3 ─► failed
                   └─ crash recovery: no job and claim too old ─► failed
   scheduled/failed ─fallback check (cancel ok, or lookup says failed)─► fallback ─ ✅ tap ─► set_posted (Dual)
   scheduled ─brake─► cancelled ─/go─► pending
```

**The key.** `key = sha256("<item_id>|<sorted platforms>|<attempt>").hexdigest()[:32]`, stored in `posts.request_id` and sent as both `Idempotency-Key` and `request_id`. Hex only, so it fits any header and query rule, and it carries no item id in clear.

**Hand-off, for one approved item:**
1. **Check before claiming.** Re-check the brake (the Dict) and re-run the gate. A violation un-approves the item (back to the lane, reason `gate`), and its slot goes to the substitute rule (§4.2).
2. **Claim** the item's platforms that aren't disconnected, in one transaction (`state.claim`):
   ```sql
   UPDATE posts SET publisher='upload_post', state='claimed', claimed_at=:now,
       attempts=1, request_id=:key, copy=:frozen_copy
   WHERE item_id=:item AND platform = ANY(:platforms)
     AND publisher IS NULL AND state='pending'
   RETURNING platform
   ```
   - The copy is frozen here: `item.copy` or `captions.py`, with tracked links (§7.4).
   - The Dict in-flight marker is written in the same step (§3.1).
   - Disconnected platforms go straight to the fallback (§6.6).
3. **Commit, then call** `publisher.publish(...)` with the key.
4. **Record the receipt:** accepted platforms move to `scheduled` (`upload_job_id`, `scheduled_for`, `handed_off_at`). Rejected platforms move to `retrying` (retryable codes) or `failed` (final codes). `state.py` overwrites `publish:last_handoff`.
5. **Re-check the brake.** If a brake now covers the account, cancel at once (§6.7): `/pause` may have run between steps 1 and 4.
6. **Ask `plan.py` to move the slot** `approved → handed_off`.

**The retry check.** A row in `retrying` that has an `upload_job_id` (Upload-Post accepted it, then reported a retryable failure) first gets the fallback check's two calls on that job: `cancel(upload_job_id)`, then `lookup(job_id=…)`.
- If the lookup says `published`, the row is recorded as published (and `set_posted`), with no retry.
- If the status is still pending and the cancel failed, the row waits for the next reconcile.
- Only a successful cancel, or a lookup that says `failed`, lets the retry claim run.

A row rejected at submit (no `upload_job_id`) skips the check.

**A deliberate retry** (reconcile, for rows in `retrying` that passed the retry check) is a new claim, never a re-send:
```sql
UPDATE posts SET state='claimed', claimed_at=:now, attempts=attempts+1, request_id=:new_key
WHERE item_id=:item AND platform=:platform AND publisher='upload_post'
  AND state='retrying' AND attempts < 3
```
The new key is minted from the new attempt number, then steps 3–5 run again. A row in `retrying` with `attempts = 3` moves to `failed`.

**Final and retryable.**
- **Retryable:** 429 (the per-day caps), 5xx, timeouts and Upload-Post's `retryable`.
- **Final:** a per-platform failure Upload-Post reports as final; validation errors (4xx other than 429); `tiktok_privacy_unavailable`; or a row still `scheduled` with no result 60 min after its slot (Upload-Post's own "failed after 1 h inactivity"), confirmed by the fallback check (§6.6).

**The one claim per (item, platform).** Exactly three conditional updates give a row a publisher: the first claim (`publisher IS NULL AND state='pending'`), the retry claim (`publisher='upload_post' AND state='retrying'`) and the fallback claim (§6.6). The assisted path therefore runs only after Upload-Post's confirmed final failure, and the two can never both publish the same (item, platform).

**The publish call** (`publishing/upload_post.py`): `POST /api/upload`, multipart, `Authorization: Apikey <UPLOAD_POST_API_KEY>`:
- `user=<profile>`, `video=<media link>`, `platform[]=…`, `async_upload=true`;
- `scheduled_date=<slot ISO>` and `timezone=<account tz>` while the slot is in the future (omitted once it has passed);
- per platform from the frozen copy: `tiktok_title`, `instagram_title`, `youtube_title` + `youtube_description`, `facebook_title` + `facebook_description`, plus `title` (required for YouTube);
- `facebook_page_id`;
- the AI flags from `ai_disclosure`: `is_aigc`, `is_ai_generated` (Instagram, TikTok, YouTube alias), `containsSyntheticMedia`, `facebook_is_ai_generated`;
- `disable_inbox_fallback=true`: a TikTok draft isn't a post, so it counts as a failure and goes to the fallback;
- `privacy_level` is omitted, so the account default applies. Connecting a profile includes checking that the TikTok account allows public posts (§9).

It uses httpx (timeouts 10 s connect, 30 s total) and logs only the host, the status and the item id: never the API key, the signed media link or the response body (rule 8). `lookup` maps to `GET /api/uploadposts/status` (then `GET /api/uploadposts/history` when the status is `not_found`). `cancel` maps to `DELETE /api/uploadposts/schedule/<job_id>`, and `scheduled` to `GET /api/uploadposts/schedule?profile_username=`.

### 6.3 Crash recovery (`publishing/reconcile.py`)

A row still `claimed` more than 2 minutes after `claimed_at` means hand-off stopped between the claim and the receipt. Recovery **never re-claims**:
1. `lookup(request_id=<stored key>)`.
2. **Upload-Post has a job:** record it as the receipt (`scheduled`, with `upload_job_id`) and apply any per-platform results it already carries (`published`, `retrying`, `failed`).
3. **No job, and the claim is under `RECOVERY_WINDOW_S`:** re-send once with the **stored** key (steps 3–5 of hand-off).
   - **The default is 0, so there is no re-send** until R5's real call confirms that Upload-Post keeps a key for at least 10 minutes. Then it becomes 600.
   - If the 10-minute repeat fails, the rule stays "no re-send". The window is never lowered to fit, because a re-send with a forgotten key could post twice.
4. **No job, and no re-send:** mark the row `failed` with `error="lost hand-off"`. The fallback check (§6.6) then decides, and for a row without a job it waits longer before any fallback.

### 6.4 The webhook (`publishing/webhook.py`, `POST /webhooks/upload-post` on `web`)

1. **Check the signature.** `UPLOAD_POST_WEBHOOK_SECRET` missing answers 503. It verifies `X-Upload-Post-Signature` (`sha256=` + HMAC-SHA256 of `"<X-Upload-Post-Timestamp>.<raw body>"`) with `hmac.compare_digest`, and that the timestamp is within 5 minutes; otherwise 401.
2. **Insert and process in one transaction:**
   - `INSERT INTO webhook_deliveries … ON CONFLICT DO NOTHING`, then `SELECT … FOR UPDATE` on the row.
   - If `processed_at` is already set, it's a replay: answer 200 and change nothing.
   - Otherwise process the event (step 3) and set `processed_at`, in the same transaction.

   A concurrent duplicate waits on the row lock and then sees `processed_at`. A crash before the commit leaves nothing, so Upload-Post's next delivery, or reconcile, processes it.
3. **`upload_completed`:** find the row by `upload_job_id` and `platform`.
   - Success: `published` with `external_id` and `url`, then `posting.repo.set_posted(ref, platform, True, at, actor="system:upload-post")` (Dual, so the Dict gets `posted:<platform>`; §3.1).
   - Failure: `retrying` or `failed` by its error, as in §6.2.
   - **An unknown `job_id`** (hand-off hasn't recorded its receipt yet, or crashed) is stored with `processed_at` left empty and answers 200, so Upload-Post doesn't pause the channel. Reconcile resolves it:
     1. it runs crash recovery (§6.3) for `claimed` rows, which records their job ids;
     2. it calls `lookup(job_id=…)` for the delivery;
     3. it re-runs the stored delivery once a row has that `upload_job_id`.

     A delivery unmatched after 24 h raises an ops alert.
4. **`social_account_disconnected` and `social_account_reauth_required`:** set `accounts.publisher.disconnected[platform]` through the accounts service and raise an instant `publisher_disconnected` alert (§7.3). **`social_account_connected`** clears it.
5. Ops alerts are sent after the commit. The answer comes well within Upload-Post's 10 s limit (a few row writes).

Webhook deliveries lost while Upload-Post's channel is paused are recovered by `publish_reconcile` (§4.3), never by a replay.

### 6.5 Reconcile for scheduled rows

A row still `scheduled` 10 minutes after its slot gets `lookup(job_id=…)`. Its results apply exactly as a webhook's would, including `set_posted` for a success. A row still unresolved 60 minutes after its slot goes to the fallback check (§6.6).

### 6.6 Fallback and the assisted path (`publishing/assisted.py`)

`AssistedPublisher` wraps today's `bot/posting._deliver` with a platform subset. It is used in two ways:
- **Accounts on the assisted path** (Publish off, or no profile; Q5). This is today's flow at the slot, unchanged: the same `p:` callbacks, so old messages keep working. The gate holds violating items. In `dict` mode, items with a Dict in-flight marker are excluded (§3.1).
- **The fallback.** Before any fallback claim, the **fallback check**:
  1. If the row has an `upload_job_id`, call `cancel(job_id)`, then `lookup(job_id=…)`.
  2. If the lookup says `published`: record it as published (and `set_posted`); there is no fallback.
  3. The fallback proceeds **only if** one of these holds:
     - the cancel succeeded;
     - the lookup says that platform `failed`;
     - the row has no job at all (§6.3 step 4), and all three of the following are true:
       - it is now at least 60 minutes after the slot;
       - `publisher.scheduled(profile)` shows no job;
       - `lookup(request_id=<stored key>)`, which reads status and then history, still finds nothing.

     An async upload that is slow to appear therefore gets the full hour before the phone is asked to post by hand.
  4. Otherwise (the cancel failed and the status is still pending) the row stays as it is; the next reconcile repeats the check, and after 3 inconclusive checks an ops alert asks the owner to look.

  Then:
  1. The fallback claim moves the row `publisher='upload_post' AND state IN ('failed','scheduled')` → `publisher='assisted', state='fallback'`.
  2. An instant `publish_failed` alert goes out (§7.3).
  3. If the slot is still today and the account has a chat, the assisted card follows, listing **only the failed platforms**. It is recorded in `review_messages` (kind `fallback`), not in `sends`, so the item's derived status doesn't change.
  4. The ✅ tap goes through `posting/actions.set_posted`, as today.

### 6.7 The brake

**Commands:** `/pause [account|all]` and `/go [account|all]`, through `posting/actions.pause`; the dashboard later uses the same function. With no argument, `/pause` is the whole fleet (today's `/pause` already pauses every account).

**`/pause`:**
1. **Write the Dict key `brake:<scope>`** (`Brake` JSON) first. That's the part that must survive a Neon outage.
2. **Then write `posting_state`** for each account in scope (`paused`, `changed_by`, `reason`), through the PostingRepo as today (Dual). If Neon is down, the reply says "Paused. The database is unavailable, so this is recorded in the brake only."
3. **Effect:** every dispatcher phase skips a braked scope (`brake:all` or `brake:<account>` with `on=true`). Hand-off checks before claiming and again after recording the receipt (§6.2 steps 1 and 5).
4. **Cancel what's already scheduled.** `posts` rows in `scheduled` with `scheduled_for > now`, in scope, get `publisher.cancel(job_id)` and move to `cancelled`.
   - With Neon down, the job ids come from Upload-Post's own list (`publisher.scheduled(profile)`; the profile is in the account's Dict schedule copy). Reconcile then fixes the rows.
   - Hand-off happens 30 min ahead, so there are at most a few posts per account to cancel.
5. **The reply counts the result:** "Paused realtalk-clips-en: 1 scheduled post cancelled, 0 already out."

**`/go`:**
1. Overwrites the key with `on=false` and the time (never deletes it, so the time of every `/go` survives a Neon outage). Then it writes `posting_state` (`paused=false`, `changed_by`, `reason`) through `posting/actions.pause`, as `/pause` does.
2. Moves `cancelled` rows back to `pending`. Their items lead the next plan; a slot whose time has passed is `missed`.
3. Clears `posting:outage`, as today (#217).
4. `/go <account>` while `brake:all` is on records the account's `on=false`, but the fleet brake still covers it. The reply says "still braked by /pause all; send /go all to resume".

**Expiry and repair.**
- A brake key must never expire into "go". Every dispatcher tick reads every `brake:*` key (on and off) with `get`, which counts as activity (ADR-24).
- `posting_daily` compares each brake key with `posting_state`. Where they differ, **the newer one wins**, comparing `Brake.at` with `posting_state.changed_at`. It repairs through `posting/actions.pause` with actor `system:daily`, so pausing keeps one writer.
  - A key newer than the row (a `/pause` or `/go` during a Neon outage) → `posting_state` is written to match the key.
  - A row newer than the key → the key is rewritten to match the row.
  - **A missing key is never restored blindly.** A key can only be missing if it expired (impossible while the dispatcher reads it every tick) or was never written. Then the row is written to the Dict only if the row says paused, and the repair raises an ops alert so the owner sees it.

The brake is one of the two one-tap actions Telegram keeps (#427).

## 7. Telegram, the digest, failure rows and tracking links

### 7.1 Review cards (`review/cards.py`)

- **The card:** the video, then a text: the account, the slot ("goes out 13:00, America/New_York"), the reasons in plain words ("producer window: 2 of 5", "spot check", each gate violation), and the copy per platform (read-only).
- **Buttons:** **✅ Approve** · **🗑 Reject**, then the reason row (`RejectReason`, as today). **Open ↗** to `/act/review/<item>` once S3 serves that page; before S3 the card has no Open button.
- **Callbacks:** `r:ok:<ref>`, `r:rej:<ref>`, `r:why:<reason>:<ref>`. The `p:` callbacks of the posting flow are unchanged, so every older message keeps working. Taps are accepted only from `TELEGRAM_ALLOWED_USER_IDS`, in the account's chat; actor `telegram:<user id>`.
- **After a decision on any surface,** every card of the item (`review_messages`) is redrawn: "Approved · telegram:… · 09:04 · out at 13:00", or "Rejected · Bad crop".
- **When cards are sent:**
  - **the 09:00 batch** (Q3, R1): one card per undecided review-lane item in the plan's horizon (§4.2), sent after the digest.
    - It is a bridge behind `REVIEW_BATCH=on` (default on), turned off when S3's Review page ships.
    - **It is exempt from ADR-45's 20-an-hour cap and counts as one delivery** (R1, amending #442).
    - `dispatch_task` paces the sends at most one message per second to the chat (each card is two messages, video then text), staying under Telegram's per-chat limit. A 429 from Telegram waits its `retry_after` and continues.
  - **the 2 h card** (§4.2): for any review-lane item still undecided 2 h before its slot, or a replacement planned inside that window. These count as instant messages under ADR-45's limits.
- **No card is sent** for items due more than 2 h ahead outside the 09:00 batch. A 2 h card that falls in quiet hours (23:00–08:00) isn't sent: its item already had a card in the batch, and if it is still undecided at hand-off, the slot takes the substitute or is missed (§4.2).

### 7.2 The 09:00 digest (`dispatch/digest.py`)

One message at 09:00 in the owner's time zone (R3), claimed `digest:<date>`. Lines with nothing to say are left out. An empty day is one line: "Nothing needs you today. Yesterday: 12 posted across 3 accounts."
1. **Anomalies first:** an outage (`posting:outage`), a brake that's on, a disconnected publisher, yesterday's final publish failures, the database unavailable at a tick, unmatched webhook deliveries.
2. **Yesterday, per account:** posted (of which automatic), failed, rejected; "ran without you" (auto-approved items, demotions, from `post_events` and `autopilot_events`).
3. **Today, per account:** slots, approved, need you.
4. **The attention arithmetic** (S3 §2.7):
   - one line, e.g. "Today: 9 review cards ≈ 9 min + 2 assisted clips ≈ 14 min = ~23 of ~20 min";
   - after S2 a decision counts about 1 minute and an assisted clip about 7;
   - when it's over budget, the line names the accounts whose ladder criteria are met.

   Then "N review cards follow ↓".
5. **Digest-level rows (S3 §4):**
   - promotions ready, with the command until S3;
   - demotions done;
   - runway under 14 days;
   - held clips;
   - permissions expiring within 14 days;
   - other job failures;
   - the review backlog;
   - missed slots.

Links appear only to pages that exist: `/jobs/<id>` before S3, then 08 §2b and §2c's formats as S3 ships them, under S3's link-contract test. The digest is built from one read per account plus fleet counts, all in `dispatch_task`.

### 7.3 Failure rows and alerts

| Row | Raised by | Level |
|---|---|---|
| `publish_failed` (subject `<item>:<platform>`) | the fallback (§6.6), on a confirmed final failure | instant; **urgent** (through quiet hours) when final failures hit 2 or more accounts within an hour ("publishing broken across accounts", ADR-45) |
| `publisher_disconnected` (subject `<account>:<platform>`) | the webhook | instant |
| `strike` (subject `<account>:<platform>`) | `clipforge autopilot strike` (no webhook exists) | instant, with the automatic demotion |

- Each alert goes through `ops.alert` (dedup per kind, subject and hour; quiet hours; the cap) with `path="/act/<kind>/<subject>"` for S3's Open button.
- **The data is S2's:** `publishing.open_problems()` returns the rows that are failed or in fallback and not posted, the disconnected flags, the recorded strikes and unmatched deliveries. **The "needs me" list is S3's:** `GET /needs` turns them into rows (S3 §8.3).

### 7.4 Tracking links (`tracking.py`; ADR-33)

- **`GET /go/{slug}` on `web`,** public:
  1. Look up `links`; an unknown slug answers a plain 404.
  2. Validate `?p=`: only `tt`, `ig`, `yt` or `fb`; anything else is recorded as no platform and never echoed.
  3. Write a `clicks` row with `sub_id = <account>.<item or "bio">.<platform or "x">` and `country` only if the request carries a country header. This is best-effort: a failed write never blocks the redirect.
  4. Answer 302 to `target_url` with the sub-id in `sub_param`.

  No IP address or user agent is stored. **Every click opens Neon** (a lookup and an insert), so a busy bio link keeps it awake while clicks arrive. That's acceptable at today's volume; S7 can cache the links in the Dict if clicks grow.
- **Slugs:** 8 random base62 characters (`secrets.choice`).
- **Creation:** `clipforge link add <account> <url> --kind bio|affiliate [--sub-param p]` and `POST /admin/links` (actor recorded).
- **Use in copy.**
  - When the copy is frozen at hand-off, an account's `brand.bio_link` and any affiliate link are replaced by `<API_URL>/go/<slug>?p=<platform>`, one link per account and link, with the per-platform `p`.
  - A campaign's `required_links` stay verbatim: campaign programs attribute on their own links.
  - For the clip accounts this is mostly the bio link. Per-item sub-ids matter from S8 (avatar offers).
- Conversion import is not here: it becomes draft ADR-51 (§11.3), for S7.

## 8. Tests and safety

Every item has its tests in the same task, written first. DB tests use the local Postgres, and fail, never skip, without it. Fast tests mock every network call.

| Area | Tests |
|---|---|
| Publisher contract | `FakePublisher` (scripted per-platform results, a key → job map, a call log, a configurable `lookup`) for the hand-off, recovery and fallback tests. `UploadPostPublisher` against an httpx `MockTransport`, with golden request fields per platform (AI flags, `facebook_page_id`, `disable_inbox_fallback`, per-platform titles, `scheduled_date` and `timezone`, the hashed key as `Idempotency-Key` and `request_id`), error mapping (429 and 5xx retryable; `tiktok_privacy_unavailable` final) and `lookup` (`not_found` falls back to history). No secret or signed URL in logs (a `caplog` check) |
| Gate | About 15 golden cases in EN and ES, `(item, account, source, copy) → violations`: an AI asset without the flag; sponsored without `#ad` on one platform; a missing credit; an `unrecorded` Dict item with and without a recorded source permission; a cross-account duplicate at IoU 0.4 and 0.6; an expired permission |
| Routing | One case per reason. Several reasons together. **R2:** only review-service decisions by people count; a `system:autopilot` approval and assisted ✅/🗑 taps don't close a window. Spot checks over a 30-item sequence give ≥ 1 in 10 and ≥ 3 a week, the same picks on every run |
| Autopilot and ladder | Presets and overrides (`custom`). History rows per changed field. The trigger rejecting UPDATE and DELETE. A reason required for any owner change to the dial. A missing row reads as Hands-on. The seed's `monthly_cap_usd` from the budget or the type default. A Publish change rewrites the schedule copy. Ladder criteria from fixtures, at and just below each threshold. The second reject in the last 5 spot checks demotes inline (`system:demotion`). A strike drops to Hands-on |
| Claim per (item, platform) | Two connections race the first claim and exactly one wins. A row in `claimed` is never re-claimed. The retry claim works only from `retrying` and below 3 attempts, with a new key. The fallback claims only after the fallback check. Upload-Post and the assisted path never both hold one row. A disconnected platform goes straight to the fallback |
| Crash recovery and keys | A crash after `publish` and before the receipt: lookup finds the job (recorded, no second call); no job with `RECOVERY_WINDOW_S=0` (no re-send: `failed`, then the fallback check, which waits until slot + 60 min and checks `scheduled(profile)` and the lookup again); no job with the window at 600 and inside it (one re-send with the stored key); no job after it (`failed`). The retry check on a `retrying` row with a job: published → no retry; pending with a failed cancel → waits; cancelled or failed → retry claim. A deliberate retry mints a new key, never reuses one. Keys are 32 hex characters and deterministic per (item, platforms, attempt) |
| No double send (#202) | Overlapping ticks. A lost Dict claim. A renamed claim key (`dispatch:` prefix changed). A late approval racing the hand-off phase. The brake set between claim and receipt (cancelled after the receipt). The assisted path's existing guard tests keep passing |
| Dict mirror (§3.1) | A webhook success writes `posted_at` in Postgres and `post:<ref>:posted:<platform>` in the Dict through Dual; `posting verify` reports 0 differences after a day of Upload-Post posts in a test. The per-item marker is set at the first claim and kept through `failed` and `retrying`, then deleted only when every claimed platform is `published`, `fallback` or `cancelled`. `publish:last_handoff` is overwritten, never deleted, and reconcile stops being due 26 h after it. Only `state.py` writes either key (an import check). In `dict` mode the assisted pick skips an item with a marker |
| Dispatcher | `due()` from the Dict alone: a tick with nothing due runs against a database stub that fails if touched. Planning at 08:50 owner time for accounts in other time zones, with the horizon to the next plan plus 2.5 h. Each phase at S − 2 h, S − 30 min and S. Planning skips held, planned and in-flight items. Substitution and `missed`. Only `plan.py` writes `slot_plans` (an import check). A failed task releases its claim and alerts. Spawned tasks run once |
| Brake under a Neon outage | With the database raising `DatabaseUnavailable`: `/pause realtalk-clips-en` and `/pause all` set the Dict key and reply honestly; the dispatcher skips the scope; cancel uses `publisher.scheduled(profile)`; `posting_daily` later repairs `posting_state` through `actions.pause` (`system:daily`). Newer wins both ways: a `/go` written to the Dict during the outage beats an older paused row, and a missing key is never restored blindly. `/go` writes `on=false` (never deletes) and moves `cancelled` rows to `pending` |
| Webhook | A valid delivery. **The same delivery replayed twice** (200, one event, one state change). **Two concurrent copies** (the row lock: one processes, one sees `processed_at`). A crash before the commit (reprocessed next time). A bad signature, a stale timestamp, a missing secret (503). An unknown job id (stored unprocessed, then matched by reconcile). The disconnect and connect events |
| Fallback | Cancel succeeds → fallback. Cancel fails, lookup `failed` → fallback. Cancel fails, lookup `published` → published, no card. Cancel fails, lookup pending → no fallback, re-checked, alert after 3 |
| Media links | Signature and expiry. The `media:` prefix (a zip-link signature is refused, and the reverse). A path escaping `/jobs`. Range requests |
| Cards and digest | Golden texts. `r:` callback parsing (and `p:` unchanged). Redraw of every card on approve and reject from either surface. "Already decided" answers. The batch flag. **Paced sends** (no more than 1 message a second; a Telegram 429 waits and continues). The batch is not counted against the hourly cap. The digest leaves out empty lines and shows the attention arithmetic |
| Tracking links | The redirect with its sub-id. A failed click write still redirects. An unknown slug. `?p=` validation. Copy wrapping for bio and affiliate links, while campaign links stay verbatim |
| Migration | Up and down. An empty autogenerate diff. The `actor` backfill from `data.actor`. The seed rows. `EXPECTED_HEAD` moved |
| Cost | Hand-off and webhook record nothing per post. `Prices` gains the Upload-Post plan as a fixed subscription (shown on S3's Costs, never against caps) |

**Reviewers:**
- `migration-reviewer`: 0002, the `posts` claim updates and the Dual write path.
- `security-reviewer`: the webhook, media links, `/go`, the new secrets, and logs.
- `pr-reviewer`: before every merge.
- `pipeline-reviewer` isn't needed: no stage changes.

**Secrets:** `UPLOAD_POST_API_KEY` and `UPLOAD_POST_WEBHOOK_SECRET` (the `whsec_…` value), in `clipforge-secrets` and `.env`. Both are optional: without them, publishing is off with the reason in `/status` (like `Settings.posting_problem`), and the webhook answers 503.

**New settings:** `GATE_ENFORCE` (`on`/`off`, default `off`; on from S2b, after the dry run), `REVIEW_BATCH` (`on`/`off`, default `on`), `MEDIA_LINK_TTL_S` (default 86400), `RECOVERY_WINDOW_S` (default 0 = no re-send; 600 after R5 confirms key retention) and `UPLOAD_POST_PROFILE_LIMIT` (default 5). Account create warns when the profiles in use would exceed `UPLOAD_POST_PROFILE_LIMIT` (O4: upgrade at the 6th).

**Cost:**
- **Upload-Post Basic** is $24/month, a fixed subscription.
- **Modal:** the same 5-minute cron as today, plus a few webhook, media and API calls a day, so variable cost is negligible.
- **Neon:** about 13 wake-ups per account per day, plus about one webhook per post and every tracking-link click; it still scales to zero between them at today's volume.
- **The build card's cap:** about $5 for smoke runs, plus a few real posts.

## 9. Rollout of S2 (owner steps; the plan and the runbook carry the exact commands)

**S2a**, after card 010 (`STATE_READS=postgres` verified; Dual writes on):
1. Deploy outside the posting slots (runbook §1). CI runs 0002.
2. For one day, check that `dispatcher:` log lines show the same sends as yesterday's `posting_tick:` lines, that `posting verify` stays at 0, and that `db_doctor` reports the new head.
3. Test `/pause realtalk-clips-en`, `/go`, `/pause all` and `/go` in Telegram, and `clipforge autopilot show realtalk-clips-en`: Hands-on, "Publish: on, waiting for a connected profile".

Nothing else changes for the owner.

**Before S2b's build (R5):** one real Upload-Post call, by the S2 build card's session with the owner, on a test profile with a private or self-only post. It must confirm:
- that a repeated `Idempotency-Key` returns the same job, and for how long (repeat after 10 minutes and after 24 h);
- Basic's rate limit, from the `X-RateLimit-*` headers;
- that a scheduled async upload is visible by `request_id` (status, then history) within seconds of the call.

The results go in the S2 build's report.
- If the 10-minute repeat returns the same job, `RECOVERY_WINDOW_S` becomes 600.
- If not, it stays 0 (no re-send) and crash recovery relies on the lookup and the fallback check (§6.3).
- If the third check fails (the upload is not visible within seconds), recovery's "no job" answer can't be trusted early. The 2-minute threshold for a row stuck in `claimed` (§6.3) is raised to the measured delay before S2b is built.

**S2b:**
1. Buy Upload-Post Basic (monthly). Create the profile `realtalk-clips-en`. Connect TikTok (set to public posting), Instagram (Professional, linked to the Facebook Page), YouTube and Facebook. Note the Facebook Page id.
2. Register the webhook URL `<API_URL>/webhooks/upload-post` for `upload_completed` and the three account events. Put `UPLOAD_POST_API_KEY` and `UPLOAD_POST_WEBHOOK_SECRET` in `clipforge-secrets` and `.env`. Deploy.
3. `clipforge account edit realtalk-clips-en --publisher-profile realtalk-clips-en --facebook-page-id <id>`, then `clipforge publisher check realtalk-clips-en`: read-only; it checks the profile, the connections, TikTok's allowed privacy levels and the webhook's reachability.
4. The next morning: approve one item in the 09:00 batch. Watch it post at its slot, then check `clipforge status`, the item's `posts` rows, its `post_events`, and that `posting verify` still reports 0.
5. Run a day on Hands-on. Test the brake with one item scheduled (`/pause realtalk-clips-en` cancels it; `/go` brings it back).

**S2c:**
1. Before the build: O3 (the handles, already warmed up per runbook §6).
2. `clipforge account create` for `founder-tapes-en` and `hombre-en-construccion-es`; they start Hands-on.
3. **One permitted source each** (`clipforge source add` with its permission record), with at least one episode clipped (`clipforge clip`), so each has a queue before its profile connects.
4. One Upload-Post profile each (3 of Basic's 5), connected as in S2b, then `account edit` and `publisher check`.
5. **Exit (04's S2 exit, restated in S3 §8.6):**
   - realtalk auto-posts to its 4 platforms from its profile on its rung;
   - founder.tapes and hombre start Hands-on on S2's flow;
   - every post and click is recorded (`posts`, `post_events`, `clicks`);
   - a gate failure lands in review;
   - the daily digest arrives.

**Rollback:**
- **One account, S2b or S2c:** `clipforge account edit <id> --clear-publisher`. It:
  - cancels the account's scheduled Upload-Post jobs (as the brake does, §6.7);
  - leaves in-flight items excluded from the assisted pick until reconcile resolves them (§3.1);
  - rewrites the schedule copy, so the account is back on the assisted path at the next slot.
- **S2a:** a revert deploy only. 0002 is expand-only, so the S1 code runs on it. Readers treat a missing autopilot row as Hands-on. `STATE_READS` doesn't change; ADR-41's own rollback stays separate.

## 10. Coverage of 04's S2 list

| 04's S2 item | Here |
|---|---|
| `Publisher` protocol, `UploadPostPublisher`, `AssistedPublisher` | §2, §6.2–§6.6 |
| Media by signed per-file Volume links | §6.1 |
| Signed webhook updates `posts`; per-platform AI disclosure | §6.4, §6.2 |
| Review tiers; Telegram cards only for items due within 2 h; copy fixes only in the dashboard | §5.2, §5.3, §7.1 (with Q3's morning-batch bridge) |
| Notification policy, the 09:00 digest, quiet hours, deduped alerts | §7.2, §7.3 (`ops.py` reused) |
| The brake survives a Neon outage and cancels scheduled posts | §6.7 |
| One claim per (item, platform); the fallback only after the final failure | §6.2, §6.3, §6.6 |
| Policy gate v1 | §5.1 |
| Tracking links | §7.4 |
| Autopilot (table, history, dial, Publish switch, presets, ladder, demotions, spot-check floor) | §5.4, §5.5, §5.2, §3 |
| Review windows (format 10, producer version 5, dubs 10) | §5.2 |
| The brake's scope (`/pause <account>`, `/pause all`) | §6.7 |
| One-tap only for due-soon reviews and the brake; Open → `/act` elsewhere | §7.1, §7.3 |
| Publishing-failure rows as instant alerts and "needs me" data | §7.3 |
| The dispatcher replaces `posting_tick`; the digest and alert fold; 3 crons | §4 |
| Migrations: the landing-order rule; the deferred items in the first migration | §3 |

## 11. Proposed changes to other documents (for the coordinator)

### 11.1 ADR-27, acceptance text (into `docs/DECISIONS.md`; 05 keeps a pointer)

> ## ADR-27: One dispatcher cron
> Date: 2026-09-29 · Status: Accepted (2026-10-01, card 011's S2 design; ruling #434; built in S2)
> Context: Modal Starter allows 5 deployed crons; three are used (`sweeper`, `posting_tick`, `posting_daily`). S2 adds the 09:00 digest, publish reconcile and per-slot review and hand-off phases; S6, S7 and S3b add the queue filler, the analytics pull, program checks and a weekly report.
> Decision: One `dispatcher` function runs every 5 minutes, replacing `posting_tick`, and runs each periodic task when it is due. Every tick first folds the ops alerts held over quiet hours or the hourly cap into one message (ADR-45's alert fold, moved from `posting_tick`). A task declares `due(now)` from Dict state only (the brake, the outage flag, the schedule copies, last-run markers) and `run(key)` within a time budget; slow work is spawned. Each due key is claimed set-if-absent (`dispatch:<task>:<key>`) and released on failure, which raises an ops alert. Postgres is opened only when a task is due, so Neon can scale to zero between due times. Planning and the digest run in the owner's time zone for every account. `sweeper` and `posting_daily` stay as they are: 3 crons.
> Consequences: Adding a periodic task needs no new cron. One slow task can't delay the others beyond its budget. The per-slot phases (plan at 08:50 owner time, review card at S − 2 h, hand-off at S − 30 min) wake Neon about 13 times a day per account.

### 11.2 ADR-33, acceptance text: tracking links only (R4)

> ## ADR-33: Tracking links
> Date: 2026-09-29 · Status: Accepted (2026-10-01, card 011's S2 design; built in S2). Conversion import, part of the 2026-09-29 draft, moved to draft ADR-51
> Context: Affiliate and bio-link money needs attribution per account, per platform and later per video, and a single link in a bio can't provide it. Vercel Hobby forbids affiliate use, so the redirect can't live on the dashboard's host.
> Decision: `GET /go/<slug>` on the Modal web app looks up a `links` row (slug, target, account, optional item and platform, kind `bio`, `campaign` or `affiliate`, the program's sub-id parameter) and answers 302 to the target with a sub-id `<account>.<item or bio>.<platform>`. Before redirecting it logs a click (slug, time, platform from a validated `?p=`, sub-id, and a coarse country only if a request header carries one; never the IP address or user agent); logging is best-effort and never blocks the redirect. When copy is frozen for publishing, the account's bio link and any affiliate link are replaced by their tracked link with a per-platform `p`; a campaign's required links stay verbatim, because campaign programs attribute on their own links. Slugs are 8 random base62 characters.
> Consequences: Clicks per account and platform from S2, per item from S8's offers. Every click opens the database (a lookup and an insert), so a busy link keeps Neon awake while clicks arrive; cache the links in the Dict if that ever costs. No personal data is kept about the person clicking. Revenue per video needs conversions, which ADR-51 adds in S7.

### 11.3 Draft ADR-51 for 05 (conversion import, R4)

> ## ADR-51: Conversion import
> Date: 2026-10-01 · Status: Proposed (split from ADR-33 on 2026-10-01; build in S7)
> Context: ADR-33's tracking links count clicks; money per video and per account also needs the sales those clicks produced.
> Decision: Import conversions from programs with APIs (ClickBank, Hotmart) on a daily dispatcher task, and from CSV uploads otherwise (Skool, Amazon, TikTok Shop), matching each sale to a link by its sub-id. Store them in a `conversions` table with the program, amount, currency, time and sub-id.
> Consequences: Revenue per video and per account in the dashboard, which is the "scale the winners" loop; the per-program importers are maintained as the programs change.

### 11.4 04 (roadmap), S2

- Split the list into **S2a** (migration with the deferred items, the dispatcher, the brake, autopilot on Hands-on, the gate and routing; assisted flow unchanged), **S2b** (the publisher, media links, the webhook, reconcile and crash recovery, the slot plan, review cards and hand-off, the fallback; realtalk on Upload-Post) and **S2c** (the dial, spot checks, the ladder and demotions, the digest, failure rows, tracking links; founder.tapes and hombre launch, one permitted source each). Each sub-step is one PR or more, deployable alone.
- Note under S2b: its build starts after one real Upload-Post call confirms key retention and Basic's rate limit (R5).
- Note the morning-batch bridge (`REVIEW_BATCH`, exempt from the hourly cap, R1) under the "Telegram review cards only for items due within 2 h" item.
- Strikes: entered by hand (CLI in S2, S3's form later); Upload-Post documents no strike event.
- S7: conversion import is draft ADR-51.
- The exit is unchanged.

### 11.5 06 (session prompts), the S2 card

- **Owner:**
  - Upload-Post **Basic** (O4), not Professional; upgrade at the 6th account.
  - The Facebook Page id per account.
  - Register the webhook URL; `UPLOAD_POST_API_KEY` and `UPLOAD_POST_WEBHOOK_SECRET`.
  - TikTok accounts set to allow public posts.
  - One permitted source each for founder.tapes and hombre.
  - A Whop account only if a campaign source is planned.
  - The R5 test call, with the session.
- **Actions:** replace 1–8 with the plan's tasks, by sub-step (S2a, S2b, S2c).
- **Depends:** S1's rollout (card 010) with Dual writes on, ADR-27 accepted (§11.1), ADR-33 accepted as tracking links (§11.2).
- **Cost:** $5 plus real posts (unchanged).

### 11.6 08 §2b and §2c

- Review cards use `r:` callbacks; posting cards keep `p:`.
- The **09:00 morning batch** is a bridge (Q3), behind `REVIEW_BATCH`, exempt from the hourly cap and paced (R1), until S3's Review page ships; then only the 2 h cards remain (#427).
- The **digest's content** (§7.2, with the attention arithmetic) replaces "digest at 09:00" as the description. Planning and the digest run in the owner's time zone (R3).
- **The brake:** `/pause` and `/go` take `<account>` or `all`, with a Dict key `brake:<scope>` mirrored to `posting_state`, and cancel posts already scheduled at Upload-Post.
- **The "Telegram after S2" paragraph:** the ✅ taps stay for accounts on the assisted path (Publish off, or no connected profile) and for the fallback's failed platforms. A ✅ means "posted", never "reviewed" (R2).

### 11.7 The owner runbook (11)

- **§2 (every day):** the 09:00 digest and review cards replace "answer the clip at each slot" for accounts on Upload-Post.
- **§6 (S2):** Basic, not "a paid plan"; the exact secret names; the webhook registration; the Facebook Page id; the R5 test call; `clipforge publisher check`. Then the S2a/S2b/S2c rollout steps of §9, with real account ids.
- **New "Brake" section:**
  - `/pause <account>`, `/pause all` and `/go`;
  - what a brake cancels;
  - what "recorded in the brake only" means;
  - how to check (`clipforge status`).
- **New commands** in the command list: `clipforge autopilot show|set|promote|strike`, `clipforge link add|list`, `clipforge publisher check`, `clipforge account edit --publisher-profile/--facebook-page-id/--clear-publisher`.

### 11.8 Decision log and STATUS

- O4 closes (#440: Basic now, Professional at the 6th account).
- STATUS's S2 row: "designed (card 011)", continuing at the S2 build card after the rollout and R5's call.
- ARCHITECTURE.md is updated by the build card, not now.
