# Studio S3: the dashboard as the studio's control room (design)

Date: 2026-10-01 · Card: [009](../../cards/009-s3-dashboard-design.md) · Status:
- §1 routine, §2 autopilot model, §3 jobs mapped to the loop, §4 Telegram and the dashboard, §5 staged availability, §6 information architecture: **approved by the owner at checkpoint A (2026-10-01)**, after two rounds of the coordinator's review. Decision log #420–#430.
- §7 pages (revised after the owner's review: §7.3 type tabs, §7.8 Personas, log #431–#432; §8 revised for the owner's rulings #433–#436), §8 gaps (with the coordinator's six additions: crons, the queue filler, the "needs me" API, where autopilot settings live, the hook-variant cost, S2's card), §9 proposed ADRs (A, B, C; for the owner's review at B, then the coordinator accepts them), §10 proposed changes to other documents: **written at checkpoint B (2026-10-01), for the owner's review.** Mockups and `DESIGN.md` in `docs/design/dashboard/` (impeccable finish review: 8 material fixes in 2 correction rounds; 7 resolved at the final verdict, the last one fixed after it and confirmed by a computed-style check). 08 §2c carries the proposed 08 edits.

Builds on, and doesn't reopen: ADR-29 (review tiers, policy gate), ADR-38 (the dashboard over the API only), ADR-39 (disclosed synthetic personas), ADR-42 and the [S3c spec](2026-09-30-studio-s3-workspaces-design.md) (versioned setup, experiments, notes), ADR-43 (derived producer version), ADR-44 (one home per task), ADR-45 (notification budget), D8 (Review is a queue manager until S2), D9 (the `admin` endpoint and its token). Facts: [01](../../studio/01-vision-and-strategy.md) (money, review policy), [03](../../studio/03-tools-and-models.md) (cost model), [07](../../studio/07-channel-portfolio.md) and [09](../../studio/09-account-registry.md) (portfolio, accounts, pairs), [08 §2](../../studio/08-dashboard-and-operations.md#2-dashboard-information-architecture-nextjs) (page list).

## 0. Goal

The dashboard is the main place the owner works: analyze each account, review and post, edit each account's style, improve hooks and steer production. **Each account runs as automatically as it has earned**, and the owner steps in only where judgment pays off. Success: the daily check-in fits in about 20 minutes on the phone at any fleet size the budget allows, and the weekly hour on the laptop starts with "these 3 accounts need you".

## 1. The owner's routine (approved)

- **Daily check-in, about 15–20 minutes, mostly on the phone.** Home shows, in order:
  1. **Needs me:** one prioritized list across the fleet, one action per row, with an **attention meter** ("12 of ~20 min today", §2.7).
  2. **Fleet scoreboard:** one line per account (yesterday's posts, views, followers, revenue, a health dot, the ladder rung).
  3. **Today's slots:** scheduled, posted and failed, across accounts.
  When "needs me" is empty, it says "nothing needs you" and the scoreboard moves up.
- **Weekly session, about an hour on the laptop.** It opens on **Accounts → Compare**: every account side by side (lifecycle day N of 90, runway, approval rate, cost per item, top hooks, ladder rung), sorted so the hour starts with the 3 accounts that need the owner most. Style, hooks, experiments and batch planning happen here.
- **The phone must do four things well:** clear "needs me"; review with the video playing; read the numbers (scoreboard and each account's headline stats and money, no editing); and **+ Note** / **+ Hook idea** from anywhere. Both land as S3c notes on the account; a hook idea also becomes a **draft** pattern in that account's hook library (§3.6).

## 2. The autopilot model (approved)

### 2.1 Three switches and a dial per account

| Control | Values | What it does |
|---|---|---|
| **Produce** switch | off / on | Off: the owner starts batches in Produce. On: the **queue filler** keeps the account N days of runway ahead (default 7), within its budget and spend line |
| **Review** dial | `review` · `sample` · `auto` | ADR-29's tier. It has no Off: the policy gate runs on every item in every position |
| **Publish** switch | off / on | Off: assisted posting (Telegram ✅ per platform, today's flow). On: Upload-Post publishes approved items at the slots (S2) |
| **Scale** switch | off / on | Off: dubs of winners are suggested. On: dubs are queued for the **paired** account (§2.5) |

**Presets** set all four at once; any one control can then be overridden, and the account shows "Supervised, with Scale on".

| Preset | Produce | Review | Publish | Scale |
|---|---|---|---|---|
| Hands-on | off | `review` | on | off |
| Supervised | on | `sample` | on | off |
| Autopilot | on | `auto` | on | on |

**Controls never block each other.** Each one shows what it is waiting on, in one line: "Publishing: 0 approved, 3 waiting for you", "Producing: paused, monthly cap reached", "Scale: no paired account". The only blocks are the rails (§2.2).

### 2.2 Rails (no control lifts them)

- The **policy gate** on every item; a failure sends the item to `review`.
- The **spend lines and caps** (§2.6).
- **New accounts start Hands-on.**
- **Format change** (S3c §3.5): the first **10** items made under a version that changed a format field go to `review`.
- **Producer-version change** (ADR-43, e.g. a render `STAGE_VERSION` bump): the first **5** items per account under the new `producer_version` go to `review`, then the account's dial applies again. A producer bump never moves an account down the ladder. This refines ADR-29 and is proposed as a new ADR (§9).
- **First dubs in a language pair:** the first **10** go to `review` (§2.5).

### 2.3 Always the owner's, whatever the controls say

- Any spend above the account's **per-batch line** (§2.6).
- **Sponsored and #ad items:** every one in an account's first 30 days (01's review policy), and every brand-deal post, always.
- **New sources and new series formats.** Autopilot only uses approved ones.

### 2.4 The graduation ladder

The system **suggests**; the owner **approves with one tap** (a "needs me" row). A promotion is never automatic. A demotion is automatic, one step, and shows as a "needs me" row with its reason.

| Move | Criteria |
|---|---|
| Hands-on → Supervised | 01's review policy: ≥ 30 days live, ≥ 50 approved items, < 10% rejected among the last 50, no gate failure in 14 days |
| Supervised → Autopilot | ≥ 30 days on Supervised, ≥ 12 spot checks, ≤ 1 of them rejected, no gate failure or strike in 30 days, runway ≥ 14 days |
| Demotion, one step (automatic) | 2 rejects among the last 5 spot checks |
| Demotion to Hands-on (automatic) | a strike or takedown |

**Spot-check rate on `sample`:** at least 1 item in 10, and at least 3 a week per account, whichever gives more. A 1.5-a-day account gets about 13 spot checks a month (about 0.4 actions a day), so the criteria are reachable in about a month at any cadence.

### 2.5 Dubs

- Dubs go **only to a paired account** (`paired_account_id`, 09). The first real pair is **untold.archive ↔ historias.ocultas** (wave 2, S6). No clips account has a pair today, so for clips the Scale switch shows "No paired account".
- A dub is allowed only where the **source permission allows translation** (O5's field on the source); original scripts always allow it.
- A dub follows the **target** account's review dial and budget, not the source account's.
- The first 10 dubs in a pair go to `review`: a dub is a native adaptation (07), not a literal translation.

### 2.6 Spend

| Limit | Default | What happens at the limit |
|---|---|---|
| **Per-batch approval line** (per account) | $2 | A batch or re-cut estimated above it waits as a "needs me" row |
| **Per-account monthly cap** (variable spend) | clips $5, story $10, band $10, model $10, avatar $20 (about 2× 03's expected variable cost per account) | Production pauses for that account; an instant alert (ADR-45 budget breach) |
| **Fleet monthly cap** (variable spend) | $50 until wave 3, then raised as revenue arrives (03's scenario 2 has about $160 of variable spend) | Production pauses fleet-wide; an instant alert |

- **Variable spend** is GPU, LLM and posting usage. **Fixed subscriptions** (the Modal plan, Upload-Post, Vercel, Neon) are shown separately on Results → Costs and never count against a cap.
- **The brake** is the one mechanism of 04's S2 item: a Dict key checked by every tick and every publish, which survives a Neon outage and cancels posts already scheduled at Upload-Post. Its scope is one account (`/pause <account>`) or the fleet (`/pause all`). There is no second mechanism. Until S2, `/pause` is today's `posting_state` pause.

### 2.7 The attention budget

The owner's daily budget is **~20 minutes** (editable in Settings). Home shows "N of ~20 min today".

- **Until S2, it is counted in minutes,** because assisted posting dominates: one clip posted by hand on TikTok, Instagram, YouTube and Facebook, with copy, costs about **7 minutes**. realtalk at 4 clips a day is about 28 minutes, already over budget. Home shows that honestly.
- **After S2, one decision ≈ 1 minute,** so the budget is about 20 actions. Estimated owner minutes per account per day:

| Type (cadence) | Hands-on | Supervised | Autopilot |
|---|---|---|---|
| clips (3–5 a day) | ~6 | ~1 | ~0.2 |
| story (1–2 a day) | ~3 | ~0.5 | ~0.2 |
| band, avatar, model (~1 a day) | ~2–3 (licenses, claims, drift) | ~0.5 | ~0.2 |
| Fleet overhead (alerts, runway, experiments) | ~2 in total | | |

- **founder.tapes and hombre.en.construccion wait for S2**, whatever the controls say: before S2 each would add about 25 minutes a day.
- Launching an account, changing a format or turning a control down shows the load it adds ("+6 min a day for 30 days") before the owner confirms.
- When "needs me" goes over budget, Home names the Supervised accounts whose ladder criteria are met ("promote these to free ~N min").
- The estimates are replaced by measured minutes (time from a row's appearance to its action) once 30 days of data exist.

## 3. The owner's jobs mapped to the loop (approved)

### 3.1 One home per task (ADR-44)

| Step | Runs alone (when its control allows) | The owner decides | Home in the dashboard | Telegram |
|---|---|---|---|---|
| **Produce** | The queue filler keeps N days of runway: clips from approved sources, story scripts rotating series and pillars, avatar scripts from approved offers, carousels for model accounts | New sources and series; batches over the line; topics, if they want to steer | **Produce** (batch planner), the account's Overview | none (`/clip` retires when Produce ships, ADR-44) |
| **Review** | The policy gate and routing by dial | Items in the `review` lane: the dial, the format and producer-version windows, sponsored items, gate failures, spot checks | **Review** | one-tap approve or reject for items due within 2 h (§4) |
| **Publish** | Upload-Post at the slots (S2) | The brake, rescheduling, assisted posting on accounts with Publish off | **Calendar** | one-tap brake; assisted posting |
| **Measure** | Analytics (S7), costs, payout-program progress, the lifecycle day | Marking campaign submissions; CSV imports | **Results**, the account's Results tab | the 09:00 digest |
| **Scale** | Winners flagged, dubs queued (Scale on), hook patterns ranked | Experiments, hook patterns, promotions, new accounts | **Experiments**, the account's **Hooks** tab, **Accounts → Compare** | digest lines only |
| **Setup** | — | Style, hooks, autopilot, personas, sources | The account's **Autopilot**, **Style**, **Hooks** and Setup tabs; **Personas**; **Sources** | none |

### 3.2 What differs by account type

| Type | What the owner mainly decides | Note |
|---|---|---|
| `clips` | Source permissions | Until S11, new episodes still need a local fetch (ADR-34), so the Produce switch covers only what the sources already hold; runway (§3.3) says so |
| `story` | Pillars and series | Fact sources stored and checked by the gate |
| `band` | Every asset license | A license is a new source, so it is always the owner's |
| `avatar` | Offers | #ad items in review for the first 30 days; no first-person, health or earnings claims |
| `model` | The persona's identity | A drift warning (the consistency score, Personas) sends the item to `review` |

### 3.3 Runway

**Days of content left** per account = (approved queue + items in production + unused material) ÷ cadence. Unused material is unclipped episodes for clips (estimated clips per source hour from the account's history) and open series slots for story-type accounts. Under **14 days** it becomes a "needs me" row: "add sources" (clips) or "approve a series" (others).

### 3.4 Platform health

"Needs me" rows for: a failed post due today, a disconnected publisher (Upload-Post), a **view collapse** (7-day views under 30% of the 28-day median, after S7), and **strikes or takedowns** (from Upload-Post webhooks where they exist, or entered by hand on the account).

### 3.5 What ran without me

Yesterday's automatic actions per account: produced, auto-approved, posted, dubbed, demoted. They appear as a digest line and on the account's **Activity** tab, each linked to its record: the decision-ledger row (08 §1) from S6, and the `post_events` row or the job before that.

### 3.6 Hooks: a versioned library with rotation, separate from experiments

- **The hook library** belongs to an account, and patterns can be shared up to its blueprint. A pattern is a name, a structure ("number + conflict", "open question", "the day that…"), an example line, and the beats it fits (07's hook in the first 3–5 s).
- **Patterns are immutable versions.** An edit writes `pattern@v+1`; every item stamps the `hook_pattern_id@version` it used. ADR-42's traceability holds: an item's setup is `(account_id, account_version)` plus that hook stamp.
- **Rotation:** producers write 2–3 hook variants per item from the approved patterns and ship the best-ranked one. Patterns rotate by weight and are ranked by results. Only one video ships per item (one video, one account, 01).
- **Separate from experiments:** the library lives **outside** S3c's versioned setup, in its own tables, so editing it is never blocked by S3c §4.4. While an account runs a setup experiment, its **rotation weights are frozen**, and the weights in force are logged on each item too, so both sides of an experiment rotate hooks the same way. Changing ADR-42's scope this way is proposed as a new ADR (§9).
- **Judged by:** before S7, the owner's 👍/👎 per hook in review, the posted and reject rates, and numbers entered by hand; after S7, the 3-second hold rate and views at 24 h. Weak patterns are flagged; the owner retires or promotes them (a "needs me" digest line, never instant).

## 4. Telegram and the dashboard (approved; extends ADR-44 and 08 §2b)

- **Every Telegram alert is a "needs me" row pushed to the phone.** Its Open button deep-links to that row's **focused action view**, `/act/<kind>/<id>`: the video or context, 2–3 actions, then **Next** through the rest of the list, so one alert can start a run through the whole list.
- **Acting in either place clears both:** the Telegram message is redrawn as done (no new message, no budget), and the row leaves Home. A link to something already handled shows who did it, when and where ("done by telegram:… at 14:02, in Telegram"), never an error.
- **One-tap inside Telegram** only for review items due within 2 hours (approve or reject, plus today's posting buttons) and for the brake (`/pause`, `/go`). Everything else opens the dashboard (owner ruling, #427).
- **Telegram is the only push channel.** No browser push notifications. In-app banners and toasts for live events while the dashboard is open are fine.
- **Links carry ids only, never tokens;** login is required and keeps the target (#99). The 08 §2b link formats plus `/act/<kind>/<id>` are a **contract**, listed in §7, with a test that each one still resolves.

**Notification level per row type (ADR-45):**

| Row type | Level |
|---|---|
| A review item due within 2 h; the brake; platform health (a failed post due today, a disconnected publisher, a strike); spend over the line or a cap; an expired permission holding clips | **instant** push |
| Runway under 14 days; a promotion ready; a demotion done; experiments to decide; held clips; other job failures; the review backlog; weak hook patterns; "what ran without me" | a **digest** line at 09:00, linking to a filtered view |
| Job done; versions saved; hook rankings moved; stats | **dashboard only** |

## 5. What works when (approved in summary; the per-page table is in §7)

| | Now (Dict, assisted posting) | After S1 | After S2 | After S7 |
|---|---|---|---|---|
| Needs me | failed jobs, held clips | + runway, sources, permissions | + the review lane, publish failures, promotions | + view collapse |
| Controls | Review = the phone checks everything; Publish off (assisted) | the Produce switch for clips (from sources) | the Review dial and the Publish switch live | Scale (winners need views) |
| Hooks judged by | the owner's 👍/👎 | + posted and reject rate | same | + 3-second hold, views at 24 h |
| Results | job costs | + costs per account | + clicks | + views, revenue, program progress |

Every empty state names what unlocks it ("Views arrive with analytics (S7)").

## 6. Information architecture (approved: inbox-first)

Three structures were compared: **A. inbox-first** (Home is "needs me" with focused action views; a few fleet pages, one per loop step, filterable by account; an account workspace for everything about one account), **B. account-first** (navigation is the account list; good for style editing, but reviewing 6 accounts means 6 pages and nothing is fleet-wide), and **C. loop-first** (Produce, Review, Publish, Measure, Scale as navigation; clean for batches, but style, hooks and autopilot have no home). **A** was chosen: it matches the routine (daily inbox on the phone, weekly fleet and workspaces) and the Telegram deep-link model.

**Reconciled with 08 §2 and the S3c pages:**

| 08 §2 / S3c page | In this design |
|---|---|
| Home | **Home**: needs me, then the fleet scoreboard, then today's slots |
| Review inbox | **Review** (before S2, a queue manager, D8) |
| Calendar | **Calendar** |
| Accounts (S3c studio map) | **Accounts**, with two views: **Map** (by category, S3c §2.2) and **Compare** (the weekly side-by-side view; no separate Fleet page) |
| Account workspace (S3c §2.5) | `/accounts/<id>` with tabs: Overview · **Autopilot** · **Style** · **Hooks** · Setup & History (S3c) · Results · Experiments · Notes · Sources · **Activity** (new tabs in bold) |
| Category and blueprint workspaces (S3c) | Unchanged; the blueprint gains a **Hooks** section (shared patterns) |
| Experiments (S3c) | **Experiments** (setup experiments only; hook rotation is not here) |
| Produce | **Produce**: submit, the batch planner with its estimate, the production queue, and a **Jobs** tab (Jobs moves here; `/jobs` and `/jobs/<id>` stay as link targets) |
| Stats, Money, Costs | **Results**, one page with tabs **Stats · Money · Costs**, so revenue and cost sit side by side per account; fixed subscriptions on Costs |
| Sources | **Sources** |
| Personas | **Personas** (under More); the account workspace links to its persona |
| Decisions (S6), Desk, Funnel | Under More, each added when it is built |
| — | **New: Settings** (under More): the attention budget, the fleet cap and default lines, payout-program thresholds (01: editable settings, not constants), quiet hours (read-only) |
| — | **New: `/act/<kind>/<id>`**, the focused action view (a route, not a navigation item) |

- **Laptop sidebar:** Home · Review · Calendar · Accounts · Produce · Experiments · Results · Sources · More (Personas, Jobs, Decisions, Desk, Funnel, Settings).
- **Phone bottom tabs:** Home · Review · Accounts · Results · More.
- **Goes:** Jobs as a top-level item (into Produce; its links keep working), Stats and Costs as separate pages, a separate Fleet page.


## 7. Pages

Mockups: `docs/design/dashboard/` (open `index.html`; resize below 1024 px for the phone layout; the bar on each page switches its states). Design rules: `docs/design/dashboard/DESIGN.md`. All routes below are on S3's `admin` endpoint (D9) with the bearer token and `X-Clipforge-Actor: web:<login>`; every write records that actor (ADR-44). New routes are named here as proposals; the gaps (§8) say which card builds each one.

**Shared states.** Every page has the same four: **loading** (skeletons in the final layout, never a centered spinner); **error** (a red notice naming what failed and what still works, e.g. "the brake still works from Telegram", with Retry; never old numbers presented as current); **stale** (S3a's StaleNote line, "updated 6 min ago · retrying", above the last data; nothing dims, actions stay enabled and the server re-validates each one, answering 409 with the current state if it changed); **empty** (a sentence that says what will fill the page and what unlocks it). Polling follows log #50: Home every 15 s, nothing while the tab is hidden.

### 7.1 Home (`/`) · mockup `home.html`

- **Purpose:** the daily check-in: what needs the owner, at what time cost, then the fleet and today's slots (§1).
- **Data:** the "needs me" rows (§7.11) with their level, account, context, estimated minutes and actions; the attention meter (minutes done today, minutes in the list, budget); the fleet scoreboard (per account: rung, lifecycle day, yesterday's posts, approval rate, cost, runway, health; views, followers and revenue after S7); today's slots per account (posted, failed, next, waiting for an approval); the "ran without you" line.
- **Actions:** each row's primary action in place (approve, reconnect, approve spend, promote, open); "Start with the first row" opens `/act` on the first row; snooze a digest-level row (3 days); the over-budget card's promotion link.
- **API:** `GET /needs` (rows and the meter), `GET /fleet/scoreboard?date=`, `GET /slots?date=`; row actions through `POST /needs/{kind}/{id}/{action}`.
- **Telegram:** instant rows are the alerts the bot pushed, with Open → `/act/<kind>/<id>`; digest rows are the 09:00 digest's lines.
- **Phone:** meter, then rows with their actions under the text; scoreboard as compact rows; slots last. **Laptop:** list left (1.6 fr), scoreboard and slots right.
- **States:** over budget (the meter turns red and a card names the accounts ready to promote and launches that add load), empty ("Nothing needs you" with yesterday's totals), plus the shared four.
- **When:** now: failed jobs, held clips, assisted-posting slots; S1: runway, permissions, per-account cost; S2: the review lane, publish failures, promotions and demotions, spend rows; S7: views and the view-collapse row.

### 7.2 Act (`/act/<kind>/<id>`) · mockup `act.html`

- **Purpose:** where an Open button lands: one decision with its evidence, then **Next** through the list (§4).
- **Data:** the row and its subject (for a review item: video from a signed Volume link, title, account, due time, why it is in review, the gate's answers, the hook pattern and version, copy per platform); the row's position in the list.
- **Actions:** 2–3 per kind (review: Approve for the slot / Reject with reason / 👍 👎 on the hook; spend: Approve / Decline; promotion: Promote / Not yet; publisher: Reconnect / Post by hand); then Next.
- **API:** `GET /needs/{kind}/{id}` (open, or done with who, when and where), `POST /needs/{kind}/{id}/{action}`, `GET /needs?after={kind}/{id}` for Next.
- **Telegram:** every instant message's Open button; the same decision is one tap inside Telegram only for reviews due within 2 h and the brake (#427).
- **Phone:** the video at about half the screen height, evidence below, actions in a sticky bar above the tabs. **Laptop:** video left, evidence and actions right.
- **States:** already handled ("Approved by telegram:owner at 13:02, in Telegram", then Next), not found ("isn't in the list any more; nothing was changed"), plus the shared four.

### 7.3 Account workspace (`/accounts/<id>`) · mockup `account.html`

S3c §2.5's workspace, as a **shared core plus tabs by type** (owner ruling, #431). The core is the same for every type: Overview (its panels change per type), Autopilot, Style, Hooks, Activity, and S3c's tabs (Setup & History, Results, Experiments, Notes, Sources) under More. Each type adds its own tabs after Overview:

| Type | Its own tabs | What they hold | API (proposed) | When |
|---|---|---|---|---|
| `clips` | **Sources & episodes** | Sources with their permission record (monetize, translate, expiry), episodes clipped, clipping and imported but not clipped, clips per source hour; "fetch more" points to the local `clipforge fetch` until S11 | `GET /accounts/{id}/sources`, `GET /accounts/{id}/episodes` | S3 (from S1 sources and `jobs`) |
| | **Framing & captions** | Reframe mode, the no-face fallback, length and minimum score, caption preset, hook title card, the credit line (rules), loudness (fixed, ADR-47), with a preview frame | S3c's setup routes | S3c-2 |
| `story` | **Series & topics** | Series formats with their beats and rotation share (new ones are the owner's to approve), the topic queue with pillar, series and research status, "suggest topics" with its cost | `GET/POST /accounts/{id}/topics`, S3c's setup routes for series | S6 |
| | **Research** | Fact sources per item and their check status; an item with a weak or missing source is held, with "find another source" or "drop the claim" | `GET /items/{id}/sources` | S6 |
| `band` | **Bands & licenses** | The band pipeline (submitted, researching, licensing, featured) and the license of every asset (Commons CC-BY/BY-SA with attribution, band permission, generated art without people) | `GET /accounts/{id}/bands`, `GET /assets?account=` | S9 |
| | **Sounds** | The suggested sound per item (masters are music-free) and whether it was added in each app | `GET /accounts/{id}/sounds` | S9 |
| `avatar` | **Offers & links** | Approved offers with program, commission, tracking link, clicks and sales; a new offer is the owner's to approve | `GET/POST /accounts/{id}/offers` | S8 (links S2) |
| | **Claims** | The claim check per item (first-person use, health, finance, earnings, unsourced comparisons) with a suggested fix | `GET /items/{id}/claims` | S6 Judge, S8 |
| `avatar`, `model` | **Persona & looks** | The persona it uses (consistency, the voice for this account's language) and the looks this account may use; edits happen on the persona page | `GET /accounts/{id}/persona` | S8 |
| `model` | **Carousels** | Carousel, image and reel items with their look and consistency per slide | `GET /items?account=&kind=carousel` | S13 |
| | **Brand deals** | The deal pipeline (lead, negotiating, signed, posted), fee, deliverables and disclosure | `GET/POST /accounts/{id}/deals` | S13 (or S7's money) |

A type tab appears only when its producer exists; before that the account shows the core tabs. The mockup switches types from its top bar (`account.html?type=clips|story|band|avatar|model`); the build reads `kind` from the account.

- **Header:** handle, id, type, language, pair, blueprint and account versions, rung, "day N of 90", open review windows; + Note; Pause this account (the brake, account scope).
- **Overview (new content, per type):** the loop at a glance, one panel per step, with numbers that fit the type (clips: episodes unclipped and spot checks; story: runway and sources; band: licenses waiting; avatar: offers, clicks and sales; model: looks, reach and deals), each with its control's position, one number and one link (Produce: runway, in production; Review: waiting, approval rate; Publish: posts this week, next slot; Measure: views or cost per item; Scale: winners, pair). **Next rung** (the ladder criteria with progress, §2.4) and **Day N of 90** (payout-program progress from the editable thresholds; "months 1–2 usually earn nothing").
- **Autopilot (new):** the three presets with their minutes a day; the four controls with what each is waiting on; spend (month so far against the cap, the batch line, the cap); the rails in force with their windows; a preview of a change ("+$4.20 a month, about −1 min a day") before Apply. Turning the Review dial **up** needs a note. API: `GET /accounts/{id}/autopilot` (state, presets, waiting-on lines, open windows), `PUT /accounts/{id}/autopilot` (with `preview=true` for the dry run), `GET /accounts/{id}/ladder`.
- **Style (new):** S3c's setup fields grouped as Look (caption preset, hook title card, brand kit, visual brief), Voice & persona (voice with a sample, persona link, disclosure), Format (length, series formats with their beats as a bar, pillars) and Posting (slots, hashtags, CTA, bio link). Each value shows its origin (category, blueprint, account) and its change class; a preview frame re-renders the last item with the pending change. Saving goes through S3c's one dry run (`POST /setup/preview`) and its versions; no new write path.
- **Hooks (new):** the library (pattern, version, status, rotation weight with ❄ when frozen, items, 👍/👎, 3-second hold after S7) with Edit (writes v+1), Approve (a draft), Retire, Share to blueprint; the approval rate per pattern with a 90% interval (dataviz: dot and interval, direct labels, a table view); the frozen-weights notice while a setup experiment runs. API: `GET /accounts/{id}/hooks`, `POST /hooks` (draft, also from the phone's + Hook idea), `PUT /hooks/{id}` (new version), `POST /hooks/{id}/approve|retire|share`, `GET /hooks/{id}/stats`.
- **Activity (new):** what ran without the owner, per day, each line linked to its record (§3.5). API: `GET /accounts/{id}/activity?date=`.
- **Telegram:** deep links to `/accounts/<id>` (08 §2b) and to a tab with `?tab=`; nothing is edited from Telegram.
- **Tabs:** Overview, the type's own tabs, Autopilot, Style, Hooks and Activity, then a **More** menu for S3c's tabs, so the phone row fits (it wraps to two rows below 1024 px).
- **Phone:** the loop panels stack; Style's preview frame comes after the groups; + Note lives in the header only.
- **States:** not found; a new account (empty Overview: "approve a series and plan its first batch"); the shared four.

### 7.4 Accounts → Compare (`/accounts?view=compare`) · mockup `accounts.html`

- **Purpose:** the weekly hour (§1): the three accounts that need the owner most this week, then every account side by side.
- **Data:** per account: rung, lifecycle day, runway, approval rate, cost per item, top hook, the owner's minutes a day, views (S7); a ranked focus list with its reason (experiments to decide, open windows, runway under 14 days, weak hooks, health, minutes spent).
- **Actions:** open an account; create one from a blueprint (S3c).
- **API:** `GET /accounts/compare?days=7`.
- **Map** stays S3c §2.2's studio map, as the other view of the same page.
- **Phone:** focus cards, then compact rows. **Laptop:** three focus cards, then the table.

### 7.5 Review (`/review`) · mockup `review.html`

- **Purpose:** decide the review lane in batches on the laptop, or one at a time on the phone; the only place copy is edited (ADR-44).
- **Data:** the queue with thumb, title, account, reason (new-format window, producer-version window, first dubs, sponsored, gate failure, spot check) and due time; the selected item's video, gate answers, copy per platform, hook pattern and version.
- **Actions:** approve (one or a selected batch), reject with a reason, edit copy, re-render, 👍/👎 on the hook; filters by account, reason and due.
- **API:** `GET /review?account=&reason=&sort=`, `POST /review/{item}/approve|reject|rerender`, `PUT /review/{item}/copy`, `POST /review/batch`.
- **Before S2 (D8):** the page is the posting-queue manager: next up per account, reorder, skip, reject with a reason, correct posted marks, all through `posting/actions.py`; it never sends.
- **Telegram:** review cards (approve / reject / Open) only for items due within 2 h (#427).
- **Phone:** the queue only (no batch bar, no inline detail); a row opens `/act/review/<item>`, and Next walks the rest one at a time.

### 7.6 Produce (`/produce`) · mockup `produce.html`

- **Purpose:** plan batches with the cost and the owner's review time shown first; watch the queue fillers; follow jobs (Jobs moves here).
- **Data:** the plan (items with series, pillar and hook pattern, rotating); the estimate per stage (from `config.Prices` and measured costs), the month's spend against the cap, the batch line, the review minutes the batch adds at the account's rung; the queue filler per account (switch, target, runway, what limits it); recent jobs with status and cost.
- **Actions:** queue a batch (under the line) or "Ask me on Home" (over it); resume a failed job; look up a job id.
- **API:** `POST /batches/preview {account, what, n}` (writes nothing), `POST /batches`, `GET /fillers`, `GET /jobs?account=` (S1's `jobs` table), S3a's `GET /jobs/{id}`.
- **Telegram:** none once Produce ships (`/clip` retires, ADR-44); the failure alert keeps [Resume].
- **States:** no approved series ("Autopilot and batches only use approved series"), the over-line case, the shared four.

### 7.7 Results (`/results`) · mockup `results.html`

- **Purpose:** what came out and what it cost, per account, under one filter row (date range, accounts) so the numbers agree.
- **Stats:** one summary line for the period (views, followers gained, posts, approval rate, each with its change; no hero-figure tiles), views per day per account (lines, at most three accounts at once; more fold into "Other" or small multiples), winners (top 10% per account after 7 days) with Clone series and Dub.
- **Money:** revenue against variable cost per account (grouped bars on one dollar axis, margin as a direct label), payout-program progress.
- **Costs:** cumulative variable spend against the fleet cap (line with the cap as a reference line), per-account caps, fixed subscriptions (not counted against caps).
- **Charts** follow the dataviz rules: one axis, categorical slots 1–3 validated for light and dark (`#2a78d6 #eb6834 #1baf7a` / `#3987e5 #d95926 #199e70`), thin marks, a legend plus selective direct labels, a crosshair or per-mark tooltip on hover and keyboard focus, a table view under every chart; aqua is below 3:1 on the light surface, so direct labels and the table are required, not optional.
- **API:** `GET /results/stats|money|costs?from=&to=&accounts=`.
- **When:** now: costs per job; S1: costs per account; S3: caps and fixed subscriptions; S7: views, followers, revenue, programs, winners. The empty state says "Views arrive with analytics (S7)".

### 7.8 Personas (`/personas`, `/personas/<id>`, `/personas/new`) · mockups `personas.html`, `persona.html`, `persona-new.html`

**A persona can serve several accounts, within a pair or one niche** (owner ruling, #432): an EN/ES pair shares the face with a native voice per language, and accounts of one niche can share a presenter. Linking a persona to accounts of unrelated niches is allowed but flagged, because each account should read as its own brand (07). Personas stay synthetic and disclosed (ADR-39).

- **List (`/personas`):** every persona as a card: face, name, role and niche, status (draft with its step, active, retired), voices per language, the accounts it serves (chips), 30-day consistency (median and drift count), looks, and the unrelated-niche warning. "Design a persona…" opens the flow. API: `GET /personas`.
- **Persona page (`/personas/<id>`)**, header with face, status, LoRA version and the accounts it serves; tabs:
  - **Profile:** name, role, a bio per language (with "AI host" or "AI creator"), personality and tone, niche, lifecycle; **rules** (never says: first-person product use, health, finance, legal or earnings claims, anything hiding that it is AI; always on: AI labels, C2PA, #ad on affiliate items, synthetic-only training); the accounts it serves with each one's voice, allowed looks, renders and median score.
  - **Looks:** outfits, settings and props made by inpainting from the anchors (the face stays locked), each draft or approved, with the accounts allowed to use it, its renders and median score; renders rotate through an account's allowed looks; "+ New look" shows its cost. A look that drifts is named in Consistency.
  - **Consistency:** the score of every render over 30 days per account (dots, the 0.80 threshold as a reference line, a table view), the causes of drift (lighting, pose, outfit) with the look behind them, and a flagged render side by side with the anchors, with "re-render with another look" or "approve anyway" (a note).
  - **Voice:** one voice master per language (design prompt, pace, pauses), a box to hear any test line, A/B variants. A dub uses the target account's voice.
  - **Anchors & LoRA:** the 3 anchors (versioned; renders keep the version they used) and the LoRA versions with what each was trained on and its median score.
- **Design a persona (`/personas/new`):** seven steps, saved after each, each showing its cost before it runs: (1) brief, with the synthetic-only checks (no photos of real people, disclosure on, niche check); (2) about 12 candidate faces; (3) pick 3 and refine them into front, ¾ and profile anchors; (4) a voice per language from a prompt; (5) test lines; (6) train the LoRA on its own generated images only; (7) link accounts (the niche warning applies) and activate. The footer keeps the running cost (about $1.10–2.10 per persona, mostly the LoRA; spike X3 measures it). A failed step charges nothing and keeps what was saved.
- **API:** `GET /personas`, `POST /personas` (draft), `GET /personas/{id}`, `PUT /personas/{id}/profile`, `GET/POST /personas/{id}/looks`, `POST /looks/{id}/approve|retire`, `GET /personas/{id}/renders?days=30`, `GET/POST /personas/{id}/voices`, `POST /personas/{id}/voices/{lang}/say` (a test line), `POST /personas/{id}/anchors`, `POST /personas/{id}/lora`, `PUT /personas/{id}/accounts`, `POST /personas/{id}/activate|retire`.
- **Data (proposed):** `personas(id, name, status, niche, profile jsonb)`, `persona_versions` (anchors and LoRA, append-only), `persona_accounts(persona_id, account_id, voice_id, looks[])`, `persona_looks(id, persona_id, version, status, data)`, `persona_voices(id, persona_id, lang, version, data)`, and on each item `persona_id`, `look_id`, `anchor_version`, `lora_version` and `consistency`.
- **Telegram:** none, except a drifted render that blocks a due item, which is a normal review row.
- **When:** S8 (the persona producer, with X3's consistency method); the model accounts' looks and carousels in S13. Until then the list is empty ("comes with the avatar producer").

### 7.9 Settings (`/settings`, no mockup)

The attention budget (default 20 min), the fleet cap ($50) and default batch line ($2) and caps per type (§2.6), payout-program thresholds (01: editable, not constants), quiet hours (read-only, ADR-45). `GET /settings`, `PUT /settings` (actor recorded).

### 7.10 The link contract

Every path Telegram or the digest links to (#427). A test resolves each one after login (Playwright, phone and desktop) and checks that an unknown id shows "not found", never a blank page.

| Path | From | Since |
|---|---|---|
| `/jobs/<id>` | failure alert, job done | S3a (08 §2b) |
| `/accounts/<id>`, `/accounts/<id>?tab=<tab>` | alerts and digest lines about one account | 08 §2b, S3c §2.9 |
| `/sources/<id>` | permission alerts | 08 §2b |
| `/experiments/<id>`, `/experiments?needs=decision` | digest | 08 §2b |
| `/review?account=<id>` | digest backlog line | 08 §2b |
| `/categories/<code>`, `/blueprints/<name>` | — (dashboard only) | S3c §2.9 |
| **`/act/<kind>/<id>`** | every instant alert's Open button | new (§4) |
| **`/?needs=<kind>`** | digest lines that list several rows of one kind | new |
| **`/accounts?view=compare`** | the weekly digest | new |
| **`/results?tab=costs&account=<id>`** | budget alerts | new |

### 7.11 "Needs me" rows

One row per decision, `id = <kind>:<subject>`. Its level comes from §4's table; its time estimate from §2.7.

| Kind | Subject | Level | Primary action | Built in |
|---|---|---|---|---|
| `review_due` | item, due within 2 h | instant | Approve / Reject | S2 |
| `review_batch` | account + reason | digest | Open batch | S2 |
| `publish_failed` | post due today | instant | Retry / Post by hand | S2 |
| `publisher_disconnected` | account + platform | instant | Reconnect | S2 |
| `strike` | account + platform | instant | Open | S2 (webhook) or S3 (manual entry) |
| `spend_line` | batch | instant | Approve / Decline | S3 |
| `cap_reached` | account or fleet | instant | Raise cap / Leave paused | the card that enforces caps in `create_job` (§8.2) |
| `permission_expired` | source | instant | Open source | S1 data, S3 row |
| `runway_low` | account | digest | Add a source / Approve a series | S3 |
| `promotion_ready` | account | digest | Promote / Not yet | S2 |
| `demotion_done` | account | digest | Open | S2 |
| `experiment_decision` | experiment | digest | Open (decided only on its page, D7) | S3c-3 |
| `held_clips` | account | digest | Open | S1 data, S3 row |
| `job_failed` | job | instant if under 1 day of queue, else digest | Resume | today (ops alert), S3 row |
| `hook_weak` | pattern | digest | Open hooks | hooks card (§8) |
| `series_approval` | draft series | digest | Approve / Reject | S3c (series formats) |
| `view_collapse` | account | instant | Open | S7 |
| `outage` | `posting:outage` | instant | Restore / Go | today's flag (#217), S3 row |

## 8. Gaps: what no card builds yet

Each gap names the work and the roadmap item or card that should own it. "S3" means 06's S3 card (dashboard v1); "hooks card" is a new card proposed below.

### 8.1 Scheduled work and the cron limit

Modal allows 5 deployed crons. Three are used: `sweeper` (every 10 min), `posting_tick` (every 5 min), `posting_daily` (07:00 UTC).

| Periodic work | Where it runs |
|---|---|
| "Needs me" rows, runway, graduation suggestions, the attention meter | **derived on read** by `GET /needs`, like S3c's "needs a decision" (no cron) |
| Instant pushes | **inline**, by the writer of the event (tick, step failure, webhook, review service), through ADR-45's `ops_alert()` path |
| Demotions | **inline**, in the review service when a spot check is rejected (§2.4) |
| The 09:00 digest (S2) | needs a schedule: a claim `digest:<date>` checked by a 5-minute cron |
| The queue filler (Produce switch) | daily per account, at its batch hour |
| S7's analytics pull | daily |
| Notion weekly report (S3b) | weekly |

**Ruling (#434): accept ADR-27 (one dispatcher cron) by S2,** when the digest arrives. ADR-27 is drafted in 05; the coordinator accepts it into `docs/DECISIONS.md` with S2's card. The dispatcher replaces `posting_tick` at the same 5-minute cadence and runs each task when it is due, with last-run markers in the Dict and Postgres touched only when a task is due, so Neon can still scale to zero. `sweeper` and `posting_daily` stay as they are: 3 crons, room for 2.

| Task the dispatcher runs | When | Added by |
|---|---|---|
| The posting tick (today's `posting_tick`: slots per account, assisted sends, the outage guard) | every 5 min | S2 (moved, unchanged) |
| Upload-Post scheduling and the brake check before each publish | every 5 min, inside the tick | S2 |
| The 09:00 digest (owner's time zone, claim `digest:<date>`) | daily | S2 |
| Ops-alert folding after quiet hours (ADR-45) | 08:00 owner time | S2 (moved from the tick) |
| The queue filler (Produce switch), per account at its batch hour | daily | S6 |
| The analytics pull (Upload-Post, YouTube Analytics) | daily | S7 |
| Program progress and view-collapse checks | daily, after the pull | S7 |
| The Notion weekly report (S3b) | weekly | S3b/S7 |

Not on the dispatcher: "needs me" rows, runway and graduation suggestions (derived on read), instant alerts and demotions (inline, by the event's writer), `sweeper` (every 10 min) and `posting_daily` (07:00 UTC, ADR-46).

### 8.2 The queue filler (Produce switch)

- **Owner: S6.** S6 builds the first producer where automatic production matters (stories from briefs, its variation engine). Build the filler there as a generic `produce/filler.py` (Modal-free): per account, top up to N days of runway from approved series and sources, within the batch line and caps, through the same `POST /batches` path.
- **For clips, before S11** the filler can only clip sources already imported (uploaded to the Volume or registered as sources) and not yet clipped; it can't fetch (ADR-34, local fetch). Runway (§3.3) shows "fetch more episodes" when that pool is empty. A clips adapter ships with the S6 filler.
- **Hard spend caps (ruling #435):** the per-account monthly cap and the fleet cap are enforced in the job service, `service.create_job`, for **every** caller: the API, the CLI, Telegram, the batch planner and the queue filler. A job over a cap is refused with the cap and the month's spend; a batch over the account's per-batch line becomes a "needs me" row instead of a job. The check is built by **the first card that creates jobs automatically**: the queue filler (S6), unless an earlier card adds automatic job creation, in which case that card builds it. The dashboard only shows the caps, the lines and the burn (Produce's estimate, Results → Costs, the Autopilot tab). S7 keeps the reporting (spend per account and per stage, budget burn-down).

### 8.3 The "needs me" API

- **Owner: S3.** One read endpoint assembles the rows: `GET /needs?account=&level=` → `{rows: [{id, kind, level, account_id, title, context, due_at, est_minutes, actions: [{key, label, primary}], href}], attention: {budget_min, done_min, listed_min}}`; `GET /needs/{kind}/{id}` (open or done, with actor, time and surface); `POST /needs/{kind}/{id}/{action}` dispatches to the owning service (`posting/actions.py`, the review service, the autopilot service, the batch service), which writes with the actor. The router owns no state.
- **Sources:** before S1's rollout, the Dict (jobs, `post:*`, held clips, the outage flag); after it, Postgres (`jobs`, `posts`, `post_events`, sources, accounts) plus the Dict's claims. The row kinds are §7.11.
- **New data:** `needs_snoozes(row_id, until, actor)`; `needs_log(row_id, appeared_at, acted_at, surface)` for measured minutes after 30 days (§2.7).
- **Telegram link:** each instant alert records its row id, so a dashboard action redraws the message as done (08 §2b's sync rule) and the Open button carries `/act/<kind>/<id>`. Ops alerts (ADR-45) gain the Open button in S3.

### 8.4 Where the autopilot settings live

- **Ruling (#433): operating state, not ADR-42 setup.** A table `autopilot(account_id PK, preset, produce, review_dial, publish, scale, runway_days, batch_line_usd, monthly_cap_usd, updated_by, updated_at)` with an **append-only change history** `autopilot_events(id, account_id, at, actor, field, from_value, to_value, reason)`, one row per changed field, never updated or deleted (a trigger rejects UPDATE and DELETE, like S3c's `*_versions`).
  - **Who:** `actor` is `web:<login>`, `telegram:<id>`, `system:promotion` or `system:demotion`. A promotion is always the owner's tap, so its row carries `system:promotion` as the actor with the approving owner in `reason` ("promotion approved by web:owner: 34 days on Supervised, 13 spot checks, 0 rejected"); a demotion is automatic (`system:demotion`, reason "2 rejects in the last 5 spot checks").
  - **When, from → to, why:** `at`, `from_value`, `to_value` and `reason` (required for the owner's changes to the Review dial, written by the system for its own).
  - **Readers:** the account's **Activity** tab and the "what ran without me" digest line and Home footer read it; Accounts → Compare shows the last change per account.
- **Why not the versioned setup:**
  - demotions are automatic and must apply at once, even while a setup experiment runs (S3c §4.4 would block them);
  - the dial changes how items are reviewed, not what is produced, so it doesn't belong in `(account_id, account_version)`;
  - it is the same kind of runtime state as the pause in `posting_state` (ADR-41).
- **One writer (ADR-41):** `accounts/autopilot.py` (Modal-free), called by the admin routes, the review service (demotions) and the ladder (promotions on the owner's tap). Automatic writes use a new actor prefix, `system:<component>` (`system:promotion`, `system:demotion`, and `system:filler` for the queue filler's jobs), which S3c's actor check constraint must allow (§10.3).
- **Traceability:** every send and review decision records the dial and windows in force in `post_events.data` (`review_dial`, `window`), so results stay attributable.
- **Experiments:** an autopilot change during a running setup experiment is allowed; the experiment page shows it as a marker ("Produce switched on, day 3").
- **Consequence for S3c:** the review tier (S3c's "rules" class) and the budget (its "identity" class) move out of the versioned setup into this table (§10.3).
- **Owner:** **S2** creates the table, the service and the routes with the Review dial and the Publish switch (review tiers are S2's); Produce becomes live with S6's filler, Scale with S10's dubs; **S3** builds the Autopilot tab.

### 8.5 Hook variants and their cost

- **Per item:** the producer writes 2–3 hook variants from the account's approved patterns and ranks them in the same Haiku call; one ships.
  - Clips: the hook title card's text, in one extra call of about 1.5K input and 200 output tokens. That is about **$0.0025 per item** (Haiku 4.5 at $1/M in, $5/M out).
  - Story and avatar: the script's first line, about 2K in and 300 out, about **$0.0035 per item**.
  - At 03's scenario 2 (about 1,000 items a month), about **$3 a month**.
- **Where it shows:**
  - a "Hook variants" line in every batch estimate (Produce, `/act` spend rows);
  - a "hooks" stage in Results → Costs;
  - per-item cost in `metadata.json` (rule 7).
- **Attention cost: none.** 👍/👎 is optional and costs about 0 minutes.
- **Owner: a separate hooks card (ruling #436),** sequenced **after S1's rollout and before S6**, so the story producer is built on it. Outline:
  1. **Pattern versions:** tables `hook_patterns(id, account_id, blueprint_name NULL, status)` and `hook_pattern_versions(pattern_id, n, data jsonb, author, created_at)`, append-only (an edit writes v+1); drafts from + Hook idea (S3c notes); share to a blueprint; seed each clips account's library from its current hook title style.
  2. **Item stamping:** `content_items.hook_pattern_id`, `hook_version` and `hook_weights jsonb` (the weights in force when the item was made); the stamp also lands in `metadata.json`.
  3. **Variants in producers:** the clips producer writes 2–3 hook-title variants from approved patterns and ranks them in one Haiku call (a new prompt version, so the captions `STAGE_VERSION` bumps; about $0.0025 per item, logged as cost, rule 7); the story producer uses the same interface from its first version (S6).
  4. **Rotation:** `hook_weights(account_id, pattern_id, weight, frozen_by_experiment NULL)`; per item, a weighted pick among approved patterns; weights freeze while the account runs a setup experiment (ADR C).
  5. **Ranking before S7:** the owner's 👍/👎 per hook in review (`hook_ratings`), approval and reject rates per pattern with the 90% interval and S3c's 10-item floor; weak patterns become a digest line.
  6. **Ranking after S7:** the 3-second hold and views at 24 h per pattern join the ranking, each with its maturity age; weights move only on settled results.
  7. **Surfaces:** admin routes (`GET /accounts/{id}/hooks`, `POST /hooks`, `PUT /hooks/{id}`, `POST /hooks/{id}/approve|retire|share`, `GET /hooks/{id}/stats`) and the Hooks tab (§7.3); before S3c's workspace exists, a standalone `/hooks?account=` page.
  8. **Tests:** pattern versions append-only; every item stamped; weights frozen during an experiment; the variants call validated with rule 5's single retry and a fallback to the plain title; cost recorded.

### 8.6 S2's card must change

04's S2 exit expects all three wave-1 accounts to auto-post. With #428, founder.tapes and hombre.en.construccion are **created just before S2** and launch on it. S2's new items:
- the **review windows**: the first 10 items after a format change (S3c's `format_changed`), the first 5 per account after a `producer_version` change (§9, ADR B), the first 10 dubs in a pair (S10 reads it);
- the **Review dial and the Publish switch per account** in the `autopilot` table (§8.4), with presets, the ladder, the spot-check floor and automatic demotions;
- the **brake's scope**: `/pause <account>` and `/pause all` as one Dict key with a scope, checked by every tick and publish, cancelling posts scheduled at Upload-Post;
- **one-tap in Telegram only for items due within 2 h** (approve / reject) and the brake (#427); every other card carries Open → `/act`;
- **publishing-failure rows** (`publish_failed`, `publisher_disconnected`, `strike` where Upload-Post reports it) as instant alerts and "needs me" rows;
- ADR-27's dispatcher replaces `posting_tick` and runs the 09:00 digest (§8.1);
- the `autopilot` table with its append-only change history (§8.4);
- **exit, restated:** realtalk auto-posts from its profile on its rung; founder.tapes and hombre.en.construccion are created and start Hands-on on S2's flow.

### 8.7 Every other gap

| # | Gap | Proposed owner |
|---|---|---|
| G1 | `/act/<kind>/<id>` view and the "already handled" lookup (who, when, where, from `post_events` and review decisions) | S3 |
| G2 | Fleet scoreboard (`GET /fleet/scoreboard`) and today's slots (`GET /slots`) | S3 (views columns in S7) |
| G3 | Accounts → Compare and its focus ranking (`GET /accounts/compare`) | S3c-1 (the Accounts page) |
| G4 | Graduation ladder: criteria on read, promote route, automatic demotion, spot-check floor | S2 |
| G5 | Producer-version window (first 5) | S2 |
| G6 | Dubs: translation permission check, target dial and budget, first 10 to review | S10 |
| G7 | Hard caps (per account, fleet) enforced in `service.create_job` for every caller; the batch line turns an over-line batch into a "needs me" row | the first card that creates jobs automatically (S6's queue filler, or earlier); `POST /batches/preview` and `POST /batches` for clips in S3; S7 keeps the reporting |
| G8 | Fixed subscriptions (a settings list) shown in Costs | S3 |
| G9 | Fleet brake scope (`/pause all`) | S2 (the brake item) |
| G10 | Attention estimates per row and per rung; measured minutes from `needs_log` after 30 days | S3 |
| G11 | Runway per account (clips: unclipped imported sources; story: open series slots) | S3 (clips), S6 (story) |
| G12 | Strikes and takedowns: manual entry on the account, webhook where Upload-Post exposes it | S3 (manual), S2 (webhook) |
| G13 | View collapse (7-day views under 30% of the 28-day median) | S7 |
| G14 | Activity feed per account (`GET /accounts/{id}/activity`), linked to jobs and `post_events`, then to the ledger | S3, S6 (ledger links) |
| G15 | Hook library, versions, stamps, frozen weights, ratings, the Hooks tab; clips variants | the hooks card (§8.5), after S1's rollout, before S6 |
| G16 | 3-second hold and views at 24 h per hook pattern | S7 |
| G17 | Lifecycle day N of 90 (from `accounts.created_at`) and program progress from editable thresholds | S3 (day), S7 (programs) |
| G18 | Settings page and `settings` table | S3 |
| G19 | Results page with tabs; Costs in S3, Stats and Money in S7 | S3, S7 |
| G20 | Personas: the list, the persona page (profile, looks, consistency, voices, anchors and LoRA), the creation flow, the persona–account links with the niche warning, and per-item stamps (`persona_id`, `look_id`, anchor and LoRA versions, score) | S8 (with X3's method); looks for model accounts in S13 |
| G26 | Type tabs in the account workspace (§7.3 table): routes and data per type | S3 (clips), S6 (story), S8 (avatar), S9 (band), S13 (model) |
| G21 | Review routes (copy edit, re-render, batch approve) | S2 (the review service), S3 (the page) |
| G22 | Link-contract test (§7.10) | S3 |
| G23 | `system:` actor prefix (`system:promotion`, `system:demotion`, `system:filler`) and the append-only `autopilot_events` history | S2 (with the `autopilot` table) and S3c-1's migration 0002, whichever lands first |
| G24 | `needs_snoozes` and `needs_log` | S3 |
| G25 | Ops alerts with Open buttons to `/act` | S3 |

## 9. Proposed ADRs

For the coordinator to accept into `docs/DECISIONS.md` after the owner's review. Numbers are assigned on acceptance (the next free number is ADR-48, per 05).

### ADR A: Autopilot per account
Date: 2026-10-01 · Status: Proposed (card 009; refines ADR-29; log #421, #422, #425, #428)
Context: ADR-29 gives each account a review tier. The owner wants each account to run as automatically as it has earned, across production, review, publishing and scaling, within a daily attention budget of about 20 minutes and spend limits, with the owner stepping in only where judgment pays off.
Decision:
- Each account has three switches (Produce, Publish, Scale) and the Review dial (ADR-29's `review`, `sample`, `auto`), set together by presets Hands-on, Supervised and Autopilot; any one can be overridden. Controls never block each other; each shows what it waits on.
- Rails no control lifts: the policy gate; the batch line, account cap and fleet cap; new accounts start Hands-on; the review windows (format change: 10; producer version: 5, ADR B; first dubs in a pair: 10).
- Always the owner's: spend over the line, sponsored and #ad items (first 30 days; brand deals always), new sources and new series formats.
- A graduation ladder: the system suggests promotions on 01's criteria (Hands-on → Supervised) and on ≥ 30 days, ≥ 12 spot checks with ≤ 1 rejected, no gate failure or strike in 30 days and runway ≥ 14 days (Supervised → Autopilot); the owner taps. Demotions are automatic: one step after 2 rejects in the last 5 spot checks, to Hands-on after a strike. On `sample`, spot checks are at least 1 in 10 and at least 3 a week per account.
- The settings are operating state in an `autopilot` table with one writer (`accounts/autopilot.py`) and an append-only change history (who, when, from → to, why), not part of ADR-42's versioned setup; automatic changes use the actors `system:promotion` and `system:demotion`. The Activity tab and "what ran without me" read the history.
- Hard spend caps are enforced in `service.create_job` for every caller; the dashboard only shows them.
Consequences: owner time scales with how new each account is. ADR-29's tier becomes the Review dial and leaves S3c's "rules" class. Two new tables. Wave-2 clip accounts wait for S2 because assisted posting doesn't fit the attention budget.

### ADR B: Producer-version review window
Date: 2026-10-01 · Status: Proposed (card 009; refines ADR-29 and ADR-43; log #423)
Context: ADR-29 says a new producer version starts in `review`. With ADR-43, a `producer_version` changes whenever stage versions, prompts or models change (for example S4's render version bump), which would put every account back in full review.
Decision: after a `producer_version` change, the first 5 items per account made under the new version go to `review`; then the account's dial applies again. The account's rung doesn't change. A format change keeps S3c's 10.
Consequences: about 5 reviews per account per producer change (about 95 across 19 accounts), against a full return to Hands-on. S2 enforces it from `content_items.producer_version`.

### ADR C: Hook library versioned outside the account setup
Date: 2026-10-01 · Status: Proposed (card 009; refines ADR-42; log #426)
Context: hooks are the lever the owner wants to improve most. Rotating hook patterns per item and ranking them by results is continuous, while ADR-42's setup experiments change one account version at a time and block other setup edits while they run.
Decision: each account has a hook library (patterns shareable to its blueprint) in its own tables, outside the versioned setup. Patterns are immutable versions; an edit writes v+1; every item stamps `hook_pattern_id@version` and the rotation weights in force. Producers write 2–3 variants per item from approved patterns and ship the best-ranked one. While the account runs a setup experiment, its rotation weights are frozen. Hook rotation is never an S3c experiment.
Consequences: an item's setup is `(account_id, account_version)` plus its hook stamp, so ADR-42's traceability holds. About $0.0025–0.0035 of Haiku per item. A separate hooks card builds it after S1's rollout and before S6.

## 10. Proposed changes to other documents

### 10.1 08 §2 and §2b

Added to 08 as a new subsection, **§2c "Proposed by card 009 (pending the owner's review)"**, without changing the accepted tables: the merges and moves of §6 (Results, Accounts → Compare, Jobs into Produce, Settings, Personas under More, `/act`), the one-tap rule (#427), every alert as a "needs me" row with an Open link, the new link formats (§7.10) and the level table (§4). The coordinator folds them into §2 and §2b on acceptance.

### 10.2 06's S3 card (and 04's S3 list)

- **Pages:** Home with "needs me", the attention meter, the scoreboard and slots; `/act`; Review; Calendar; Produce with the batch planner and the Jobs tab; Results with Costs (Stats and Money in S7); Sources; Settings; the account workspace's Overview, Autopilot and Activity tabs (on S3c's workspace once it exists; before that, a minimal `/accounts/<id>` read view). Remove "Costs" as its own page.
- **API:** `GET /needs`, `GET /needs/{kind}/{id}`, `POST /needs/{kind}/{id}/{action}`, `GET /fleet/scoreboard`, `GET /slots`, `GET /accounts/{id}/activity`, `POST /batches/preview`, `POST /batches`, `GET /results/costs`, `GET /settings`, `PUT /settings`.
- **Data:** `needs_snoozes`, `needs_log`, `settings`.
- **Caps shown, not enforced:** Produce's estimate and the Autopilot tab show caps and lines; enforcement is in `create_job` (§8.2).
- **The link-contract test** (§7.10) and ops alerts with Open buttons.
- **Exit, restated:** the owner runs the daily check-in from the phone in under 20 minutes, and every Telegram alert opens its row in `/act`.

### 10.3 The S3c spec (proposed; the S3c spec itself is not edited here)

- §3.5: the **review tier** leaves the "rules" class and the **budget** leaves "identity": both move to the `autopilot` table (§8.4). The format-change window (`format_changed`) stays in the setup.
- §5.3: the actor check constraint allows `system:<component>` (automatic demotions, the filler).
- §2.2: the Accounts page gains the **Compare** view next to the Map (§7.4).
- §2.5: the workspace gains Overview content, Autopilot, Style (S3c's setup fields grouped, same write path), Hooks and Activity tabs (§7.3).
- §2.7: the experiment page shows autopilot changes as markers.
- §4.1: hook-pattern metrics are reported on the Hooks tab, not in the experiment metric registry.

### 10.4 04 (roadmap)

- S2: §8.6's items and restated exit.
- S3: §10.2.
- S6: the queue filler (§8.2) and story hook variants.
- S7: "budget enforcement before job start" moves to `create_job` in the first card that creates jobs automatically (S6's filler, or earlier); S7 keeps the reporting. The dispatcher is accepted earlier, at S2 (§8.1).
- A new hooks card after S1's rollout and before S6 (§8.5).
