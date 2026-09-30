# ClipForge Studio: planning pack

ClipForge today turns long videos into 9:16 clips for one brand. **ClipForge Studio** extends it into a multi-account content studio. It produces, reviews, publishes and measures short vertical videos for 20+ accounts across TikTok, Instagram Reels, YouTube Shorts and Facebook Reels, in English (US) and Spanish. Everything runs on Modal, with a Next.js dashboard on Vercel and Telegram as the phone surface.

This folder is the input for new Claude Code sessions. It was written on 2026-09-29 from a brainstorm with the owner plus web research. The kickoff review (2026-09-29) re-checked the facts, corrected the pack, and accepted ADR-25, 26, 28, 29, 30, 31, 34, 35, 38 and 39 into `docs/DECISIONS.md`. ADR-27, 33, 36, 37 and 40 stay proposed (built later), and ADR-32 is deferred. Anything not in `docs/DECISIONS.md` is still a proposal.

| File | What it holds |
|---|---|
| [01-vision-and-strategy.md](01-vision-and-strategy.md) | Goals, account types, monetization per platform, content rules |
| [02-target-architecture.md](02-target-architecture.md) | Target system design: components, contracts, data, flows |
| [03-tools-and-models.md](03-tools-and-models.md) | Chosen tools and open models, with licenses, GPUs, costs and sources |
| [04-roadmap.md](04-roadmap.md) | Sub-projects in build order, with exit criteria |
| [05-proposed-adrs.md](05-proposed-adrs.md) | ADR drafts (ADR-25 to ADR-40) to accept, change or reject |
| [06-session-prompts.md](06-session-prompts.md) | Prompts A–I plus one action card per roadmap item (S0–S14, X1–X6) and the close-out checklist |
| [07-channel-portfolio.md](07-channel-portfolio.md) | 15 channel concepts in 5 categories, EN/ES pairs, blueprint scaling model, launch waves |
| [08-dashboard-and-operations.md](08-dashboard-and-operations.md) | Decision ledger, lanes and audit; dashboard pages; Notion mirror; the Desk; funnel and own products |
| [09-account-registry.md](09-account-registry.md) | **What exists:** the 5 categories (with code names) and all 19 accounts with ids, handles, platforms, money, sources, waves and status |
| [10-decision-log.md](10-decision-log.md) | **Every owner decision**, dated, with status (current, superseded, open) and where it's recorded |
| [11-owner-runbook.md](11-owner-runbook.md) | **Every owner step and command**, in order: where secrets go, daily Telegram and CLI use, S1 rollout, dashboard setup, publishing prep, spikes, creating the git repo |

## How to use

1. **Kickoff (once):** start a new Claude Code session in the repo root and paste prompt **A** from `06-session-prompts.md`. It reviews this pack against the code, re-checks the facts, and turns the accepted ADRs into `docs/DECISIONS.md`. Then run prompt **G** to mirror the settled pack to Notion (card S3b).
2. **Every later session:** paste prompt **B** (build) or **C** (spike), then the matching **action card** from §D. Each card lists its dependencies, what you have to do first, numbered actions, a done-when check and a cost limit.
3. **Other prompts:** **E** launches an account from a blueprint. **F** is the weekly review. **H** is for incidents. **I** is a quick status check.
4. Every session ends with the **close-out checklist** in 06.

## Decisions

All owner decisions, including the ones that changed, are in [10-decision-log.md](10-decision-log.md). Architecture decisions are ADRs in [docs/DECISIONS.md](../DECISIONS.md). Every account, and each category's rules, is in [09-account-registry.md](09-account-registry.md). When a session makes or changes a decision, it adds a row to 10 (and updates 09 if an account changes).
