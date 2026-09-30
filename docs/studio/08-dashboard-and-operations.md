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
| `review` | a human decides in Telegram or the dashboard |
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

| Page | What it shows | Primary actions |
|---|---|---|
| **Home** | Today across all accounts: posts scheduled or published, review inbox count, escalation rate, spend vs budget, anomalies, a banner for any source permission expiring within 14 days, and experiments that **need a decision** (S3c) | Jump to the inbox or the experiment |
| **Review inbox** | Items in `review`/`fix`, with video preview (R2), per-platform copy, gate answers and confidences, and the reason for escalation | Approve, edit copy, reject (with reason), re-render |
| **Calendar** | Week view per account and platform: scheduled, published, failed | Drag to reschedule, pause an account |
| **Accounts** (S3c) | The **studio map**: every account grouped by category (`clips`, `story`, `band`, `avatar`, `model`) with status, blueprint and version, tier, recent posting and running experiments. **Workspaces** per category (playbook, rules, defaults, blueprints), blueprint (pillars, series, briefs, money, prompts) and account (effective setup with where each value comes from, versions and diffs, results, experiments, notes, its sources, health). Every save is a new version (ADR-42) | Create from a blueprint; edit the setup (with a note); reset an override; diff and restore versions; apply a category or blueprint version to its accounts; add a note; start an experiment |
| **Experiments** (S3c) | Across all accounts: **needs a decision**, running (progress, before vs during so far), drafts, and ideas (open idea notes). Each experiment: hypothesis, change (from and to version), one metric, window, cost preview, result with a verdict (likely better / no clear difference / likely worse) and a "too few items" warning | Start one from an idea or a setup change; stop; keep or revert with a reason; add the learning to the category playbook |
| **Sources** | Every source (kind, account, status) with its permission record: type, granted date and by whom, evidence link, platforms, monetization and translation allowed, expiry, restrictions; campaign rules; change history | Add a source, edit it, pause or end it (the database is the only copy, since S1) |
| **Personas** | Voice sample, face references, LoRA versions, a consistency score (from X3's method) | Regenerate, retire |
| **Produce** | Submit jobs (clip a source, picked from Sources so credit and permission come with it; story brief or topic batch, band, avatar offer, dub a winner); **batch planner** ("10 scripts for account X this week") | Queue batches with a cost estimate |
| **Decisions** | The ledger: filter by decision, lane, judge, account; calibration chart vs audit outcomes; threshold settings | Adjust thresholds (logged) |
| **Stats** | Per item and account: views, retention (where available), followers; **winners** (top decile) | Queue a dub, clone a series |
| **Money** | Program progress (YPP, TikTok Rewards, Facebook CMP), clicks, conversions, revenue vs cost per account, campaign submissions (Whop) | Import CSV, mark a campaign submission |
| **Costs** | GPU, LLM and Judge costs per stage, item and account; budget burn-down | Change budgets |
| **Desk** (after S7) | Inbound events by lane (comments, DMs, emails, submissions, offers, trends) with drafts | Send a draft (manually), mark handled |
| **Funnel** (later) | Bio-page visits, email signups, sequence performance, product sales | — |

Implementation notes:
- **Server components** call the Modal `admin` endpoint from Vercel route handlers, with proxy-auth headers plus the bearer token (02 §8).
- The typed client is generated by hey-api. TanStack Query polls every 2–5 s on live pages.
- Media plays from R2 URLs.
- No direct database access from Vercel (ADR-2).
- **Phone and laptop:** every page works on both. On a phone: bottom tabs and one column. On a laptop (≥ 1024 px): a sidebar, multi-column pages, and tables where lists get long (clips, sources, posts). Telegram and the phone remain the quick path; the laptop is for review batches, planning and setup.

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
