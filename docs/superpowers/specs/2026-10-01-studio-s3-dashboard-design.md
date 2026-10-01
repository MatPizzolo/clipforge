# Studio S3: the dashboard as the studio's control room (design)

Date: 2026-10-01 · Card: [009](../../cards/009-s3-dashboard-design.md) · Status:
- §1 routine, §2 autopilot model, §3 jobs mapped to the loop, §4 Telegram and the dashboard, §5 staged availability, §6 information architecture: **approved by the owner at checkpoint A (2026-10-01)**, after two rounds of the coordinator's review. Decision log #420–#430.
- §7 pages, §8 gaps, §9 proposed ADRs, §10 proposed changes to other documents: **written at checkpoint B** (mockups in `docs/design/dashboard/`).

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

## 7. Pages (checkpoint B)

Written at checkpoint B: Home, `/act`, the account workspace, Review, Produce and the batch planner, the Hooks tab, Results, Personas; each with purpose, data, actions, the API calls it needs, its Telegram counterpart, its states (empty, loading, error, stale), its phone layout and its availability per stage; plus the link contract.

## 8. Gaps (checkpoint B)

Written at checkpoint B: every API route, data and producer feature the dashboard needs that no card builds yet, each with the roadmap item or new card that should own it.

## 9. Proposed ADRs (checkpoint B)

To be written in full at checkpoint B, for the coordinator to accept into docs/DECISIONS.md after the owner's review:
- **Autopilot per account:** three switches, the Review dial, presets, rails, the graduation ladder and spot-check floor (§2; refines ADR-29).
- **Producer-version review window:** the first 5 items per account after a `producer_version` change go to `review` (§2.2; refines ADR-29 and ADR-43). Log row #423.
- **Hook library versioned outside the account setup:** immutable pattern versions stamped on items, rotation weights frozen during a setup experiment (§3.6; refines ADR-42). Log row #426.

## 10. Proposed changes to other documents (checkpoint B)

08 §2 and §2b (as proposed edits marked for the owner's review), 06's S3 card, and the S3c spec.
