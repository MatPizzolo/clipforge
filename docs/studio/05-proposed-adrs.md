# 05: Proposed ADRs

Accepted in the 2026-09-29 kickoff review: ADR-25, 26, 28, 29, 30, 31, 34, 35, 38, 39. Accepted later: ADR-41 (S1, written into `docs/DECISIONS.md` by card 002 on 2026-09-30) and ADR-42 to ADR-46 (2026-09-30), ADR-47 (two-pass loudness, 2026-10-01), and ADR-48 to ADR-50 (autopilot, the producer-version window, the hook library; 2026-10-01). Accepted ADRs live only in `docs/DECISIONS.md`, which is binding; this file keeps one-line pointers to them, except ADR-43 to ADR-46. The drafts left are ADR-27, 33, 36, 37 and 40 (proposed) and ADR-32 (deferred). The next free number is ADR-51. To accept a draft, copy it into `docs/DECISIONS.md` with `Status: Accepted` and the acceptance date. ADR-24 is already taken by the Dict keep-alive (plan C Task 6).

---

**ADR-25: Multi-account studio with one content-item seam**: accepted 2026-09-29; the text is only in [DECISIONS.md](../DECISIONS.md#adr-25-multi-account-studio-with-one-content-item-seam).

**ADR-26: Postgres (Neon) for durable state; Dict only for hot step state**: accepted 2026-09-29; the text is only in [DECISIONS.md](../DECISIONS.md#adr-26-postgres-neon-for-durable-state-dict-only-for-hot-step-state).

## ADR-27: One dispatcher cron
Date: 2026-09-29 · Status: Proposed
Context: Modal Starter allows 5 deployed crons. Today there is 1 (sweeper); plan C makes it 3. Analytics pulls, digests and budget checks would exceed 5.
Decision: When a 5th periodic task is needed (S7), one `dispatcher` function runs every 5 minutes and calls each periodic task when it's due. Last-run markers live in the Dict, and the dispatcher opens a database connection only when a task is due, so Neon can still scale to zero.
Consequences: Adding a periodic task needs no new cron. One slow task can delay the others, so each task has a time budget and heavy work is spawned.

**ADR-28: Publishing through Upload-Post behind a Publisher protocol**: accepted 2026-09-29; the text is only in [DECISIONS.md](../DECISIONS.md#adr-28-publishing-through-upload-post-behind-a-publisher-protocol).

**ADR-29: Tiered review with an always-on policy gate**: accepted 2026-09-29; the text is only in [DECISIONS.md](../DECISIONS.md#adr-29-tiered-review-with-an-always-on-policy-gate).

**ADR-30: Self-hosted open media models on Modal, license-gated**: accepted 2026-09-29; the text is only in [DECISIONS.md](../DECISIONS.md#adr-30-self-hosted-open-media-models-on-modal-license-gated).

**ADR-31: Timeline as the single render input**: accepted 2026-09-29; the text is only in [DECISIONS.md](../DECISIONS.md#adr-31-timeline-as-the-single-render-input).

## ADR-32: Two LLM quality levels
Date: 2026-09-29 · Status: Deferred (kickoff review: bulk text is under $5/month even at 19 accounts; revisit if LLM spend passes $50/month)
Context: Claude Haiku already costs cents per job. Free tiers (Gemini, Groq, OpenRouter) have unstable limits, retire models, and sometimes train on prompts.
Decision:
- **Quality-level** stages (highlights, scripts, copy, translation, claim checks) use pinned Claude models, with the model in the cache key and an eval gate before any change.
- **Bulk-level** stages (hashtag and title variants, research summaries) go through a router over free tiers. It backs off using rate-limit headers and falls back to Haiku.
- Only public content goes to free tiers.
Consequences: Small savings with no quality risk where it matters. The router is one small module behind `LLMClient`.

## ADR-33: Tracking links and conversion import
Date: 2026-09-29 · Status: Proposed
Context: Affiliate money needs attribution per video, and a single link in the bio can't provide it. Vercel Hobby forbids affiliate use.
Decision:
- `GET /go/<slug>` on the Modal web app logs the click (item, platform, time, coarse country) and returns a 302 to the affiliate URL with a sub-id.
- Conversions are imported from APIs where they exist (ClickBank, Hotmart) and from CSV otherwise (Skool, Amazon, TikTok Shop).
Consequences: Revenue per video and per account in the dashboard, which is the "scale the winners" loop.

**ADR-34: Local download helper**: accepted 2026-09-29; the text is only in [DECISIONS.md](../DECISIONS.md#adr-34-local-download-helper).

**ADR-35: Channels as blueprint instances**: accepted 2026-09-29; the text is only in [DECISIONS.md](../DECISIONS.md#adr-35-channels-as-blueprint-instances).

## ADR-36: Judge protocol for decisions, with TypeSafe Jev as a candidate
Date: 2026-09-29 · Status: Proposed (build in S6 with the first AI content; Jev adoption depends on spike X5)
Context: Gate checks, review routing, variant ranking and tagging are typed decisions, not text. Tiered review (ADR-29) needs calibrated confidence to know when to auto-post. Jev (TypeSafe, early access since 2026-09-15) returns typed answers with calibrated probabilities at ~$0.04 per M tokens. It's a hosted, early-stage vendor with vendor-run benchmarks.
Decision: A `Judge` protocol with `choice`, `score` and `noul` methods, each returning a value, probabilities and a confidence. `ClaudeJudge` (Haiku) ships first. `JevJudge` is added and set as the default per decision only if X5 shows equal or better accuracy and calibration, in English and Spanish. Thresholds are configured per decision and scale with the cost of a wrong action. Only public content is sent.
Consequences: Cheap, fast, calibrated routing if Jev holds up, and no lock-in if it doesn't. Text generation stays with Claude.

## ADR-37: Decision ledger, lanes, audit sampling and fail-closed
Date: 2026-09-29 · Status: Proposed (refines ADR-29 and ADR-36; build in S6)
Context: Automated review and gating can only be trusted if each decision is recorded, silent mistakes are measured, and failures go to a person. Cheap judges make decisions almost free, so cost and risk sit in the escalations ("Jev Desk" analysis).
Decision:
- Every Judge call writes a `decisions` row: questions, answers with confidences, lane, model version, tokens, cost and a later outcome.
- Content lanes: `publish`, `review`, `fix`, `reject`. Desk lanes: `ignore`, `log`, `draft`, `human`.
- Errors and timeouts fail closed to a human.
- Parallel questions that disagree escalate the item.
- About 5% of `publish` and about 1% of `ignore` decisions are sampled for audit, which measures the false-pass and false-ignore rates.
- Thresholds are cost settings, changed one at a time and checked against the audit.
- A daily Telegram morning message reports the cost split, the escalation rate and audit findings.
Consequences: The auto-post rate becomes a measured, tunable number. Adds one table and a daily job.

**ADR-38: Next.js as the operational dashboard, Notion as a one-way mirror**: accepted 2026-09-29; the text is only in [DECISIONS.md](../DECISIONS.md#adr-38-nextjs-as-the-operational-dashboard-notion-as-a-one-way-mirror).

**ADR-39: AI model / influencer category with provenance kept**: accepted 2026-09-29; the text is only in [DECISIONS.md](../DECISIONS.md#adr-39-ai-model--influencer-category-with-provenance-kept).

## ADR-40: Funnel and own products (deferred build)
Date: 2026-09-29 · Status: Proposed (build in S14)
Context: Affiliate commissions cap the upside. Channels such as profe.ia.ingles, ai.tools.lab and realtalk.clipsdaily could feed their own course or community.
Decision: Plan a funnel module (bio pages, email capture, sequences, sales import) and use the studio's producers to make lesson videos. Build it after the channels show traction. Guardrails: no invented testimonials or statistics, no fake scarcity, guarantees only after legal review, no spam link-dropping.
Consequences: The architecture reserves `funnel/` and the dashboard reserves a Funnel page. No work until S14.

**ADR-41: Moving to Postgres by writing to both stores, and posting per account**: accepted with S1, written into DECISIONS.md by card 002 on 2026-09-30; the text is only in [DECISIONS.md](../DECISIONS.md#adr-41-moving-to-postgres-by-writing-to-both-stores-and-posting-per-account).

**ADR-42: Versioned categories, blueprints and accounts in the database**: accepted 2026-09-30; the text is only in [DECISIONS.md](../DECISIONS.md#adr-42-versioned-categories-blueprints-and-accounts-in-the-database).
