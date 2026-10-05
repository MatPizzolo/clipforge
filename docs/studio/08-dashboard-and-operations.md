# 08: Dashboard, decisions and operations

Owner decisions (2026-09-29):
- **The Next.js dashboard is the operational system,** and Postgres is the source of truth.
- **Notion gets a one-way mirror** for planning and weekly reports. Nothing is ever read back from Notion.
- A **Jev-style decision ledger and lanes** ship with the first AI producer (S6); publishing (S2) starts with pure gate checks. The inbound **Desk** comes after S7.
- **Own info products are planned now and built later.**

## 1. Decision ledger, lanes and audit (adapted from the "Jev Desk" pattern)

Every automated decision is **one row in `decisions`**. Decisions include:
- gate checks
- review routing
- hook and title ranking
- tagging
- and later, Desk triage

Each row records:

```
decisions(id, at, subject_kind, subject_id, account_id, decision, judge, model_version,
          questions_json, answers_json /* value, probs, confidence per question */,
          lane, audit bool, tokens_in, cost_usd, latency_ms, outcome /* filled later */)
```

**Lanes for content items:**

| Lane | Meaning |
|---|---|
| `publish` | auto-post (allowed only in `sample`/`auto` tiers) |
| `review` | a human decides on the dashboard (ADR-54; Telegram only notifies) |
| `fix` | a writing model redrafts the copy, then it goes back to the gate |
| `reject` | dropped, with a reason |

For inbound Desk events the lanes are `ignore`, `log`, `draft` and `human`.

**Rules:**
1. **Fail closed.** A Judge error, timeout or missing key means `review` (or `human`). It never means `publish` or `ignore`.
2. **Ask all questions in one request.** Answers come back in parallel. **When they disagree,** for example a gate "pass" alongside a "health claim" probability above a floor, **escalate the item.** This signal costs nothing extra.
3. **Requirements go in the question text and the option descriptions.** The Judge doesn't see field names.
4. **Pin model versions** (e.g. `jev-1.13.0`), never a moving alias. The version is part of the row.
5. **The input is labeled as content, not instructions,** in every request. This matters most for comments, DMs and emails.
6. **Audit the silent lanes.**
   - About 5% of `publish` decisions go to a spot-check review. This is the `sample` tier's ~10% digest, now measured.
   - About 1% of Desk `ignore` decisions get a second look.
   - The audit's outcome fills `outcome`, which gives the **false-pass** and **false-ignore** rates.
7. **The threshold is a cost setting, not a safety setting.** A higher floor means more human reviews. It doesn't mean fewer silent mistakes; only the audit measures those. Change one threshold a week and check the audit after each change.

**The bill formula** (shown on the dashboard):

```
daily cost = Σ decisions × tokens × judge price        (tiny: Jev ≈ $0.042/M input tokens)
           + escalations × cost per draft/review        (the part that moves)
escalation rate = (fix + review) / decisions          ← the number to watch
```

**Morning message** (a Telegram digest from the dispatcher cron, daily at 09:00 in the owner's timezone):
- per account: yesterday's posts, views, followers, clicks and revenue;
- the cost split (GPU, LLM writing, Judge);
- the escalation rate;
- anything flagged by the audit;
- anything over budget.

Anomalies (escalation above target, a false pass, a budget breach) go on the first line.

## 2. Dashboard information architecture (Next.js)

| Page | What it shows | Primary actions | Telegram's role (ADR-44) |
|---|---|---|---|
| **Home** | Today across all accounts: posts scheduled or published, review inbox count, escalation rate, spend vs budget, anomalies, a banner for any source permission expiring within 14 days, and experiments that **need a decision** (S3c) | Jump to the inbox or the experiment | Digest at 09:00 links here (ADR-45) |
| **Jobs** (S3a, built) | A job-id lookup, recent jobs (kept in the browser until S3 has a jobs list from S1's `jobs` table), and the job page: clips, progress, errors, cost, download link | Look up a job; resume a failed one (S3) | The failure alert carries [Resume] (deliberate duplicate: safe and cached, one tap) and [Open]; `/status <job_id>` and typed `/resume` retire when this page has Resume |
| **Review inbox** | Items in `review`/`fix`, with video preview (signed Volume links; R2 only if needed, ADR-28), per-platform copy, gate answers and confidences, and the reason for escalation | Approve, edit copy, reject (with reason), re-render | Telegram sends one notification, "N items need review → Open", for items due within 2 h; every decision and copy edit happens only here (ADR-54). Before S2b this page is a queue manager (skip, reject, reorder, posted correction), not a second posting flow |
| **Calendar** | Week view per account and platform: scheduled, published, failed | Drag to reschedule (a later card, not S3: S3 dashboard spec §11.11; writers `dispatch/plan.py` for one slot, the accounts service for the schedule), pause an account | `/status` in Telegram is a short read-only summary with a link here. The per-account pause here is the same writer as `/pause` (deliberate duplicate: the brake must work from the phone) |
| **Accounts** (S3 Compare, S3c Map) | **Compare** (S3, `/accounts?view=compare`) and the **studio map** (S3c): every account grouped by category (`clips`, `story`, `band`, `avatar`, `model`) with status, blueprint and version, rung (from `autopilot`, ADR-48), recent posting and running experiments. **Workspaces** per category (`/categories/<code>`: playbook, rules, defaults, blueprints), blueprint (`/blueprints/<name>`: pillars, series, briefs, money, prompts) and account (`/accounts/<id>`: Overview, the type's tabs, Autopilot, Style, Hooks and Activity, then Setup & History (effective setup with where each value comes from, versions and diffs), Results, Experiments, Notes and Sources under More; §2c). Every save is a new version (ADR-42), previewed first by one dry run (diff, re-runs, affected items, cost) | Create from a blueprint; edit the setup (with a note); reset an override; diff and restore versions; apply a category or blueprint version to its accounts; add a note; start an experiment | none (notes and edits only here) |
| **Experiments** (S3c) | Across all accounts: **needs a decision**, running (progress, before vs during so far), drafts, and ideas (open idea notes). Each experiment: hypothesis, change (from and to version), one metric, window, cost preview, result with a verdict (likely better / no clear difference / likely worse) and a "too few items" warning | Start one from an idea or a setup change; stop; keep or revert with a reason; add the learning to the category playbook | the digest lists "needs a decision" (link `/experiments?needs=decision`); keep or revert is decided only on the experiment's page, `/experiments/<id>` |
| **Sources** | Every source (kind, account, status) with its permission record: type, granted date and by whom, evidence link, platforms, monetization and translation allowed, expiry, restrictions; campaign rules; change history | Add a source, edit it, pause or end it (the database is the only copy, since S1) | an instant alert when an expired permission starts holding clips; the digest lists permissions expiring within 14 days |
| **Personas** | Voice sample, face references, LoRA versions, a consistency score (from X3's method) | Regenerate, retire | none |
| **Produce** | Submit jobs (clip a source, picked from Sources so credit and permission come with it; story brief or topic batch, band, avatar offer, dub a winner); **batch planner** ("10 scripts for account X this week") | Queue batches with a cost estimate | `/clip` stays in Telegram until this page ships, then retires (ADR-44) |
| **Decisions** | The ledger: filter by decision, lane, judge, account; calibration chart vs audit outcomes; threshold settings | Adjust thresholds (logged) | none |
| **Stats** | Per item and account: views, retention (where available), followers; **winners** (top decile) | Queue a dub, clone a series | none (digest line: yesterday's posts) |
| **Money** | Program progress (YPP, TikTok Rewards, Facebook CMP), clicks, conversions, revenue vs cost per account, campaign submissions (Whop) | Import CSV, mark a campaign submission | none |
| **Costs** | GPU, LLM and Judge costs per stage, item and account; budget burn-down | Change budgets | an instant alert on a budget breach |
| **Desk** (after S7) | Inbound events by lane (comments, DMs, emails, submissions, offers, trends) with drafts | Send a draft (manually), mark handled | none |
| **Funnel** (later) | Bio-page visits, email signups, sequence performance, product sales | — | none |

Implementation notes:
- **Server components** call the Modal `admin` endpoint from Vercel route handlers, with proxy-auth headers plus the bearer token (02 §8).
- The typed client is generated by hey-api (types and zod schemas). TanStack Query polls Home every 15 s and a running job every 5 s, and not at all while the tab is hidden (log #50).
- Media plays from signed, expiring Volume links (ADR-13, ADR-28); R2 only if those prove unreliable.
- No direct database access from Vercel (ADR-2).
- **Phone and laptop:** every page works on both. On a phone: bottom tabs and one column. On a laptop (≥ 1024 px): a sidebar, multi-column pages, and tables where lists get long (clips, sources, posts). Telegram and the phone remain the quick path; the laptop is for review batches, planning and setup.

### 2b. Two surfaces, one product (ADR-44, ADR-45)

**One home per task.** The column above names Telegram's role for each page. **Telegram is notifications only (ADR-54, 2026-10-05):** alerts (each "needs me" row as a notification with Open → `/act/<kind>/<id>`), the 09:00 digest, status replies (`/status`) and the brake. It takes no decisions: no clip cards with per-platform buttons, no review approve or reject, no manual-posting fallback. The dashboard does everything that needs a decision, context, comparison, editing, bulk actions, history, experiments or money. Tasks in both surfaces, each on purpose:

| Task | Why both | Shared backend |
|---|---|---|
| ~~Assisted posting (✅ per platform, ⏭, 🗑 + reason)~~ | Retired by ADR-54: paused since 2026-10-05, dormant code until removed; Upload-Post posts from S2b. The dashboard's Review Queue keeps the posted correction | `posting/actions.py` (S1 addendum), actor `web:<login>` |
| Pause / go | The brake must work from the phone; the laptop toggles one account | `posting/actions.py` `pause`, plus a Dict brake key from S2 |
| ~~Review approve / reject~~ | Dashboard only (ADR-54); Telegram sends "N items need review → Open" | the S2 review service |
| Resume a failed job | The alert carries only Open → `/act/job_failed/<id>`, where Resume is one tap with the job's context; no Resume button in Telegram (ADR-54, owner 2026-10-05) | `service.resume_job` |

**Staying in sync.** A dashboard action redraws every Telegram notification of that row as done ("Done by … at …", #616); a brake sent from Telegram shows on the dashboard's next poll. Both surfaces follow ADR-14's one-writer rule and the same claim keys.

**Notification policy (ADR-45):**

| Event | Where |
|---|---|
| Review items due within 2 h (one "N items need review → Open" notification, ADR-54); a publish failed for a post due today; a job failed with less than 1 day of queue left; `/pause` confirmation; Upload-Post disconnected; budget breach; an expired permission holding clips; the database unavailable at the tick | **instant** |
| Other job failures, held clips, accounts with under 3 days of queue, permissions expiring within 14 days, experiments needing a decision, sample-tier spot checks, review backlog, cost vs budget, yesterday's posts | **digest**: one message at 09:00 in the owner's time zone, ending with "N items need review → Open" (no cards follow, ADR-54); its content is §2c's "S2" block below (S2 spec §7.2) |
| Job done, clips rendered, successful posts, version saves, source edits, stats | **dashboard only**. A Telegram notification already sent is edited in place ("Done by … at …"), which uses no budget |

- **Quiet hours:** 23:00–08:00; only brake-worthy events (publishing broken across accounts, spend over 2× the daily budget) break through.
- **Rate limits:** one alert per (kind, subject) per hour, deduped by a Dict claim `notify:<kind>:<subject>:<hour>`; at most 20 instant messages an hour, the rest folded into "N more → dashboard".
- **Ops alerts:** silent failures (channel jobs, enqueue, tick, `posting_daily`, mirror, verify differences) go through `OpsAlerts.alert()` in `ops.py` (built by `ops_alerts()`); an alert failure never fails a step.

**Deep links.** Telegram messages carry URL buttons built from `DASHBOARD_URL`: `/jobs/<id>`, `/accounts/<id>` (a tab with `?tab=`, using the S3 dashboard spec §7.3's tab names), `/sources/<id>`, `/experiments/<id>`, `/experiments?needs=decision`, `/review?account=<id>`. `/categories/<code>` and `/blueprints/<name>` (S3c) are dashboard-only formats, never linked from Telegram. Login keeps the target (`callbackUrl`, relative paths only, log #99).

**Identity.** One owner: the Telegram user id in `TELEGRAM_ALLOWED_USER_IDS` and the GitHub account whose verified email is `OWNER_EMAIL`. Every write records which one acted.

**Telegram after ADR-54 (2026-10-05).** Telegram is notifications only: alerts (each with Open → `/act/<kind>/<id>`), the 09:00 digest, status replies and the brake (`/pause`, `/go`, `/pause all`). No review cards, no 09:00 review batch, no clip cards with ✅ per platform, and no AssistedPublisher fallback: if Upload-Post fails, Telegram sends an alert (reconnect, or open the failure row), never a manual post card. Assisted posting is paused now; realtalk posts nothing until S2b publishes through Upload-Post, and S2b waits for the Review page (card 024). The assisted code stays dormant, then is turned off per account when Upload-Post goes live. `/clip` retires when Produce ships; `/status <job_id>` and typed `/resume` retire when the job page has Resume. Only review decisions made on the dashboard count toward the ladder, the spot checks and the windows (R2, R6; #454).

### 2c. Accepted changes from card 009 (2026-10-01; ADR-48 to ADR-50)

> **Accepted on 2026-10-01** (the owner's review of card 009; log #134). Where §2 and §2b above differ, this section wins. Design: [S3 dashboard spec](../superpowers/specs/2026-10-01-studio-s3-dashboard-design.md), mockups in [docs/design/dashboard/](../design/dashboard/index.html), log #420–#439.

**Pages (§2).** The structure is inbox-first (#430):
- **Home** becomes "needs me" (one prioritized list across the fleet, one decision per row, with an attention meter against a ~20-minute daily budget), then the fleet scoreboard, then today's slots.
- **New: `/act/<kind>/<id>`**, a focused action view for one row (context, 2–3 actions, then Next). Every Telegram alert's Open button lands there.
- **Stats, Money and Costs merge into Results** (tabs Stats · Money · Costs, one filter row). Fixed subscriptions are shown on Costs and never count against caps.
- **Accounts** gets two views: a new **Compare** (every account side by side, led by "the 3 accounts that need you this week"), built in S3 as a read view (#439), and S3c's **Map**.
- **The account workspace** gains these tabs:
  - **Overview:** the loop at a glance, the next rung, and day N of 90;
  - **Autopilot:** three switches and the Review dial, presets, rails and spend;
  - **Style:** S3c's setup fields, grouped;
  - **Hooks:** a versioned library with rotation;
  - **Activity:** what ran without you.
- **The account workspace is a shared core plus the type's own tabs** (#431), e.g. clips get Sources & episodes and Framing & captions; avatar accounts get Offers & links, Claims and Persona & looks.
- **Personas** opens on a list of every persona with the accounts it serves; a persona may serve a pair or one niche, with a warning across unrelated niches (#432). A persona page has Profile, Looks, Consistency, Voice, Anchors & LoRA, plus a seven-step creation flow with costs.
- **Jobs moves into Produce** as a tab; `/jobs` and `/jobs/<id>` keep working as link targets.
- **New: Settings:** the attention budget, caps and lines, payout-program thresholds, and quiet hours (read-only).
- Personas, Decisions, Desk, Funnel and Settings sit under **More**.
- **Navigation:**
  - laptop sidebar: Home · Review · Calendar · Accounts · Produce · Experiments · Results · Sources · More;
  - phone tabs: Home · Review · Accounts · Results · More.

**Two surfaces (§2b).**
- **Every Telegram alert is a "needs me" row** pushed to the phone, with Open → `/act/<kind>/<id>`. Acting in either place clears both. A link to something already handled shows who did it, when and where (#429).
- **No one-tap decisions in Telegram** (ADR-54, 2026-10-05; replaces #427's due-soon review buttons): review items due within 2 hours get one notification, "N items need review → Open". The brake stays (`/pause`, `/go`, and `/pause all` at fleet scope, the same Dict key as 04's S2 brake). Everything else opens the dashboard.
- **Telegram is the only push channel.** There are no browser push notifications.
- **New link formats** (a contract, with a test that each one resolves): `/act/<kind>/<id>`, `/?needs=<kind>`, `/accounts?view=compare`, `/results?tab=costs&account=<id>`.
- **Levels per row type:**

  | Level | Row types |
  |---|---|
  | Instant | due-soon reviews (one "N items need review → Open" notification), the brake, platform health (a failed post due today, a disconnected publisher, a strike), spend over a line or a cap, expired permissions holding clips |
  | Digest | runway under 14 days, promotions ready, demotions done, experiments, held clips, other failures, the review backlog, weak hook patterns, "what ran without you" |
  | Dashboard only | everything else |

**S2 (card 011's spec, accepted 2026-10-02, amended by ADR-54 on 2026-10-05; [S2 spec](../superpowers/specs/2026-10-01-studio-s2-design.md) §6.7, §7; log #443, #448, #454, #455, #149, #150).**
- **Callbacks:** no review cards and no `r:` callbacks (ADR-54). Old posting cards keep their `p:` callbacks, dormant while posting is paused.
- **No 09:00 morning batch and no `REVIEW_BATCH`** (removed by ADR-54, log #150). Undecided review items get one "N items need review → Open" notification at S − 2 h.
- **The digest's content:** one message at 09:00 in the owner's time zone, claimed `digest:<date>`; lines with nothing to say are left out. In order: anomalies (an outage, a brake that's on, a disconnected publisher, yesterday's final publish failures, the database unavailable at a tick, unmatched webhook deliveries); yesterday per account (posted, of which automatic, failed, rejected, what ran without you); today per account (slots, approved, need you); the attention arithmetic (about 1 minute per review decision against the ~20-minute budget; no assisted clips after ADR-54; naming accounts whose ladder criteria are met when over); then the digest-level rows (promotions ready, demotions done, runway under 14 days, held clips, expiring permissions, other job failures, the review backlog, missed slots), ending with "N items need review → Open". Planning (08:50) and the digest run in the owner's time zone for every account; slots keep each account's own (R3).
- **The brake:** `/pause` and `/go` take `<account>` or `all` (no argument is the fleet). The Dict key `brake:<scope>` is written first and mirrored to `posting_state` (`changed_by`, `reason`); `/go` writes `on=false` and never deletes the key. A pause cancels posts already scheduled at Upload-Post and the reply counts them; with Neon down it says the pause is recorded in the brake only. `posting_daily` repairs a difference between the key and the row: the newer one wins.

**S3 (card 019's delta, proposed 2026-10-02, pending the owner's review; [S3 dashboard spec §11](../superpowers/specs/2026-10-01-studio-s3-dashboard-design.md#11-revised-2026-10-02-card-019-the-delta-after-s2s-plan); log #610–#623).**
- **Two endpoints, split by caller:** the dashboard's Vercel route handlers call `admin` (Modal proxy auth plus `ADMIN_API_TOKEN`, actor `web:<login>`); `web` keeps the public routes and, until S3-5b's CLI cut-over, S2's `/admin/*` routes for the CLI. Every dashboard API route is under `/admin/`.
- **Sync:** alerts and notifications with an Open button are recorded under `alert:msg:<row id>` and edited to "Done by … at …" after the row is acted on (best-effort).
- **Review** has a Queue tab (assisted accounts: move to the front, skip, reject, posted correction) and a Review lane tab (S2's routes, plus batch approve).
- **Bridges end after 7 days online:** `/clip`, `/status <job_id>` and typed `/resume` in S3-5b, after Produce and the job page's Resume (S3-4); `/status` with no argument, `clipforge status <id>` and `clipforge resume <id>` stay. (`REVIEW_BATCH`, once listed here, was removed by ADR-54.)

**Hooks (card 020's spec, 2026-10-02; [hooks spec](../superpowers/specs/2026-10-02-studio-hooks-design.md) §5, §6, §7; log #550–#562).**
- **Home:** the account workspace's **Hooks** tab (`/accounts/<id>?tab=hooks`, S3c). Until S3c's workspace exists, a standalone page **`/hooks?account=<id>`**, which then redirects to the tab. Both paths join the link contract. The page holds the library (pattern, version, status, weight with ❄ while a setup experiment freezes the rotation), each pattern's rates against the "Highlight title" control with a 90% interval, and Edit, Approve, Retire, Share to blueprint and Weight (with the suggested value pre-filled).
- **Dashboard only:** 👍/👎 per hook (on the Review page and the Hooks page), weight changes, and re-rendering one item with another pattern or title (Review's re-render button, disabled until the hooks build's HK-2). Telegram has no hook task and, after ADR-54, no review cards at all (#553).
- **Digest:** `hook_weak`, one line per pattern likely worse than the control with ≥ 10 decided items, with a suggested weight, linking to the Hooks page. Never instant (ADR-45).

## 3. Notion mirror (one-way)


- **What gets mirrored:**
  - the planning pack (`docs/studio/*`, as pages under a "ClipForge Studio" parent);
  - the channel portfolio;
  - SOPs (how to add an account, connect platforms, handle a takedown);
  - a **Weekly report** page per week.
- **How:** a small `notion_mirror` periodic task on the dispatcher cron (weekly), using the Notion API with an integration token stored in the Modal secret. It **creates or replaces** pages and never reads edits back.
  - Planning pages: synced when the docs change, by a CLI command `clipforge notion sync-docs`.
  - Weekly report: generated from Postgres.
- **Rule:** Notion is for reading, sharing and thinking. Changes to accounts, thresholds or queues are made only in the dashboard or repo. Notion pages say so at the top.
- The Notion mirror doesn't need to wait for the dashboard. The pack can be mirrored on day one.

## 4. The Desk (inbound triage, after S7)

- **Sources:**
  - comments and DMs (through the posting provider's API where it's available, otherwise platform APIs);
  - a shared inbox for brand deals and band submissions (IMAP or a forwarding address);
  - Whop campaign listings;
  - trend items from the weekly research job.
- **Questions per event:**
  - `lane` (ignore / log / draft / human)
  - `urgency` (later / today / now)
  - `evidence` (enough / missing)
  - `money` (none / possible deal / payment or legal)
- **Guards:**
  - money, legal, safety or `evidence=missing` → `human`;
  - `urgency=now` with `ignore`/`log` → `human`;
  - Judge errors → `human`.
- **Drafts:** Claude writes replies into the Desk queue. **Nothing is ever sent automatically.** The owner sends.
- **Privacy:** personal messages go only to providers whose terms fit. Retention is limited.

## 5. Own products and funnel (planned now, built later)

- **Candidates:**
  - profe.ia.ingles → a Spanish-language English course on Hotmart, taught by the same AI tutor persona;
  - ai.tools.lab → an AI-automation course or templates;
  - realtalk.clipsdaily → a Skool community.
- **Funnel pieces:**
  - link-in-bio pages on the same Vercel app (per account, with Umami analytics);
  - email capture;
  - an email service (to choose later: Resend, Loops or Beehiiv);
  - a 5–7 email sequence per product;
  - sales imports (Hotmart API, Skool CSV, Gumroad).
- **The studio can produce lesson videos** with the story or avatar producers (same persona, same Timeline renderer).
- **Guardrails** (FTC and platform rules):
  - no invented testimonials or "X% of students" figures unless they're measured;
  - no fake scarcity;
  - guarantees only with legal review;
  - no link-dropping spam on Reddit or Quora.
