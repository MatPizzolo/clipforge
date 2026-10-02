# ClipForge Studio: planning pack

ClipForge is a studio for running and growing many short-video channels: 20+ accounts across TikTok, Instagram Reels, YouTube Shorts and Facebook Reels, in English (US) and Spanish. Each channel is an account of one type (podcast clips, AI stories, band discovery, AI-avatar affiliate, AI model persona), built from a blueprint, and every account runs the same loop: produce → review → publish → measure → scale. Everything runs on Modal, with a Next.js dashboard on Vercel and Telegram as the phone surface. Today the podcast-clips type and its posting assistant are live; this folder plans the rest (the short version is in the [README](../../README.md)).

This folder is the input for new Claude Code sessions. It was written on 2026-09-29 from a brainstorm with the owner plus web research. The kickoff review (2026-09-29) re-checked the facts, corrected the pack, and accepted ADR-25, 26, 28, 29, 30, 31, 34, 35, 38 and 39 into `docs/DECISIONS.md`. ADR-41 (S1) and ADR-42 to ADR-46 were accepted on 2026-09-30. ADR-27, 33, 36, 37 and 40 stay proposed (built later), and ADR-32 is deferred. ADR-47 to ADR-50 were accepted on 2026-10-01. The next free number is ADR-51. Anything not in `docs/DECISIONS.md` is still a proposal.

| File | What it holds |
|---|---|
| [01-vision-and-strategy.md](01-vision-and-strategy.md) | Goals, account types, monetization per platform, content rules |
| [02-target-architecture.md](02-target-architecture.md) | Target system design: components, contracts, data, flows |
| [03-tools-and-models.md](03-tools-and-models.md) | Chosen tools and open models, with licenses, GPUs, costs and sources |
| [04-roadmap.md](04-roadmap.md) | Sub-projects in build order, with exit criteria |
| [05-proposed-adrs.md](05-proposed-adrs.md) | ADR drafts still open (27, 32 deferred, 33, 36, 37, 40), pointers to the accepted ones, and the next free number (ADR-51) |
| [06-session-prompts.md](06-session-prompts.md) | Prompts A–I plus one action card per roadmap item (S0–S14, X1–X6) and the close-out checklist; the coordinator builds cards in `docs/cards/` from them |
| [07-channel-portfolio.md](07-channel-portfolio.md) | 15 channel concepts in 5 categories, EN/ES pairs, blueprint scaling model, launch waves |
| [08-dashboard-and-operations.md](08-dashboard-and-operations.md) | Decision ledger, lanes and audit; dashboard pages; Notion mirror; the Desk; funnel and own products |
| [09-account-registry.md](09-account-registry.md) | **What exists:** the 5 categories (with code names) and all 19 accounts with ids, handles, platforms, money, sources, waves and status |
| [10-decision-log.md](10-decision-log.md) | **Every owner decision**, dated, with status (current, superseded, open) and where it's recorded |
| [11-owner-runbook.md](11-owner-runbook.md) | **Every owner step and command**, in order: where secrets go, daily Telegram and CLI use, S1 rollout, dashboard setup, publishing prep, spikes, the git repo and GitHub |

## How to use

1. **Kickoff (done 2026-09-29):** prompt **A** from `06-session-prompts.md` reviewed this pack against the code and turned the accepted ADRs into `docs/DECISIONS.md`. Prompt **G** mirrors the settled pack to Notion (card S3b).
2. **Every session starts from a card:** `Run card docs/cards/NNN-….md` (see [docs/cards/README.md](../cards/README.md)). The coordinator builds each card from the matching prompt (**B** build, **C** spike) and **action card** in 06 §D. A card lists its branch, scope, dependencies, owner steps, numbered actions, checkpoints, a done-when check and a cost cap.
3. **Other prompts:** **E** launches an account from a blueprint. **F** is the weekly review. **H** is for incidents. **I** is a quick status check. They become cards the same way.
4. Every session ends with a hand-off report in `docs/reports/` and the **close-out checklist** in 06.

## Decisions

All owner decisions, including the ones that changed, are in [10-decision-log.md](10-decision-log.md). Architecture decisions are ADRs in [docs/DECISIONS.md](../DECISIONS.md). Every account, and each category's rules, is in [09-account-registry.md](09-account-registry.md). When a session makes or changes a decision, it adds a row to 10 (and updates 09 if an account changes).
