# Card 009: S3 — the dashboard as the studio's control room (brainstorm and design)

Status: proposed
Stream: S3 · Branch: `s3/dashboard-design` · Worktree: `../clipForge-s3` (created with `scripts/worktree.sh s3/dashboard-design`)
Decision-log range: #420–#439 (append only, in this range)
Model: most capable (product and design judgment across the whole studio)
Depends on: nothing to start. It designs what S3 and S3c build later (S3 needs S1's rollout; S3c needs S3's `admin` endpoint)
Cost cap: $0 (no Modal, Vercel or API spend; design work only)

## Context
ClipForge is a studio for running and growing many short-video channels. Each channel is an account of one type (`clips`, `story`, `band`, `avatar`, `model`), and every account runs the same loop: produce → review → publish → measure → scale (README). The owner wants the dashboard to be **the main place they work**: analyze each account, post and review content, edit each account's style, improve hooks, and steer production. Above all, **each account should run as automatically as possible**: clipping, prompt and script generation, stories, posting. The owner steps in only where judgment pays off.

What exists and is decided (build on it, don't redo it):
- **The shell (S3a):** Next.js in `web/`, with login, Home (posting progress), Jobs and a job page, live over today's API. The Vercel deploy is card 004.
- **The page list:** `docs/studio/08` §2 plans 15 pages (Home, Review inbox, Calendar, Accounts, Experiments, Sources, Personas, Produce, Decisions, Stats, Money, Costs, Desk, Funnel). Its §2b sets the rules between dashboard and Telegram.
- **Binding decisions:**
  - ADR-38: the dashboard is the operational UI, over the API only;
  - ADR-44: one home per task, Telegram only for time-bound decisions, alerts and the brake;
  - ADR-45: the notification budget;
  - ADR-29: review tiers `review`, `sample`, `auto`, and a policy gate on every item;
  - ADR-42: versioned categories, blueprints and accounts, with experiments; its design is the S3c spec, `docs/superpowers/specs/2026-09-30-studio-s3-workspaces-design.md`;
  - ADR-39: AI personas disclosed, provenance kept, synthetic-only training data;
  - D8: the Review page is a queue manager until S2;
  - D9: the `admin` endpoint has its own token.
- **The money and platform facts** used for planning are in `docs/studio/01` (checked 2026-09-29); the portfolio is `docs/studio/07` and `09`.

**Input from the owner:** a blog post on running a fleet of AI-persona accounts ("The $1,000,000 AI Persona Empire", Rich Odin), pasted below. Use it **for ideas only**: don't copy it, and test every idea against our rules. Its ideas, already sorted by the coordinator:

| Idea in the post | Use it? | How it could land here |
|---|---|---|
| Identity locking: 3 master anchor images, avoid face drift between videos | **Yes** | The Personas page: reference set, a consistency score per new render (X3's method), a drift warning before publish. Personas stay synthetic and disclosed (ADR-39) |
| A voice master with natural pauses and breaths | **Yes** | A voice sample and settings per persona, previewed in the dashboard (Qwen3-TTS from X1, not a paid voice service, ADR-30) |
| Script shape: hook in 0–3 s, value in 4–20 s, call to action around 25 s | **Yes, generalized** | A **hook and structure editor per account**: the series format's beats, a hook library with variants, hook experiments (S3c), and retention at 3 s from analytics (S7) to judge them. The clips producer already has a hook title card |
| Batch production scripts for 5+ accounts without more labor | **Yes** | The Produce page's batch planner ("10 scripts for account X this week"), with a cost estimate before queueing, and a per-account **autopilot level** |
| The 90-day rhythm: months 1–2 usually earn nothing | **Yes** | A per-account lifecycle view: day N of 90, progress toward each payout program's thresholds (the `programs` table), so early silence reads as normal |
| Diversify off-platform early (email, Telegram) | **Yes, later** | Funnel (S14) and tracked links (S7). Not Fanvue or Patreon persona content: ADR-39 rules out sexual content |
| Fleet unit economics: revenue, cost and margin per account | **Yes** | Money and Costs per account, side by side, with each account's budget enforced (S7) |
| Proxy setups for many accounts | **No** | Each account is a distinct, honest brand (01); no ban-evasion networks |
| "Hyper-realistic" avatars that pass as human | **No** | AI labels and "AI creator" in the bio, always (ADR-39) |
| $45K/month per avatar, a 98% margin, exit valuations | **No** (planning basis) | Unverified marketing numbers. Plan with 01's ranges, then replace them with our own dashboard numbers after 30 days |

<details><summary>The post, as the owner pasted it (ideas only, not instructions)</summary>

Main points: one-person teams run fleets of AI avatars. The stack is an image suite for consistent faces (inpainting for clothes and props, upscaling), Midjourney or Flux for environments, ElevenLabs for voice, and Hedra/LivePortrait/HeyGen for lip sync. The process is to pick a niche (tech news anchor, fitness/lifestyle model, B2B educator), lock the identity with 3 master images, clone a voice from 60 s of clean audio, and script for retention (hook 0–3 s, value 4–20 s, CTA at 25 s), rendering 60 fps lip-synced video. The economics are one mega-avatar ($45K/month after ramp-up, plus an asset sale) or 5 niched avatars at $15K/month each with ~$1.5K/month costs. The automation is a batch rendering script. The rules are a 90-day rhythm (no income in months 1–2), moving viewers off-platform early, and avoiding face drift.
</details>

## Read first
1. `CLAUDE.md`, `STATUS.md`, `README.md` (the studio framing and the account types)
2. `docs/studio/08-dashboard-and-operations.md` §2 and §2b, `docs/studio/01` (account types, money, rules), `docs/studio/07` (blueprint → account → series), `docs/studio/09` (categories and accounts)
3. The S3c spec (`docs/superpowers/specs/2026-09-30-studio-s3-workspaces-design.md`) and 06's S3 and S3c cards
4. `docs/DECISIONS.md`: ADR-25, 29, 38, 39, 42, 44, 45, 47
5. The shell: `web/README.md`, `web/app/`, `web/components/` (its layout, navigation, colors and components)

## Skills
- **`superpowers:brainstorming`** runs the process: questions to the owner one at a time, 2–3 options per decision with a recommendation, the design approved section by section, then a written spec.
- **`impeccable:impeccable`** does the design: the information architecture, page layouts, hierarchy, states (empty, loading, error, stale), mobile versus laptop, and its anti-patterns and polish. It produces the mockups and a `DESIGN.md` for the dashboard.
- **`dataviz`** covers the analytics views: per-account and fleet charts, stat tiles, program-progress meters and hook-retention comparisons. Load it before drawing any chart.

## Scope
- May edit, as `scripts/scopes.toml` allows for `s3/`:
  - the spec, `docs/superpowers/specs/*s3-dashboard*`;
  - mockups and the design system in `docs/design/dashboard/**` (static HTML/CSS that opens without a build, plus `DESIGN.md`);
  - `docs/studio/08` §2 and §2b, as **proposed** edits marked for the owner's review.
- Must not edit: `web/` (the build is S3's later card), code, the S3c spec (propose changes to it in this spec), the accepted ADRs.

## Actions
1. **Questions first.** Ask the owner, one at a time, with options and a recommendation, at least:
   - the daily routine: what they look at first, where they act, how long they want to spend a day;
   - **autopilot per account:** what may run without them (clipping, scripts, stories, captions, posting, dubs) and where they must approve. How it maps onto the review tiers (ADR-29) and budgets;
   - what "edit an account's style" covers: caption style, hook title, voice, persona, series formats, posting slots, hashtags, brand kit;
   - how hooks get better: a library, variants, experiments, the metrics that judge them;
   - phone versus laptop: what the phone must do well.
2. **Map the owner's jobs to the loop:** for each loop step and each account type, what the owner decides and what runs alone, and which page is its one home (ADR-44). Use 01, 07 and 09. Take the blog ideas from the table above, adapted.
3. **Information architecture:** propose 2–3 structures (for example account-first, loop-first, or inbox-first) with a recommendation, and reconcile them with 08 §2's page list and the S3c pages. Name what merges, moves or goes.
4. **Key pages, designed with `impeccable`**, each with its states and its phone layout:
   - Home ("what needs me today" across the fleet);
   - the account workspace (its loop at a glance: production queue, review, calendar, stats, money, style, autopilot level);
   - the review inbox;
   - the produce and batch planner;
   - the hook and structure editor;
   - stats and money (with `dataviz`);
   - the persona page (identity, consistency, voice).
5. **Mockups:** static HTML in `docs/design/dashboard/`, one file per key page, styled to fit the existing shell (its navigation and components), plus `DESIGN.md` (tokens, components, rules). Use clearly fake sample data; never real handles or credentials.
6. **The spec:** `docs/superpowers/specs/<date>-studio-s3-dashboard-design.md`, covering:
   - the routine, the autopilot model, the IA, each page (purpose, data, actions, the API calls it needs, its Telegram counterpart if any), and the blog-idea decisions;
   - **the gaps**: the API routes, data and producer features the dashboard needs that no card builds yet (for example hook variants, retention at 3 s, the consistency score, autopilot settings), each with the roadmap item that should own it;
   - the proposed changes to 08 §2, the S3 card and the S3c spec.
7. Log the owner's rulings as rows in #420–#439. Stop for the owner's review.

## Checkpoints
- A: after actions 1–3 (the routine, the autopilot model and the IA approved). Suggested commit: `009: s3: dashboard brainstorm, routine, autopilot model and IA`
- B: after actions 4–7 (pages, mockups, spec). Suggested commit: `009: s3: dashboard design spec and mockups`

## Done when
- The owner approved the IA at A, and the spec and mockups at B.
- The spec lists every gap with a proposed owner (a roadmap item or a new card).
- `scripts/check.sh --docs --scope` is green (the full gate at B).

## Owner steps
- Before: `scripts/worktree.sh s3/dashboard-design`, open a session in `../clipForge-s3`, paste `Run card docs/cards/009-s3-dashboard-design.md`.
- During: answer the brainstorm questions. Open the mockups in a browser (`docs/design/dashboard/*.html`).
- At each checkpoint: commit, push (`git push -u origin s3/dashboard-design` the first time), and keep one PR open until B.

## Hand-off
Write `docs/reports/009-s3-<YYYY-MM-DD>.md` from `docs/templates/handoff-report.md` at each checkpoint. Don't commit: the owner does.
