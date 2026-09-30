# 05: Proposed ADRs

Accepted in the 2026-09-29 kickoff review: ADR-25, 26, 28, 29, 30, 31, 34, 35, 38, 39 (now in `docs/DECISIONS.md`, which is binding). **Taken:** ADR-43 (derived producer version), ADR-44 (one home per task), ADR-45 (notification budget and ops alerts) and ADR-46 (daily reconcile) were accepted on 2026-09-30 and live only in `docs/DECISIONS.md`. The next free number is ADR-47. Reserved numbers: **ADR-41** is S1's ("reads come from `STATE_READS`, one writer per column group"; the code cites it already; S1 writes it into `docs/DECISIONS.md` in its Task 21). **ADR-42** is the S3 workspaces decision (the database holds versioned categories, blueprints and accounts; replaces ADR-35's "blueprints are files" part), drafted by the S3 design session. The rest are drafts. To accept one, copy it into `docs/DECISIONS.md` with `Status: Accepted` and the acceptance date. ADR-24 is already taken by the Dict keep-alive (plan C Task 6).

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

## ADR-42: Versioned categories, blueprints and accounts in the database
Date: 2026-09-30 · Status: Proposed (design approved 2026-09-30; built in S3c; replaces ADR-35's "blueprints are files" part)
Context: Each account type is very different, and the owner wants to improve every category and every account from the dashboard: edit the setup, keep notes, run experiments and see results. ADR-35 keeps blueprints as files (`blueprints/<name>.toml`), and S1 copies blueprint values into each account row and updates accounts in place, so there is no history, no way to tie a video to the setup that made it, and no dashboard editing. Spec: docs/superpowers/specs/2026-09-30-studio-s3-workspaces-design.md.
Decision:
- The database is the source of truth for three versioned levels: **category** (the 5 fixed codes: playbook, rules = compliance profile, production defaults), **blueprint** (pillars, series formats, briefs, money, prompts) and **account** (overrides plus identity fields). Effective setup = category, overridden by blueprint, overridden by account; the dashboard shows each value's origin.
- Every save writes a full, validated snapshot with an author and a note, in append-only `*_versions` tables. Restore saves an old version as a new one; history is never rewritten.
- **Accounts pin their parent versions:** an account version records the category and blueprint versions it builds on. Parent saves reach accounts through an explicit "Apply to accounts". `(account_id, version)` fully determines the setup and is stamped on every content item (`content_items.setup_version`) and on every send (`post_events.data.setup_version`).
- The setup is frozen per job at `create_job`, feeds only existing cache-key inputs (ADR-8) and is never part of a cache key. Prompts stay versioned files (CLAUDE.md rule 4); the setup only picks a released version.
- Every field has a change class (live, recut, format, rules, identity). Format changes send the first 10 items to `review` (ADR-29, enforced by S2); rules are never experimented on.
- Experiments (change → metric over a window → keep or revert, one running per account) and notes (idea, learning, question) live in the same database.
- S1's `blueprints/*.toml` and account rows are imported once as version 1 (`clipforge setup import`, `setup verify` at 0 differences), like `channels.toml` became sources. After that the files are no longer read; they stay in the repo until the move has been verified for 7 days.
Consequences: Every video can be traced to the exact setup that made it, and experiments can isolate their accounts. The accounts table becomes a projection of the current version with one writer (ADR-41). Blueprint changes are reviewed as version diffs in the dashboard instead of file diffs. A `SETUP_SOURCE=db|off` switch lets producers fall back to today's constants. Updates ADR-35: channels are still blueprint instances, but blueprints live in the database. `setup_version` (which setup) stays separate from `producer_version` (which code, derived per ADR-43); per ADR-44, setup edits and experiment decisions are dashboard tasks, and Telegram only deep-links to them.
