# ClipForge

ClipForge is a studio for running and growing many short-video channels on TikTok, Instagram Reels, YouTube Shorts and Facebook Reels, in English and Spanish.

Each channel is an **account** of one **type**: podcast clips, AI-narrated stories, music-band discovery, an AI-avatar presenter, or an AI model persona. Every account runs the same loop, **produce → review → publish → measure → scale**, on shared machinery. What differs by type is how a video gets made, how the account earns, and which rules it must follow.

Everything runs serverless on [Modal](https://modal.com), with a Next.js dashboard as the control room and Telegram as the phone surface. The target is 20+ accounts run by one owner.

> **Content policy:** every account uses only content it owns or has permission to use, discloses AI and sponsorship, and never tries to evade copyright detection. See [docs/SOURCING.md](docs/SOURCING.md) and the per-type rules below.

## The loop every account runs

```
            ┌──────────────────────────────────────────────────────────────────────────┐
            │                                                                          │
            ▼                                                                          │
 PRODUCE ─────────────► REVIEW ─────────────► PUBLISH ─────────────► MEASURE ────────► SCALE
 the account type's     policy gate on        every platform the     views, followers,   more of what wins,
 producer makes a       every item, then      account has enabled,   clicks, sales,      new series, dubs
 video (a ContentItem)  the account's tier:   at its posting slots   cost per item and   EN ↔ ES, new
                        review · sample · auto                       per account         accounts
```

| Step | What happens | Where it stands |
|---|---|---|
| **Produce** | A producer turns a source or a brief into a `ContentItem`: the video, per-platform copy, credits, licenses, AI and sponsorship flags, cost. Every producer describes its video as a `Timeline`, and one renderer turns any Timeline into the final mp4 (captions, -14 LUFS, under 50 MB). | The clip producer is live, on the Timeline renderer (S4). The other producers are planned. |
| **Review** | A pure policy gate checks every item (disclosure, #ad, credits, licenses, banned claims). Then the account's review tier decides: approve every item, spot-check about 10%, or post automatically. A new account, format or producer version always starts in full review. | Planned (S2). Today every clip is checked by hand on the phone. |
| **Publish** | Each item goes to every platform the account has enabled, at the account's posting slots, through a posting API (Upload-Post), with the AI labels each platform requires. | Today: the Telegram posting assistant sends each clip to the owner's phone at its slot, and the owner posts it by hand. API publishing is S2. |
| **Measure** | Daily analytics per post and account, tracked links for clicks and sales, cost per item and per account, and progress toward each platform's payout program. | Cost is logged per job today. The rest is planned (S7). |
| **Scale** | Winners (the top 10% per account after 7 days) get more of the same format, Spanish or English dubs for the paired account, and feed a learned ranker. New accounts start from existing blueprints. | Planned (S7, S10). New accounts can be created from blueprints now (S1). |

## Account types

An account is never designed from scratch. It is a **blueprint** (niche, content pillars, rotating series formats, voice and visual style, money sources, compliance profile) plus a language, a persona, handles, a posting schedule, a budget and a review tier:

```
type (clips · story · band · avatar · model)  →  blueprint  →  account  →  series  →  item (one video)
```

| Type | What a video is | How it's produced | How it earns | Rules it must follow | Status |
|---|---|---|---|---|---|
| **Podcast clips** | 30–60 s cut from a long video the account has permission to use | transcribe → pick the strongest moments → frame to 9:16 on the speaker → captions and hook title → render | Paid clipping deals, affiliate links, brand deals | Creator credited in every caption; source permission on record | **Live** (realtalk.clipsdaily) |
| **AI stories** | A 61–90 s narrated original script over stills and b-roll, with a music bed | brief → script → voice → images and b-roll → music → render | TikTok and Facebook creator payouts, later YouTube long-form | Fact sources stored; AI label on; structure varied per video | Planned (S6) |
| **Band discovery** | A narrated story about an unknown band, over permitted photos or generated art; music added in the app | research → licensed assets → script → voice → art → render | Disclosed paid features, gear affiliate links | A license for every asset; no photoreal images of real people | Planned (S9) |
| **AI-avatar affiliate** | A disclosed synthetic presenter (hook and call to action) plus b-roll, selling a product or community | brief → script → claim check → voice → talking head → b-roll → render | Commission per sale, through tracked links | AI label; #ad; no first-person testimonials; no health or earnings claims | Planned (S8) |
| **AI model persona** | Carousels and short reels of a disclosed synthetic persona | persona (designed voice, generated face) → images and reels | Brand deals, affiliate storefronts | "AI creator" in the bio; provenance metadata kept; synthetic-only training data | Planned (S13) |

Today's accounts and the planned launch waves: [docs/studio/09-account-registry.md](docs/studio/09-account-registry.md). Why each concept exists, and how the portfolio scales: [docs/studio/07-channel-portfolio.md](docs/studio/07-channel-portfolio.md).

## What's built

| Built and in use | Built, not live yet | In progress | Planned |
|---|---|---|---|
| The clip producer, on the Timeline renderer (S4) · batch clipping by channel · the Telegram posting assistant (one clip per slot, ✅ per platform) · ops alerts to the phone · cost logging per job | Postgres for accounts, sources, the posting queue and job records (S1; rollout: card 010) · accounts from blueprints · the dashboard shell (S3a; Vercel deploy pending) | S2 design (card 011) · the visuals and music spike (card 012) | Review tiers and API publishing (S2) · the dashboard (S3) and per-account workspaces with experiments (S3c) · media servers (S5) · the story, avatar, band, dub and model producers (S6, S8–S10, S13) · analytics, money and budgets (S7) |

Week-to-week progress: [STATUS.md](STATUS.md). The build order: [ROADMAP.md](ROADMAP.md) and [docs/studio/04-roadmap.md](docs/studio/04-roadmap.md).

## How it's built

- **Producers vs distribution.** Every producer ends in a `ContentItem`. Review, publishing and measurement only consume ContentItems, so a new account type is a new producer and nothing else (ADR-25).
- **One renderer.** Every producer describes its video as a `Timeline`, and one renderer turns any Timeline into an mp4, so captions, loudness and size limits stay the same everywhere (ADR-31).
- **Serverless steps.** Each production step is its own Modal function. Steps are cached by their inputs, so a retry or a re-cut never redoes finished work, and GPUs (transcription, voice, images, talking heads) are billed by the second (ADR-9, ADR-12).
- **Durable state in Postgres** (Neon) for accounts, items, posts, metrics and costs. The Modal Dict holds only short-lived step state (ADR-26).
- **Open media models on Modal**, each one checked against a license allowlist (ADR-30), instead of paid voice and avatar services.
- **One home per task:** the dashboard runs everything that needs context, and Telegram handles time-bound decisions, alerts and the brake (ADR-44).

Today's system in detail: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). The target design: [docs/studio/02-target-architecture.md](docs/studio/02-target-architecture.md).

## Using it

What runs today (clipping videos, the Telegram posting assistant, first-time setup, development): [docs/usage.md](docs/usage.md). Every owner step and command, in order: [docs/studio/11-owner-runbook.md](docs/studio/11-owner-runbook.md).

Development work runs as cards: each card is the brief for one Claude Code session, on its own branch, ending in a pull request that must pass `scripts/check.sh`. How that works: [CLAUDE.md](CLAUDE.md) and [docs/cards/](docs/cards/README.md).

## Where to find things

| Question | Where |
|---|---|
| Where do things stand right now? | [STATUS.md](STATUS.md) |
| How do I use what's built? | [docs/usage.md](docs/usage.md) |
| How does the system work today? | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Where is it going, and why? | [docs/studio/](docs/studio/README.md): vision and money (01), target design (02), tools and models (03), portfolio (07), dashboard (08) |
| Why was it built this way? | [docs/DECISIONS.md](docs/DECISIONS.md) (ADRs) and [docs/studio/10-decision-log.md](docs/studio/10-decision-log.md) (every owner decision) |
| What's next? | [ROADMAP.md](ROADMAP.md), and [docs/studio/04-roadmap.md](docs/studio/04-roadmap.md) for the studio phase |
| Which accounts exist? | [docs/studio/09-account-registry.md](docs/studio/09-account-registry.md) |
| What does the owner do, and how? | [docs/studio/11-owner-runbook.md](docs/studio/11-owner-runbook.md) |
| What is each session doing? | [docs/cards/](docs/cards/README.md) and [docs/reports/](docs/reports/README.md) |
| Which secret lives where, and what was deployed? | [docs/ops/secrets.md](docs/ops/secrets.md) and [docs/ops/deploys.md](docs/ops/deploys.md) |
| Designs and implementation plans | [docs/superpowers/](docs/superpowers/README.md) |
| Clip quality, content permissions, prompts | [docs/EVALS.md](docs/EVALS.md), [docs/SOURCING.md](docs/SOURCING.md), [prompts/](prompts/) |
