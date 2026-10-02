# Studio S2: publishing and autopilot (design)

Date: 2026-10-01 · Card: [011](../../cards/011-s2-design.md) · Status: §1–§9 approved by the owner section by section at checkpoint A (2026-10-01); decision log #440–#452. For the owner's review as a whole before the plan (checkpoint B).

**What S2 is.** S2 is the step that replaces the owner's hand posting with publishing through Upload-Post, reviewed where it pays off. founder.tapes and hombre.en.construccion launch on it (ADR-48, #428). [04's S2 list](../../studio/04-roadmap.md) is the source. Every item in that list maps to a section here (§10).

**What it builds on, without reopening:**
- ADR-13: signed links.
- ADR-14: one writer per key.
- ADR-23: queue status rules.
- ADR-26 and ADR-41: Postgres as the store, with `STATE_READS` for rollback.
- ADR-28: Upload-Post behind a `Publisher` protocol.
- ADR-29: review tiers and the gate.
- ADR-43: the derived `producer_version`.
- ADR-44 and ADR-45: one home per task; the notification budget.
- ADR-46: the daily reconcile.
- ADR-48 and ADR-49: autopilot; the producer-version window.
- The [S3 dashboard spec](2026-10-01-studio-s3-dashboard-design.md) §2, §4, §7.11, §8.1, §8.4, §8.6 and §8.7.
- 08 §2b and §2c.

**The code it starts from:** S1 as merged (`alembic/versions/0001`, `db/`, `posting/`, `bot/posting.py`, `ops.py`, `app.py`). Card 010's rollout is assumed finished before S2's build, so production runs with `STATE_READS=postgres`.

**Upload-Post facts.** These were checked on 2026-10-01 in the official docs: [upload-video](https://docs.upload-post.com/api/upload-video), [schedule-posts](https://docs.upload-post.com/api/schedule-posts), [upload-status](https://docs.upload-post.com/api/upload-status), [webhooks](https://docs.upload-post.com/api/webhooks), [user-profiles](https://docs.upload-post.com/api/user-profiles), [pricing-and-limits](https://docs.upload-post.com/resources/pricing-and-limits) and [rate-limits](https://docs.upload-post.com/guides/rate-limits). The ones the design depends on:
- **Upload:** `POST /api/upload` with `Authorization: Apikey <key>`. The `video` field may be a URL. Fields:
  - `user` (the profile) and `platform[]`;
  - per-platform titles and descriptions (`tiktok_title`, `instagram_title`, `youtube_title`/`youtube_description`, `facebook_title`/`facebook_description`);
  - `facebook_page_id`, required for Facebook;
  - the AI flags `is_aigc`, `is_ai_generated` (Instagram), `containsSyntheticMedia` and `facebook_is_ai_generated`;
  - `scheduled_date` with `timezone`, `async_upload`, `request_id` and `Idempotency-Key` (a repeated key returns the existing job);
  - `disable_inbox_fallback`. Without it, TikTok can put the post in drafts and still report success.
- **Scheduled posts:** list with `GET /api/uploadposts/schedule?profile_username=`; cancel with `DELETE /api/uploadposts/schedule/<job_id>`.
- **Status:** `GET /api/uploadposts/status?request_id=|job_id=`, with per-platform states. History: `GET /api/uploadposts/history`, with `platform_post_id`, `post_url` and `error_message`.
- **Webhooks:**
  - Events: `upload_completed` (one per platform, success or failure), `social_account_disconnected`, `social_account_reauth_required` and `social_account_connected`.
  - Signature: `X-Upload-Post-Signature: sha256=<hex>` over `"<X-Upload-Post-Timestamp>.<raw body>"`. Deliveries older than 5 minutes are rejected.
  - De-duplication: `X-Upload-Post-Delivery` is unique per delivery.
  - Payloads carry `job_id` but not `request_id`.
  - After 5 failed deliveries the channel pauses for 30 minutes, and deliveries skipped then are never retried.
  - **No strike or takedown event is documented.**
- **Profiles:** one profile = one account across platforms. Basic is $24/month for 5 profiles; Professional is $50 for 25.
- **Hard caps per connected account per 24 h:** TikTok 15, Instagram 50, YouTube 10, Facebook 25 (429 when exceeded).

## 0. Decisions taken in the brainstorm

| # | Question | Answer (owner, 2026-10-01) |
|---|---|---|
| Q1 | O4, the Upload-Post plan | **Basic ($24, 5 profiles) now; upgrade to Professional when the 6th account is created** (S8). One profile per account, on all four platforms. Monthly until S2 proves out, then yearly |
| Q2 | Order inside S2 | **Rails first, then the publisher:** S2a (rails, assisted flow unchanged), S2b (Upload-Post for realtalk on Hands-on), S2c (the rest of autopilot, digest, links, the two launches). §1 |
| Q3 | The review lane before S3's Review page | **A morning batch, then 2 h cards:** at 09:00 one review card per item planned for the next 24 h; anything undecided gets its card 2 h before its slot. A bridge behind `REVIEW_BATCH=on`, an exception to #427 that ends when S3's Review page ships. §7 |
| Q4 | The digest | **One message at 09:00, then the cards.** Anomalies first; lines with nothing to say are left out. §7 |
| Q5 | Accounts with Publish off | **Today's assisted flow, where sending is the review.** The gate still holds failing items. The fallback reuses the same card for the failed platforms only. §6 |
| Q6 | When an approved item goes to Upload-Post | **30 minutes before its slot,** with `scheduled_date = slot`. A late approval goes at once. §4, §6 |
| Q7 | Where publishing state lives | **Approach A: on the `posts` rows** (one per item × platform), with the claim as a conditional update. A separate `publications` table (B) and Dict state (C) were rejected. §3 |

## 1. Shape and build order

S2 ships as three steps. Each is deployable and usable on its own.

**S2a: rails.** Production behaves exactly as today, on the dispatcher.
- Migration 0002 (§3), including the deferred items of S3 §8.7.
- The dispatcher replaces `posting_tick` (§4) and takes over the ops-alert flush.
- The brake: Dict keys `brake:<scope>` (§6.6), through `posting/actions.py`.
- The autopilot service with every account on Hands-on (§5.5).
- The policy gate v1 (§5.1) and the routing and window computation (§5.2). They are computed but not used yet: with no connected profile, every account stays assisted (§1.1).
- The `clipforge autopilot` CLI and its admin API routes.

**S2b: publishing for realtalk.**
- The `Publisher` protocol, `UploadPostPublisher` and `AssistedPublisher` (§6).
- Media links, the webhook and the publish reconcile.
- The slot plan, the review cards (the 09:00 batch and the 2 h cards), hand-off 30 minutes before the slot, the claim, and the fallback for failed platforms only.
- `clipforge publisher check`.
- **Exit:** realtalk publishes through Upload-Post on Hands-on, with every item approved by the owner in Telegram.

**S2c: autopilot and measurement.**
- The `sample` and `auto` dials, spot checks, the ladder (suggest, then the owner promotes) and automatic demotions (§5).
- The 09:00 digest (§7.2), the `publish_failed` and `publisher_disconnected` rows and alerts (§7.3), and tracking links (§7.4).
- founder.tapes and hombre are created (O3), their profiles connected, and they start Hands-on.
- **Exit:** 04's S2 exit (§9).

### 1.1 What "Publish on" means before a profile is connected

ADR-48's presets all have Publish on, and controls never block each other: each says what it waits on.
- An account whose `accounts.publisher` is empty shows **"Publish: on, waiting for a connected profile"** and runs the assisted flow (§6.5).
- Connecting the profile is an explicit owner step (§9). That step turns publishing on for that account.
- Publish **off** is an override that keeps the assisted flow even when a profile is connected.

### 1.2 New modules (all Modal-free; `app.py` stays the only Modal importer)

| Module | Holds |
|---|---|
| `publishing/protocol.py` | `Publisher` protocol and the request/receipt contracts' helpers |
| `publishing/upload_post.py` | `UploadPostPublisher` over httpx (no SDK, so one fake transport tests it) |
| `publishing/assisted.py` | `AssistedPublisher`: wraps today's `bot/posting.py` delivery for a platform subset |
| `publishing/media.py` | signed per-item media links |
| `publishing/handoff.py` | the claim, publish, record sequence and the state machine (§6.2) |
| `publishing/webhook.py` | signature check, delivery idempotency, event handling |
| `publishing/reconcile.py` | status and history polling for rows stuck in `scheduled`/`claimed` |
| `review/routing.py` | pure routing: gate, sponsored, windows, dial, spot checks |
| `review/service.py` | approve and reject, with an actor (the S3 routes call it too) |
| `review/cards.py` | Telegram review cards and their callbacks (`r:` prefix) |
| `policy/gate.py` | the pure gate |
| `accounts/autopilot.py` | the `autopilot` table's one writer, presets, history |
| `accounts/ladder.py` | pure ladder criteria over counted stats |
| `dispatch/tasks.py`, `dispatch/plan.py`, `dispatch/digest.py` | the task registry and markers, the slot planner, the digest |
| `tracking.py` | tracking links and click logging (`links.py` stays the zip-link module) |

`app.py` changes:
- the `dispatcher` cron replaces `posting_tick`;
- a spawned `dispatch_task(name, key)` function is added for slow tasks;
- `web` gains `POST /webhooks/upload-post`, `GET /media/{item_id}.mp4` and `GET /go/{slug}`, plus admin routes for autopilot, links and review decisions (bearer token).

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
    monthly_cap_usd: float                # per type, S3 §2.6
    updated_by: str
    updated_at: datetime

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

PublishState = Literal["pending", "claimed", "scheduled", "published", "failed",
                       "fallback", "cancelled"]

class PublishRequest(Contract):
    item_id: str; profile: str; platforms: list[Platform]
    media_url: str; copy: dict[Platform, PostCopy]
    scheduled_for: datetime | None; timezone: str
    ai_disclosure: bool; sponsored: bool
    facebook_page_id: str | None; idempotency_key: str

class PublishReceipt(Contract):
    job_id: str | None; request_id: str
    accepted: list[Platform]; rejected: dict[Platform, str]   # platform -> error code

class PlatformResult(Contract):
    platform: Platform
    state: Literal["pending", "published", "failed", "retryable"]
    post_id: str | None = None; url: str | None = None; error: str | None = None

class Publisher(Protocol):
    def publish(self, req: PublishRequest) -> PublishReceipt: ...
    def status(self, *, job_id: str | None = None,
               request_id: str | None = None) -> list[PlatformResult]: ...
    def cancel(self, job_id: str) -> bool: ...
    def scheduled(self, profile: str) -> list[str]: ...   # job ids, for the brake without Neon

class SlotPlan(Contract):
    account_id: str; slot: datetime; item_id: str | None
    state: Literal["planned", "approved", "handed_off", "done", "empty", "missed"]

class Brake(Contract):
    scope: str                            # "all" or an account id
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
- `PostStatus` derivation in `posting/queue.py` doesn't change. `posted_at` stays the only "posted" fact, so an Upload-Post success and a ✅ tap mean the same thing.
- The actor format (`posting/actions.ACTOR`) gains `system:[a-z][a-z-]{0,39}`. That form is for changes nobody tapped: `system:autopilot` (auto-lane approval), `system:demotion`, `system:upload-post` (webhook results) and `system:migration` (the seed rows).
- Promotions carry the owner's actor (S3 §8.4).

## 3. Data: migration 0002

One expand-only migration. Its number is the next after the head on `main`: 0002 if S2 lands first. If the hooks card's or S3c's migration lands first, S2 takes the next number and drops the deferred items that migration already carries (S3 §8.7). The same change moves `EXPECTED_HEAD` in `db/doctor.py`.

**The deferred items (S3 §8.7):**
- `jobs.error text NULL`.
- `post_events.actor text NULL`, with a check constraint for the actor format (including `system:`, at most 80 characters), backfilled from `data->>'actor'`. From then on, `db/posting._event` writes the column. `data.actor` stays for old rows only.
- `posting_state.changed_by text NULL` and `posting_state.reason text NULL`. `actions.pause` writes them.

**New columns:**

| Table | Columns | One writer |
|---|---|---|
| `accounts` | `publisher jsonb NULL` (`PublisherProfile`) | the accounts service (edit) and the webhook (only the `disconnected` map, through the same service) |
| `content_items` | `copy jsonb NULL`, `review_lane text NULL`, `review_reasons jsonb NULL`, `review_dial text NULL`, `review_window text NULL`, `gate jsonb NULL`, `approved_at timestamptz NULL`, `approved_by text NULL` | `copy`: S3's copy edit. The rest: `review/service.py` (routing at plan time; approval). Rejection keeps using the existing `verdict_*` columns through `posting/actions.py` |
| `posts` | `publisher text NULL` (`upload_post`, `assisted`), `state text NOT NULL DEFAULT 'pending'`, `claimed_at`, `scheduled_for`, `handed_off_at timestamptz NULL`, `request_id text NULL`, `upload_job_id text NULL`, `post_id text NULL`, `attempts int NOT NULL DEFAULT 0`, `error text NULL`, `copy jsonb NULL` (frozen at hand-off); indexes `(state, scheduled_for)` and `(upload_job_id)` | `publishing/handoff.py`, `publishing/webhook.py`, `publishing/reconcile.py`, through forward-only conditional updates (§6.2). The existing `posted_at` and `url` keep their meaning |

`accounts.review_tier` stays, but nothing reads it after S2: `autopilot.review_dial` is the source (ADR-48). S3c's spec already moves the tier out of its "rules" class.

**New tables:**
- `autopilot(account_id PK FK, preset, produce, review_dial, publish, scale, runway_days, batch_line_usd, monthly_cap_usd, updated_by, updated_at)`.
  - The migration seeds one row per existing account: Hands-on, actor `system:migration`.
  - Account create inserts the row in the same transaction.
- `autopilot_events(id identity, account_id, at, actor, field, from_value, to_value, reason)`, append-only: a trigger rejects UPDATE and DELETE, like S3c's `*_versions`.
- `slot_plans(account_id, slot timestamptz, item_id NULL FK, state, planned_at, updated_at)`, primary key `(account_id, slot)`. The one writer is `dispatch/plan.py` and the hand-off step.
- `review_messages(item_id, chat_id, message_id, video_message_id, at, kind)`, with primary key `(chat_id, message_id)`.
  - Every review card and every fallback card is recorded here, so a decision on any surface redraws all of them.
  - Today's `sends` table can't hold them: a `sends` row makes the item's derived status `sent`.
- `webhook_deliveries(delivery_id PK, event, received_at, payload jsonb, processed_at NULL)`. Insert-if-absent is the replay guard. Kept 30 days, pruned by `posting_daily`.
- `links(slug PK, target_url, account_id FK, item_id NULL, platform NULL, kind, sub_param, created_at, created_by)` and `clicks(id identity, slug FK, at, platform NULL, sub_id, country NULL)`, indexed on `(slug, at)`. No IP address or user agent is stored.

**Modes.** S2's tables, columns and services are Postgres-only. With `STATE_READS=dict` (the rollback), the dispatcher runs today's assisted tick for account #1 and nothing else, so a rollback still works.
- `posting verify` keeps comparing only the legacy fields; the Dict never learns publish state.
- When S1's Task 23 retires the Dict writes, nothing in S2 changes.

## 4. The dispatcher (ADR-27) and the slot plan

### 4.1 The cron

`dispatcher` runs every 5 minutes (`*/5`, the same slot as `posting_tick`) and replaces it. That keeps 3 crons: `sweeper`, `dispatcher` and `posting_daily`. Each tick:
1. `ops.flush(now)`: held alerts, as the old tick did.
2. Reads **only the Dict**: `brake:*`, `posting:outage`, the `posting:schedule:*` copies (which gain the account's Publish mode and profile, §6.6) and the task markers.
3. Works out what is due from those reads alone. **Postgres is opened only when a task is due**, so Neon can still scale to zero between due times.
4. Runs each due task within its budget. A slow task (the morning batch of review cards, the digest) is spawned as `dispatch_task(name, key)`, and the tick moves on.

A task is `Task(name, due(now, schedules, markers) -> list[key], run(ctx, key), budget_s)`, registered in `dispatch/tasks.py`. A due key is claimed set-if-absent as `dispatch:<name>:<key>` before it runs, so overlapping ticks run it once. A run that raises releases its claim, so the next tick retries it, and raises an ops alert (kind `dispatch`, subject the task name).

### 4.2 Per-slot phases (accounts publishing through Upload-Post)

For each slot S of an account whose schedule copy says Upload-Post:

| Phase | Due | What it does |
|---|---|---|
| `plan` | daily at 08:50 in the account's time zone (key `<account>:<date>`) | Assigns the slots of the next 24 h that have no plan. Picks with `queue.pick_next` repeatedly, skipping items already planned and held items. Routes each item (§5.2) and stamps the routing on it. Auto-lane items are approved by `system:autopilot`. Writes `slot_plans` (`planned` or `approved`; `empty` if nothing is eligible) |
| `card` | S − 2 h | If the slot's item is unapproved and has no 2 h card yet: send its review card. If the slot is `empty`, or its item was rejected: plan a replacement now (a review-lane replacement gets its card at once) |
| `handoff` | S − 30 min | If the item is approved: hand it off with `scheduled_date = S` (§6.2) and move the slot to `handed_off`. If not: substitute an approved, unplanned item (there are any only on `sample`/`auto`); otherwise mark the slot `missed` and leave the item in the lane, planned first next time |

- **A late approval,** between S − 30 min and S + 30 min (today's `SLOT_WINDOW`), hands off at once with no `scheduled_date`. After S + 30 min the slot is `missed`, and the approved item leads the next plan.
- **An account on the assisted path** (Publish off, or no connected profile) runs today's `_tick_account` at S, unchanged: the pause rule (`PAUSE_AFTER`), the outage guard, the #202 slot guard and the claim. It has no plan and no review cards: sending is the review (Q5).
- **The gate still runs on the assisted path:** an item with violations is held, never sent, and shows in the digest.

### 4.3 Fleet tasks

| Task | Due | Notes |
|---|---|---|
| `digest` | 09:00 in the owner's time zone (`digest:<date>`) | Spawned. Sends the digest (§7.2), then the review cards for the undecided review-lane items planned for the next 24 h (§7.1) |
| `publish_reconcile` | every 15 min while the Dict marker `publish:inflight` is set; once a day regardless | Hand-off sets the marker; reconcile clears it when no `posts` row is `claimed` or `scheduled`. It polls Upload-Post status for rows still `scheduled` 10 min after their slot, and re-publishes rows stuck in `claimed` with their stored key. The daily run also reads history for the last 2 days, catching webhook deliveries dropped during Upload-Post's 30-minute pauses |
| alert fold | every tick | `ops.flush`, moved from the tick |
| (later) queue filler, analytics pull, program checks, weekly report | daily/weekly | S6, S7 and S3b register their tasks here; no new cron |

### 4.4 Never sending a slot twice (the #202 guard, extended)

Four independent guards, each enough alone:
1. `slot_plans` primary key `(account_id, slot)`: one plan per slot.
2. Hand-off moves the slot `approved → handed_off` with a conditional update; a second runner finds nothing to move.
3. Each platform is claimed `publisher IS NULL → 'upload_post'` (§6.2).
4. The idempotency key `<item_id>:<platforms>:<attempt>` is sent as `Idempotency-Key` and `request_id`, so a repeated call returns Upload-Post's existing job.

A lost or renamed Dict claim, a retried tick, a redeploy mid-hand-off, or a crash between the HTTP call and recording its receipt can therefore never post twice. The runbook's deploy blackout (#108) stays as it is: these guards make it unnecessary for the Upload-Post path, and it is retired with the assisted path's guard, not here.

**Load on Neon:** about 3 wake-ups per slot plus one plan a day. At 4 slots that's about 13 wake-ups per account per day, plus about one webhook per post.

## 5. Routing, the gate, windows and the ladder

### 5.1 The policy gate v1 (`policy/gate.py`, pure)

`gate(item, account, source, copy, others) -> GateResult`. It runs at plan time and again at hand-off, so a copy edit or a permission change in between is caught. `others` holds the planned and posted items of other accounts that share the item's `source_hash`, read by the caller.

| Code | Fails when |
|---|---|
| `missing_ai_label` | an asset is `generated` or `music_generated` and `item.ai_disclosure` is false (the publisher maps the flag to every platform's field, §6.3) |
| `missing_ad` | the item is sponsored and a platform's copy lacks `#ad` |
| `missing_credit` | the blueprint's compliance profile has `require_credit`, or the source is a `channel`, and a platform's copy doesn't name `source.credit_name` |
| `license_unrecorded` | an asset has no license. A `source_video` asset is checked against the source's **current** permission, not its stamped string, so items imported from the Dict (stamped `unrecorded`) pass when their source has a recorded permission |
| `cross_account_duplicate` | another account has planned or posted a clip of the same `source_hash` with IoU > 0.5 |
| `source_held` | `sources.hold_reason` holds the item (an expired or narrowed permission); the item isn't planned at all, as today |

The gate never edits anything. Any violation sends the item to the review lane, and the card shows each violation in plain words. The banned-claims check comes with the Judge in S6.

### 5.2 Routing (`review/routing.py`, pure)

`route(item, autopilot, gate_result, window_counts, spot_state, account_age) -> Routing` records **every** reason that applies; any one reason sends the item to `review`.
1. **gate:** at least one violation.
2. **sponsored:** a sponsored item in the account's first 30 days (counted from its first post). Brand-deal items go to review always, once S13 adds that flag.
3. **Windows** (ADR-48, ADR-49). Each counts items of the account **decided by a person**: approved or rejected by an actor that isn't `system:`.
   - `producer_window`: fewer than 5 decided items with the item's `producer_version`. Legacy `plan-c` items count as their own version.
   - `format_window`: the item was made under an account version with `format_changed`, and fewer than 10 decided items exist under it. This reads S3c's `account_versions`; until that table exists, the window is always closed.
   - `dub_window`: `parent_item_id` belongs to the account's paired account, and fewer than 10 dubs in the pair have been decided (S10 produces dubs; the rule is built and tested now).
4. **dial:** `review` sends every item to review; `auto` sends none. On `sample`, an item is a **spot check** when either:
   - 9 or more auto-routed items have passed since the account's last spot check; or
   - fewer than 3 spot checks fall in the last 7 days, and the last one was at least 24 h ago.

   This is deterministic, so tests can replay it, and it gives at least 1 in 10 and at least 3 a week (S3 §2.4).

The stamp on the item (`review_lane`, `review_reasons`, `review_dial`, `review_window`, `gate`) plus a `routed` `post_events` row make every result attributable (S3 §8.4: the dial and window in force).

### 5.3 The review service (`review/service.py`)

- `approve(ref, actor, now)`: sets `approved_at` and `approved_by`, writes an `approved` event, moves the item's planned slot to `approved`, redraws every card. A late approval hands off at once (§4.2).
- `reject(ref, reason | None, actor, now)`: the existing `posting/actions.reject` and `set_reason` (the same verdict columns), then frees the item's slot for replanning and redraws every card. If the item was a spot check, demotion is checked inline (§5.5).
- Both refuse an item already decided, and return who decided it and when: "Approved by telegram:… at 09:04" (S3 §7.2).
- Both are wrapped like `posting/actions._store`: a database error answers "Store unavailable, nothing changed".
- Copy edits and re-renders are S3's (ADR-44). S2 exposes `PUT /admin/review/{item}/copy`, which writes `content_items.copy` through the same service, so S3 adds only the page.

### 5.4 The autopilot service (`accounts/autopilot.py`, the one writer)

- `get(account_id)` and `history(account_id)`.
- `set(account_id, field, value, actor, reason)` and `apply_preset(account_id, preset, actor, reason)`.
  - Each write updates `autopilot` and appends one `autopilot_events` row per changed field, in one transaction.
  - A single override turns the preset into `custom`, shown as "Hands-on, with Publish off".
- Moving the Review dial toward `auto` (`review → sample → auto`) requires a reason.
- `waiting_on(account_id) -> dict[str, str]` gives the one-line "waiting on" per control, e.g. "Publish: on, waiting for a connected profile", "Produce: off (the queue filler arrives in S6)", "Scale: no paired account".
- Produce and Scale are stored but have no effect until S6 (the filler) and S10 (dubs).

### 5.5 The ladder and demotions (`accounts/ladder.py`, pure over counted stats)

| Move | Criteria |
|---|---|
| Hands-on → Supervised | ≥ 30 days since the first post, ≥ 50 approved items, < 10% rejected among the last 50 decided, no gate failure in 14 days |
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
- **Serving:** it serves the item's `video_path` with range support, after `jobs.is_job_id`-style validation of the item id and a check that the resolved path stays inside `/jobs`.
- **Errors:** a missing key answers 503; a bad or expired signature answers 403; a missing file answers 404. Media is never served without a signature.

### 6.2 The state machine (`publishing/handoff.py`)

Per `posts` row (item × platform). Every move is a forward-only conditional update with a `post_events` row in the same transaction.

```
pending ─claim─► claimed ─publish accepted─► scheduled ─webhook / poll ok─► published
   ▲               │  └─ retryable error, attempts < 3: re-publish with the same key ─┘
   │               └─ final failure ─► failed ─fallback claim─► fallback ─ ✅ tap ─► (posted_at set)
   └──── /go ◄──── cancelled ◄── brake ── scheduled
```

**Hand-off, for one approved item:**
1. Re-check the brake (the Dict) and re-run the gate. A violation un-approves the item (back to the lane, reason `gate`), and its slot goes to the substitute rule (§4.2).
2. **Claim** the item's platforms that aren't disconnected, in one transaction:
   ```sql
   UPDATE posts SET publisher='upload_post', state='claimed', claimed_at=:now,
       attempts=attempts+1, request_id=:key, copy=:frozen_copy
   WHERE item_id=:item AND platform = ANY(:platforms)
     AND (publisher IS NULL OR (publisher='upload_post' AND state='claimed'))
   RETURNING platform
   ```
   - The key is `<item_id>:<sorted platforms>:<attempt>`.
   - The copy is frozen here: `item.copy` or `captions.py`, with tracked links (§7.4).
   - Disconnected platforms go straight to the fallback (§6.5).
3. **Commit, then call** `publisher.publish(...)` with the key as `Idempotency-Key` and `request_id`.
4. **Record the receipt:** accepted platforms move to `scheduled` (`upload_job_id`, `scheduled_for`, `handed_off_at`); rejected platforms move to `failed`. Set `publish:inflight` in the Dict.

**Crash safety.** If the container dies between steps 3 and 4, the row stays `claimed` with its key. Reconcile (§4.3) re-publishes with the same key, and Upload-Post returns the existing job.

**Final and retryable failures.**
- **Final:** a per-platform failure Upload-Post reports as final; validation errors (4xx other than 429); `tiktok_privacy_unavailable`; or no result 60 min after the slot (Upload-Post's own "failed after 1 h inactivity").
- **Retryable:** 429 (the per-day caps), 5xx, timeouts and Upload-Post's `retryable`. These retry at the next reconcile, at most 3 attempts in all, and then become final.

**The one claim per (item, platform).** Exactly two conditional updates move a row between publishers: the Upload-Post claim (from `publisher IS NULL`) and the fallback claim (from `upload_post` + `failed`, §6.5). The assisted path therefore runs only after Upload-Post's final failure, and the two can never both publish the same (item, platform).

### 6.3 The publish call (`publishing/upload_post.py`)

`POST /api/upload`, multipart, `Authorization: Apikey <UPLOAD_POST_API_KEY>`:
- `user=<profile>`, `video=<media link>`, `platform[]=…`, `async_upload=true`;
- `scheduled_date=<slot ISO>` and `timezone=<account tz>` (omitted for a late hand-off);
- per platform from the frozen copy: `tiktok_title`, `instagram_title`, `youtube_title` + `youtube_description`, `facebook_title` + `facebook_description`, plus `title` (required for YouTube);
- `facebook_page_id`;
- the AI flags from `ai_disclosure`: `is_aigc`, `is_ai_generated` (Instagram, TikTok, YouTube alias), `containsSyntheticMedia`, `facebook_is_ai_generated`;
- `disable_inbox_fallback=true`: a TikTok draft isn't a post, so it counts as a failure and goes to the fallback;
- `privacy_level` is omitted, so the account default applies. Connecting a profile includes checking that the TikTok account allows public posts (§9).

It uses httpx (timeouts 10 s connect, 30 s total) and logs only the host, the status and the item id: never the key, the signed media link or the response body (rule 8). `status`, `cancel` and `scheduled` map to `GET /api/uploadposts/status`, `DELETE /api/uploadposts/schedule/<job_id>` and `GET /api/uploadposts/schedule?profile_username=`.

### 6.4 The webhook (`publishing/webhook.py`, `POST /webhooks/upload-post` on `web`)

1. **Check the signature.** `UPLOAD_POST_WEBHOOK_SECRET` missing answers 503. It verifies `X-Upload-Post-Signature` (`sha256=` + HMAC-SHA256 of `"<X-Upload-Post-Timestamp>.<raw body>"`) with `hmac.compare_digest`, and that the timestamp is within 5 minutes; otherwise 401.
2. **Replay guard.** `INSERT INTO webhook_deliveries … ON CONFLICT DO NOTHING` on `X-Upload-Post-Delivery`. A repeat answers 200 and changes nothing.
3. **`upload_completed`:** find the row by `upload_job_id` and `platform`.
   - Success: `published`, with `posted_at`, `url` and `post_id`; actor `system:upload-post`.
   - Failure: `failed`, final or retryable as in §6.2.
   - An unknown job id answers 200 and is logged, so Upload-Post doesn't pause the channel.
4. **`social_account_disconnected` and `social_account_reauth_required`:** set `accounts.publisher.disconnected[platform]` through the accounts service and raise an instant `publisher_disconnected` alert (§7.3). **`social_account_connected`** clears it.
5. Set `processed_at` and answer 200, well within Upload-Post's 10 s limit (a few row writes and at most one alert).

Webhook deliveries lost while Upload-Post's channel is paused are recovered by `publish_reconcile` (§4.3), never by a replay.

### 6.5 Fallback and the assisted path (`publishing/assisted.py`)

`AssistedPublisher` wraps today's `bot/posting._deliver` with a platform subset. It is used in two ways:
- **Accounts on the assisted path** (Publish off, or no profile; Q5). This is today's flow at the slot, unchanged: the same `p:` callbacks, so old messages keep working. The gate holds violating items.
- **The fallback:** when a platform's row becomes final `failed`:
  1. The fallback claim moves the row `upload_post` + `failed` → `assisted` + `fallback`.
  2. An instant `publish_failed` alert goes out (§7.3).
  3. If the slot is still today and the account has a chat, the assisted card follows, listing **only the failed platforms**. It is recorded in `review_messages` (kind `fallback`), not in `sends`, so the item's derived status doesn't change.
  4. The ✅ tap sets `posted_at`, as today.

### 6.6 The brake

**Commands:** `/pause [account|all]` and `/go [account|all]`, through `posting/actions.pause`; the dashboard later uses the same function. With no argument, `/pause` is the whole fleet (as today's `/pause` pauses every account).

**`/pause`:**
1. **Write the Dict key `brake:<scope>`** (`Brake` JSON) first. That's the part that must survive a Neon outage.
2. **Then write `posting_state`** for each account in scope (`paused`, `changed_by`, `reason`). If Neon is down, the reply says "Paused. The database is unavailable, so this is recorded in the brake only", and `posting_daily` writes `posting_state` from the brake keys later.
3. **Effect:** every dispatcher phase skips a braked scope (`brake:all`, or `brake:<account>`), and hand-off checks again just before calling Upload-Post (§6.2 step 1).
4. **Cancel what's already scheduled.** `posts` rows in `scheduled` with `scheduled_for > now`, in scope, get `publisher.cancel(job_id)` and move to `cancelled`.
   - With Neon down, the job ids come from Upload-Post's own list (`publisher.scheduled(profile)`). The profile is in the account's Dict schedule copy, which S2 extends with `publish_via` and `profile`. Reconcile then fixes the rows.
   - Hand-off happens 30 min ahead, so there are at most a few posts per account to cancel.
5. **The reply counts the result:** "Paused realtalk: 1 scheduled post cancelled, 0 already out."

**`/go`:**
1. Deletes the key.
2. Moves `cancelled` rows back to `pending`. Their items lead the next plan; a slot whose time has passed is `missed`.
3. Clears `posting:outage` as today (#217).

**Expiry.** A brake key must never expire into "go". Every dispatcher tick reads every `brake:*` key with `get`, which counts as activity (ADR-24). `posting_daily` also restores a missing brake key from `posting_state` where it says paused.

The brake is one of the two one-tap actions Telegram keeps (#427).

## 7. Telegram, the digest, failure rows and tracking links

### 7.1 Review cards (`review/cards.py`)

- **The card:** the video, then a text: the account, the slot ("goes out 13:00, America/New_York"), the reasons in plain words ("producer window: 2 of 5", "spot check", each gate violation), and the copy per platform (read-only).
- **Buttons:** **✅ Approve** · **🗑 Reject**, then the reason row (`RejectReason`, as today). **Open ↗** to `/act/review/<item>` once S3 serves that page; before S3 the card has no Open button.
- **Callbacks:** `r:ok:<ref>`, `r:rej:<ref>`, `r:why:<reason>:<ref>`. The `p:` callbacks of the posting flow are unchanged, so every older message keeps working. Taps are accepted only from `TELEGRAM_ALLOWED_USER_IDS`, in the account's chat; actor `telegram:<user id>`.
- **After a decision on any surface,** every card of the item (`review_messages`) is redrawn: "Approved · telegram:… · 09:04 · out at 13:00", or "Rejected · Bad crop".
- **When cards are sent:**
  - **the 09:00 batch** (Q3): one card per undecided review-lane item planned for the next 24 h (the 08:50 plan's horizon, so tomorrow's early slots are covered today), sent after the digest. It is a bridge behind `REVIEW_BATCH=on` (default on), turned off when S3's Review page ships. It counts as one delivery, outside ADR-45's 20-an-hour cap;
  - **the 2 h card** (§4.2): for any review-lane item still undecided 2 h before its slot, or a replacement planned inside that window. These count as instant messages under ADR-45's limits.
- **No card is sent** for items due more than 2 h ahead outside the 09:00 batch. A 2 h card that falls in quiet hours (23:00–08:00) is not sent: its item already had a card in the batch, and if it is still undecided at hand-off, the slot takes the substitute or is missed (§4.2).

### 7.2 The 09:00 digest (`dispatch/digest.py`)

One message at 09:00 in the owner's time zone (`OWNER_TIMEZONE`, else the posting time zone), claimed `digest:<date>`. Lines with nothing to say are left out. An empty day is one line: "Nothing needs you today. Yesterday: 12 posted across 3 accounts."
1. **Anomalies first:** an outage (`posting:outage`), a brake that's on, a disconnected publisher, yesterday's final publish failures, the database unavailable at a tick.
2. **Yesterday, per account:** posted (of which automatic), failed, rejected; "ran without you" (auto-approved items, demotions, from `post_events` and `autopilot_events`).
3. **Today, per account:** slots, approved, need you; then "N review cards follow ↓".
4. **Digest-level rows (S3 §4):**
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
| `publish_failed` (subject `<item>:<platform>`) | hand-off, the webhook or reconcile, on a final failure | instant; **urgent** (through quiet hours) when final failures hit 2 or more accounts within an hour ("publishing broken across accounts", ADR-45) |
| `publisher_disconnected` (subject `<account>:<platform>`) | the webhook | instant |
| `strike` (subject `<account>:<platform>`) | `clipforge autopilot strike` (no webhook exists) | instant, with the automatic demotion |

- Each alert goes through `ops.alert` (dedup per kind, subject and hour; quiet hours; the cap) with `path="/act/<kind>/<subject>"` for S3's Open button.
- **The data is S2's:** `publishing.open_problems()` returns the rows that are failed or in fallback and not posted, the disconnected flags and the recorded strikes. **The "needs me" list is S3's:** `GET /needs` turns them into rows (S3 §8.3).

### 7.4 Tracking links (`tracking.py`; ADR-33's link half)

- **`GET /go/{slug}` on `web`,** public:
  1. Look up `links`; an unknown slug answers a plain 404.
  2. Write a `clicks` row with `platform` from `?p=`, `sub_id = <account>.<item or "bio">.<platform>`, and `country` only if the request carries a country header. This is best-effort: a failed write never blocks the redirect.
  3. Answer 302 to `target_url` with the sub-id in `sub_param`.

  No IP address or user agent is stored.
- **Slugs:** 8 random base62 characters (`secrets.choice`).
- **Creation:** `clipforge link add <account> <url> --kind bio|affiliate [--sub-param p]` and `POST /admin/links` (actor recorded).
- **Use in copy.**
  - When the copy is frozen at hand-off, an account's `brand.bio_link` and any affiliate link are replaced by `<API_URL>/go/<slug>?p=<platform>`, one link per account and link, with the per-platform `p`.
  - A campaign's `required_links` stay verbatim: campaign programs attribute on their own links.
  - For the clip accounts this is mostly the bio link. Per-item sub-ids matter from S8 (avatar offers).
- Conversions (ClickBank, Hotmart, CSV) stay in S7.

## 8. Tests and safety

Every item has its tests in the same task, written first. DB tests use the local Postgres, and fail, never skip, without it. Fast tests mock every network call.

| Area | Tests |
|---|---|
| Publisher contract | `FakePublisher` (scripted per-platform results, an idempotency map, a call log) for the hand-off and fallback tests. `UploadPostPublisher` against an httpx `MockTransport`, with golden request fields per platform (AI flags, `facebook_page_id`, `disable_inbox_fallback`, per-platform titles, `scheduled_date` and `timezone`, `Idempotency-Key`), and error mapping (429 and 5xx retryable; `tiktok_privacy_unavailable` final). No secret or signed URL in logs (a `caplog` check) |
| Gate | About 15 golden cases in EN and ES, `(item, account, source, copy) → violations`: AI asset without the flag, sponsored without `#ad` on one platform, missing credit, an `unrecorded` Dict item with and without a recorded source permission, a cross-account duplicate at IoU 0.4 and 0.6, an expired permission |
| Routing | One case per reason. Several reasons together. Windows count only decisions by people (a `system:autopilot` approval doesn't close a window). Spot checks over a 30-item sequence give ≥ 1 in 10 and ≥ 3 a week, the same picks on every run |
| Autopilot and ladder | Presets and overrides (`custom`); history rows per changed field; the trigger rejecting UPDATE and DELETE; a reason required toward `auto`. Ladder criteria from fixtures, at and just below each threshold. The second reject in the last 5 spot checks demotes inline (`system:demotion`). A strike drops to Hands-on |
| Claim per (item, platform) | Two connections race the claim and exactly one wins. The fallback claims only from `failed`. Upload-Post and the assisted path never both hold one row. A disconnected platform goes straight to the fallback |
| No double send (#202) | Overlapping ticks. A lost Dict claim. A renamed claim key (`dispatch:` prefix changed). A crash between `publish` and recording the receipt: reconcile re-publishes with the same key, and the fake returns the same job. A late approval racing the hand-off phase. The assisted path's existing guard tests keep passing |
| Dispatcher | `due()` from the Dict alone: a tick with nothing due runs against a database stub that fails if touched. Each phase at S − 2 h, S − 30 min and S. Planning skips held and already-planned items. Substitution and `missed`. A failed task releases its claim and alerts. Spawned tasks run once |
| Brake under a Neon outage | With the database raising `DatabaseUnavailable`: `/pause realtalk` and `/pause all` set the Dict key and reply honestly; the dispatcher skips the scope; cancel uses `publisher.scheduled(profile)`; `posting_daily` later writes `posting_state`; a missing key is restored from `posting_state`. `/go` moves `cancelled` rows to `pending` |
| Webhook | A valid delivery. The **same delivery replayed twice** (200, one event, one state change). A bad signature, a stale timestamp, a missing secret (503), an unknown job id (200, logged), the disconnect and connect events |
| Reconcile | A row `scheduled` past slot + 10 min is resolved by status. A dropped webhook is found through history. A row stuck in `claimed` is re-published with its key. `publish:inflight` is cleared when nothing is in flight |
| Media links | Signature and expiry. The `media:` prefix (a zip-link signature is refused, and the reverse). A path escaping `/jobs`. Range requests |
| Cards and digest | Golden texts. `r:` callback parsing (and `p:` unchanged). Redraw of every card on approve and reject from either surface. "Already decided" answers. The batch flag. The digest leaves out empty lines |
| Tracking links | The redirect with its sub-id. A failed click write still redirects. An unknown slug. Copy wrapping for bio and affiliate links, while campaign links stay verbatim |
| Migration | Up and down. An empty autogenerate diff. The `actor` backfill from `data.actor`. The seed rows. `EXPECTED_HEAD` moved |
| Cost | Hand-off and webhook record nothing per post. `Prices` gains the Upload-Post plan as a fixed subscription (shown on S3's Costs, never against caps) |

**Reviewers:**
- `migration-reviewer`: 0002 and the `posts` claim updates.
- `security-reviewer`: the webhook, media links, `/go`, the new secrets, and logs.
- `pr-reviewer`: before every merge.
- `pipeline-reviewer` isn't needed: no stage changes.

**Secrets:** `UPLOAD_POST_API_KEY` and `UPLOAD_POST_WEBHOOK_SECRET` (the `whsec_…` value), in `clipforge-secrets` and `.env`. Both are optional: without them, publishing is off with the reason in `/status` (like `Settings.posting_problem`), and the webhook answers 503.

**New settings:** `REVIEW_BATCH` (`on`/`off`, default `on`), `MEDIA_LINK_TTL_S` (default 86400) and `UPLOAD_POST_PROFILE_LIMIT` (default 5). Account create warns when the profiles in use would exceed `UPLOAD_POST_PROFILE_LIMIT` (O4: upgrade at the 6th).

**Cost:**
- **Upload-Post Basic** is $24/month, a fixed subscription.
- **Modal:** the same 5-minute cron as today, plus a few webhook, media and API calls a day, so variable cost is negligible.
- **Neon:** about 13 wake-ups per account per day plus about one webhook per post; it still scales to zero between them.
- **The build card's cap:** about $5 for smoke runs, plus a few real posts.

## 9. Rollout of S2 (owner steps; the plan and the runbook carry the exact commands)

**S2a**, after card 010 (`STATE_READS=postgres`, verified):
1. Deploy outside the posting slots (runbook §1). CI runs 0002.
2. For one day, check that `dispatcher:` log lines show the same sends as yesterday's `posting_tick:` lines, and that `db_doctor` reports the new head.
3. Test `/pause realtalk`, `/go`, `/pause all` and `/go` in Telegram, and `clipforge autopilot show realtalk`: Hands-on, "Publish: on, waiting for a connected profile".

Nothing else changes for the owner.

**S2b:**
1. Buy Upload-Post Basic (monthly). Create the profile `realtalk`. Connect TikTok (set to public posting), Instagram (Professional, linked to the Facebook Page), YouTube and Facebook. Note the Facebook Page id.
2. Register the webhook URL `<API_URL>/webhooks/upload-post` for `upload_completed` and the three account events. Put `UPLOAD_POST_API_KEY` and `UPLOAD_POST_WEBHOOK_SECRET` in `clipforge-secrets` and `.env`. Deploy.
3. `clipforge account edit realtalk --publisher-profile realtalk --facebook-page-id <id>`, then `clipforge publisher check realtalk`: read-only; it checks the profile, the connections, TikTok's allowed privacy levels and the webhook's reachability.
4. The next morning: approve one item in the 09:00 batch. Watch it post at its slot, then check `clipforge status`, the item's `posts` rows and its `post_events`.
5. Run a day on Hands-on. Test the brake with one item scheduled (`/pause realtalk` cancels it; `/go` brings it back).

**S2c:**
1. Before the build: O3 (the handles, already warmed up per runbook §6).
2. `clipforge account create` for founder.tapes and hombre.en.construccion; they start Hands-on. Then one Upload-Post profile each (3 of Basic's 5), connected as in S2b, and `account edit` and `publisher check`.
3. **Exit (04's S2 exit, restated in S3 §8.6):** realtalk auto-posts to its 4 platforms from its profile on its rung; founder.tapes and hombre start Hands-on on S2's flow; every post and click is recorded (`posts`, `post_events`, `clicks`); a gate failure lands in review; the daily digest arrives.

**Rollback:**
- **S2b and S2c:** `clipforge account edit <id> --clear-publisher` puts an account back on the assisted path at once. Publishing state stays in the rows.
- **S2a:** a revert deploy, plus `STATE_READS=dict` as before. 0002 is expand-only, so the S1 code runs on it.

## 10. Coverage of 04's S2 list

| 04's S2 item | Here |
|---|---|
| `Publisher` protocol, `UploadPostPublisher`, `AssistedPublisher` | §2, §6.2–§6.5 |
| Media by signed per-file Volume links | §6.1 |
| Signed webhook updates `posts`; per-platform AI disclosure | §6.4, §6.3 |
| Review tiers; Telegram cards only for items due within 2 h; copy fixes only in the dashboard | §5.2, §5.3, §7.1 (with Q3's morning-batch bridge) |
| Notification policy, the 09:00 digest, quiet hours, deduped alerts | §7.2, §7.3 (`ops.py` reused) |
| The brake survives a Neon outage and cancels scheduled posts | §6.6 |
| One claim per (item, platform); the fallback only after the final failure | §6.2, §6.5 |
| Policy gate v1 | §5.1 |
| Tracking links | §7.4 |
| Autopilot (table, history, dial, Publish switch, presets, ladder, demotions, spot-check floor) | §5.4, §5.5, §5.2, §3 |
| Review windows (format 10, producer version 5, dubs 10) | §5.2 |
| The brake's scope (`/pause <account>`, `/pause all`) | §6.6 |
| One-tap only for due-soon reviews and the brake; Open → `/act` elsewhere | §7.1, §7.3 |
| Publishing-failure rows as instant alerts and "needs me" data | §7.3 |
| The dispatcher replaces `posting_tick`; the digest and alert fold; 3 crons | §4 |
| Migrations: the landing-order rule; the deferred items in the first migration | §3 |

## 11. Proposed changes to other documents (for the coordinator)

### 11.1 ADR-27, acceptance text (into `docs/DECISIONS.md`; 05 keeps a pointer)

> ## ADR-27: One dispatcher cron
> Date: 2026-09-29 · Status: Accepted (2026-10-01, card 011's S2 design; ruling #434; built in S2)
> Context: Modal Starter allows 5 deployed crons; three are used (`sweeper`, `posting_tick`, `posting_daily`). S2 adds the 09:00 digest, publish reconcile and per-slot review and hand-off phases; S6, S7 and S3b add the queue filler, the analytics pull, program checks and a weekly report.
> Decision: One `dispatcher` function runs every 5 minutes, replacing `posting_tick`, and runs each periodic task when it is due. A task declares `due(now)` from Dict state only (the brake, the outage flag, the schedule copies, last-run markers) and `run(key)` within a time budget; slow work is spawned. Each due key is claimed set-if-absent (`dispatch:<task>:<key>`) and released on failure, which raises an ops alert. Postgres is opened only when a task is due, so Neon can scale to zero between due times. `sweeper` and `posting_daily` stay as they are: 3 crons.
> Consequences: Adding a periodic task needs no new cron. One slow task can't delay the others beyond its budget. The per-slot phases (plan at 08:50, review card at S − 2 h, hand-off at S − 30 min) wake Neon about 13 times a day per account.

### 11.2 ADR-33 (the link half), acceptance text

> ## ADR-33: Tracking links and conversion import
> Date: 2026-09-29 · Status: Accepted for tracking links (2026-10-01, card 011; built in S2); conversion import stays Proposed for S7
> Decision (accepted part): `GET /go/<slug>` on the Modal web app looks up a `links` row, logs a click (slug, time, platform from `?p=`, sub-id `<account>.<item or bio>.<platform>`, coarse country only if the request carries one; never the IP or user agent) and answers 302 to the target with the sub-id. Logging is best-effort and never blocks the redirect. Bio and affiliate links in copy are wrapped at hand-off; campaign links stay verbatim. Not hosted on Vercel (Hobby forbids affiliate use).

### 11.3 04 (roadmap), S2

- Split the list into **S2a** (migration with the deferred items, the dispatcher, the brake, autopilot on Hands-on, the gate and routing; assisted flow unchanged), **S2b** (the publisher, media links, the webhook, reconcile, the slot plan, review cards and hand-off, the fallback; realtalk on Upload-Post) and **S2c** (the dial, spot checks, the ladder and demotions, the digest, failure rows, tracking links; founder.tapes and hombre launch). Each sub-step is one PR or more, deployable alone.
- Note the morning-batch bridge (`REVIEW_BATCH`) under the "Telegram review cards only for items due within 2 h" item.
- Strikes: entered by hand (CLI in S2, S3's form later); Upload-Post documents no strike event.
- The exit is unchanged.

### 11.4 06 (session prompts), the S2 card

- **Owner:**
  - Upload-Post **Basic** (O4), not Professional; upgrade at the 6th account.
  - The Facebook Page id per account.
  - Register the webhook URL; `UPLOAD_POST_API_KEY` and `UPLOAD_POST_WEBHOOK_SECRET`.
  - TikTok accounts set to allow public posts.
  - A Whop account only if a campaign source is planned.
- **Actions:** replace 1–8 with the plan's tasks, by sub-step (S2a, S2b, S2c).
- **Depends:** S1's rollout (card 010), ADR-27 accepted (§11.1), ADR-33's link half accepted (§11.2).
- **Cost:** $5 plus real posts (unchanged).

### 11.5 08 §2b and §2c

- Review cards use `r:` callbacks; posting cards keep `p:`.
- The **09:00 morning batch** is a bridge (Q3), behind `REVIEW_BATCH`, until S3's Review page ships; then only the 2 h cards remain (#427).
- The **digest's content** (§7.2) replaces "digest at 09:00" as the description.
- **The brake:** `/pause` and `/go` take `<account>` or `all`, with a Dict key `brake:<scope>` mirrored to `posting_state`, and cancel posts already scheduled at Upload-Post.
- **The "Telegram after S2" paragraph:** the ✅ taps stay for accounts on the assisted path (Publish off, or no connected profile) and for the fallback's failed platforms.

### 11.6 The owner runbook (11)

- **§2 (every day):** the 09:00 digest and review cards replace "answer the clip at each slot" for accounts on Upload-Post.
- **§6 (S2):** Basic, not "a paid plan"; the exact secret names; the webhook registration; the Facebook Page id; `clipforge publisher check`. Then the S2a/S2b/S2c rollout steps of §9.
- **New "Brake" section:**
  - `/pause <account>`, `/pause all` and `/go`;
  - what a brake cancels;
  - what "recorded in the brake only" means;
  - how to check (`clipforge status`).
- **New commands** in the command list: `clipforge autopilot show|set|promote|strike`, `clipforge link add|list`, `clipforge publisher check`, `clipforge account edit --publisher-profile/--facebook-page-id/--clear-publisher`.

### 11.7 Decision log and STATUS

- O4 closes (#440: Basic now, Professional at the 6th account).
- STATUS's S2 row: "designed (card 011)", continuing at the S2 build card after the rollout.
- ARCHITECTURE.md is updated by the build card, not now.
