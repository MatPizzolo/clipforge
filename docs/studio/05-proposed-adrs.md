# 05: Proposed ADRs

Accepted in the 2026-09-29 kickoff review: ADR-25, 26, 28, 29, 30, 31, 34, 35, 38, 39. Accepted later: ADR-41 (S1, written into `docs/DECISIONS.md` by card 002 on 2026-09-30) and ADR-42 to ADR-46 (2026-09-30), ADR-47 (two-pass loudness, 2026-10-01), ADR-48 to ADR-50 (autopilot, the producer-version window, the hook library; 2026-10-01), and ADR-27 (the dispatcher) and ADR-33 (tracking links only) with card 011's S2 spec (2026-10-02), and ADR-54 (Telegram is notifications only; owner ruling, 2026-10-05). Accepted ADRs live only in `docs/DECISIONS.md`, which is binding; this file keeps one-line pointers to them, except ADR-43 to ADR-46. The drafts left are ADR-36, 37, 40, 51, 52 and 53 (proposed) and ADR-32 (deferred). The next free number is ADR-55. To accept a draft, copy it into `docs/DECISIONS.md` with `Status: Accepted` and the acceptance date. ADR-24 is already taken by the Dict keep-alive (plan C Task 6).

---

**ADR-25: Multi-account studio with one content-item seam**: accepted 2026-09-29; the text is only in [DECISIONS.md](../DECISIONS.md#adr-25-multi-account-studio-with-one-content-item-seam).

**ADR-26: Postgres (Neon) for durable state; Dict only for hot step state**: accepted 2026-09-29; the text is only in [DECISIONS.md](../DECISIONS.md#adr-26-postgres-neon-for-durable-state-dict-only-for-hot-step-state).

**ADR-27: One dispatcher cron**: accepted 2026-10-02 with card 011's S2 spec; the text is only in [DECISIONS.md](../DECISIONS.md#adr-27-one-dispatcher-cron).

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

**ADR-33: Tracking links**: accepted 2026-10-02 with card 011's S2 spec, as tracking links only; the text is only in [DECISIONS.md](../DECISIONS.md#adr-33-tracking-links). Its conversion-import half is draft ADR-51 below.

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

## ADR-51: Conversion import
Date: 2026-10-01 · Status: Proposed (split from ADR-33 on 2026-10-01; build in S7)
Context: ADR-33's tracking links count clicks; money per video and per account also needs the sales those clicks produced.
Decision: Import conversions from programs with APIs (ClickBank, Hotmart) on a daily dispatcher task, and from CSV uploads otherwise (Skool, Amazon, TikTok Shop), matching each sale to a link by its sub-id. Store them in a `conversions` table with the program, amount, currency, time and sub-id.
Consequences: Revenue per video and per account in the dashboard, which is the "scale the winners" loop; the per-program importers are maintained as the programs change.

## ADR-52: Media servers and the producer registry
Date: 2026-10-03 · Status: Proposed (card 021's S5 spec, `docs/superpowers/specs/2026-10-02-studio-s5-design.md` §10; refines ADR-12 and ADR-30; built in S5)
Context: ADR-30 runs open media models as `modal.Cls` servers, and ADR-12's step chain is hard-coded for clips. S6 onwards add producers whose GPU steps run on models with cold starts of 20 s to 3 minutes (measured by card 021's probe), at 1–2 items per account per day.
Decision:
- Every producer is a list of steps in a Modal-free registry (`producers/registry.py`), run by one engine (`pipeline/engine.py`: guard, hand-off, fan-out, fan-in, resume, sweep). Clips keep their step names, keys and `producer_version`.
- A GPU step runs inside its media server's class as `run_step`, one item per call. Each server has `max_containers` (default 1), `max_batch_items` and `scaledown_window` in `media/registry.toml`, so a batch of items reuses one warm container; the window is the gap between items plus a margin. The sweeper bounds queued steps by the batch cap and running steps by their timeout.
- Memory snapshots are chosen per server by measurement: CPU snapshots by default, GPU snapshots (alpha) only where a measurement shows they pay for their creation cost.
- Derived weights (fused LoRAs, converted precisions) are prepared once on the `clipforge-models` Volume with a manifest that servers check at startup; servers mount the Volume read-only and never download.
- No `@modal.batched` until there are many small concurrent calls.
Consequences: a new producer is a step list and handlers; a new model is a registry entry and an adapter. Cold starts are paid once per batch, and the idle tail is bounded by the window. One server per model family means S6's b-roll and S8's talking head reuse the pattern.

## ADR-53: LLM tracing in Langfuse
Date: 2026-10-05 · Status: Proposed (moved out of S5 by the owner on 2026-10-05, log #597; for the owner to accept or reject; if accepted, built in an optional card after S6)
Context: Every stage already records LLM tokens and cost per stage in `metadata.json` and the `jobs` table (rule 7). S6 adds scripts, copy and the Judge, where prompt iteration is daily work and a per-call view (prompt version, latency, failures, retries) helps. Langfuse (MIT core) has a hosted free tier.
Decision (proposed):
- **Vendor and region:** Langfuse Cloud, Hobby plan ($0, 50k units a month), in the US region (`https://us.cloud.langfuse.com`), the nearest to Modal; the self-hosted option stays rejected (it needs a server, Postgres and ClickHouse, against ADR-9).
- **Where:** a `TracingLLMClient` wrapping any `LLMClient` in `llm.py`; the protocol gains an optional `meta` argument (prompt name and version, job, clip and stage ids). Off unless the keys exist.
- **Fields sent:** prompt `name@version`, model, input and output tokens, estimated USD, latency, job/clip/stage ids, and the error class on a failed call. **No prompt or completion text** unless `LANGFUSE_CAPTURE_IO=true`, an owner switch that stays off (transcripts and scripts stay in our storage).
- **Retention:** Hobby's data retention as published (30 days at the time of writing); nothing in Langfuse is a record we need: `metadata.json` and the `jobs` table stay the cost record.
- **Secrets:** `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST` in `clipforge-secrets`, added by the `docs/ops/secrets.md` procedure.
- **Failure:** the wrapper flushes at the end of each step (2 s cap); an exporter error is logged and never fails a call or a step.
Consequences: one more vendor that sees metadata only, a dashboard of calls per prompt version, and an off switch (remove the keys). Rejecting it leaves today's per-stage cost records as the only LLM telemetry.
