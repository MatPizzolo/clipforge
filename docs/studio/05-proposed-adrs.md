# 05: Proposed ADRs

Accepted in the 2026-09-29 kickoff review: ADR-25, 26, 28, 29, 30, 31, 34, 35, 38, 39 (now in `docs/DECISIONS.md`, which is binding). **Taken:** ADR-43 (derived producer version), ADR-44 (one home per task), ADR-45 (notification budget and ops alerts) and ADR-46 (daily reconcile) were accepted on 2026-09-30 and live only in `docs/DECISIONS.md`. The next free number is ADR-47. Reserved numbers: **ADR-41** is S1's ("reads come from `STATE_READS`, one writer per column group"; the code cites it already; S1 writes it into `docs/DECISIONS.md` in its Task 21). **ADR-42** is the S3 workspaces decision (the database holds versioned categories, blueprints and accounts; replaces ADR-35's "blueprints are files" part), drafted by the S3 design session. The rest are drafts. To accept one, copy it into `docs/DECISIONS.md` with `Status: Accepted` and the acceptance date. ADR-24 is already taken by the Dict keep-alive (plan C Task 6).

---

## ADR-25: Multi-account studio with one content-item seam
Date: 2026-09-29 · Status: Accepted (2026-09-29; copied to docs/DECISIONS.md)
Context: ClipForge serves one brand from one producer (podcast clips). The owner wants 20+ accounts across four kinds (clips, AI stories, bands, AI-avatar affiliate) in English and Spanish, all from one repo.
Decision:
- Every producer ends in a `ContentItem`: video, per-platform copy, AI-disclosure and sponsored flags, credits, asset licenses, cost, account.
- Distribution (queue, review, publish, analytics) consumes only `ContentItem`s.
- An `Account` holds its platforms and per-platform rules, review tier, persona, brand kit, budget and paired-language account.
- `channels.toml` sources become `sources` rows owned by accounts.
Consequences: New content types are new producers only. The clip producer gains a small wrapper step. The ADR-23 `PostItem` is replaced by `ContentItem` + `posts` rows.

## ADR-26: Postgres (Neon) for durable state; Dict only for hot step state
Date: 2026-09-29 · Status: Accepted (2026-09-29; copied to docs/DECISIONS.md; supersedes ADR-5; retires ADR-24 once migrated)
Context: Modal Dict entries expire after 7 days of inactivity, and ADR-24 works around that with keep-alives. The dashboard needs queries across accounts, dates and platforms (calendar, stats, money) that a key-value scan can't serve. Modal Volumes aren't safe for a database with many writers.
Decision: Neon Postgres, reached through the pooled endpoint with SQLAlchemy 2 + psycopg 3, holds everything durable. Migrations use Alembic. The Dict keeps only in-flight job and step keys and claims (ADR-14); `job:*` summaries move to a `jobs` table too, so nothing durable depends on a Dict entry surviving 7 idle days. The dashboard reaches the data only through the FastAPI API (ADR-2).
Consequences: One new managed dependency, free until it's outgrown. Tests need a local Postgres, and CI a Postgres service. Alembic runs in the deploy job before `modal deploy`. During the switch a setting points reads back at the Dict for rollback. The ADR-24 keep-alive and snapshot are removed a week after the migration is verified.

## ADR-27: One dispatcher cron
Date: 2026-09-29 · Status: Proposed
Context: Modal Starter allows 5 deployed crons. Today there is 1 (sweeper); plan C makes it 3. Analytics pulls, digests and budget checks would exceed 5.
Decision: When a 5th periodic task is needed (S7), one `dispatcher` function runs every 5 minutes and calls each periodic task when it's due. Last-run markers live in the Dict, and the dispatcher opens a database connection only when a task is due, so Neon can still scale to zero.
Consequences: Adding a periodic task needs no new cron. One slow task can delay the others, so each task has a time budget and heavy work is spawned.

## ADR-28: Publishing through Upload-Post behind a Publisher protocol
Date: 2026-09-29 · Status: Accepted (2026-09-29; copied to docs/DECISIONS.md; updates ADR-3 and ADR-23's "API publishing gets its own ADR")
Context: TikTok's own API allows only private posts until an app audit passes. Doing that audit and Meta's app review ourselves is slow. At ~25 accounts × 4 platforms, Upload-Post costs about $50–147/mo. Alternatives: Zernio (~$318/mo), Ayrshare (~$599/mo), self-hosted Postiz (we'd need our own audits).
Decision:
- A `Publisher` protocol with two implementations: `UploadPostPublisher` (primary) and `AssistedPublisher` (the Telegram manual flow from ADR-23).
- Media is served by URL: signed, expiring Volume links first (ADR-13's mechanism), Cloudflare R2 only if those prove unreliable.
- `ai_disclosure` maps to every platform's AI flag.
- Signed webhooks update the `posts` rows.
Consequences: A vendor dependency that can be swapped. Official YouTube and Instagram publishers can be added later behind the same protocol.

## ADR-29: Tiered review with an always-on policy gate
Date: 2026-09-29 · Status: Accepted (2026-09-29; copied to docs/DECISIONS.md)
Context: At 20+ accounts, approving every post by hand is 100+ taps a day. Platforms punish undisclosed AI, mass-produced content and false claims.
Decision:
- Each account has a review tier: `review` (every item), `sample` (auto-post, ~10% spot checks, daily digest) or `auto`.
- A new account, a new format and a new producer version all start in `review`.
- A pure policy gate runs on every item. The LLM claim check joins it with the Judge (ADR-36) in S6, when AI content first appears; clips make no product claims. It checks disclosure, #ad, credits, license manifest, cross-account duplicates, and health and earnings claims.
- Any violation sends the item to `review`.
Consequences: Owner time scales with how new the content is, not with volume. Reject reasons feed the ranker.

## ADR-30: Self-hosted open media models on Modal, license-gated
Date: 2026-09-29 · Status: Accepted (2026-09-29; copied to docs/DECISIONS.md)
Context: The owner rules out paid voice and avatar SaaS, and the target is 20+ accounts. Open models now cover voice (Qwen3-TTS), images (Z-Image), talking heads (InfiniteTalk), music (ACE-Step) and b-roll (Wan2.2). Many popular models are non-commercial (InsightFace packs, FLUX.1-dev, Qwen-Image 2.1, F5-TTS, XTTS, MusicGen).
Decision:
- Each model runs as a `modal.Cls` media server, with weights on a `clipforge-models` Volume, memory snapshots, and GPU step methods inside the class so nothing waits idle (ADR-12).
- Stage logic uses Modal-free protocols in `media/`.
- `media/registry.toml` pins every model's revision and license. A test fails for licenses outside the allowlist.
- Personas are fully synthetic (a designed voice and a generated face with a LoRA).
Consequences: Cents per video instead of a subscription per seat. We maintain GPU images and pins. Spikes X1–X4 must confirm quality and cost before each producer is built.

## ADR-31: Timeline as the single render input
Date: 2026-09-29 · Status: Accepted (2026-09-29; copied to docs/DECISIONS.md)
Context: Clips crop a source video, while stories, bands and avatars assemble stills, generated clips, talking heads, narration and music. Separate renderers would drift apart in captions, loudness and size limits (ADR-18/20).
Decision: A `Timeline` contract (visual segments, audio tracks, captions, title card, asset sources) is the only input to `render`. The clip producer moves onto it first, keeping identical output properties.
Consequences: One ffmpeg + libass path, with the ADR-20 polish applying everywhere. `render.STAGE_VERSION` bumps once.

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

## ADR-34: Local download helper
Date: 2026-09-29 · Status: Accepted (2026-09-29; copied to docs/DECISIONS.md; keeps ADR-10 for the cloud; ADR-17 stays deferred)
Context: YouTube blocks Modal's egress IPs. The owner's home connection works, and permitted sources such as creator agreements still need downloading.
Decision: `clipforge fetch` runs yt-dlp locally, with Deno and the bgutil PO-token plugin, into `videos/<channel>/`. It only downloads for sources whose permission is recorded. yoinks is fine for manual use.
Consequences: The laptop is needed only to fetch sources. Everything else stays serverless.

## ADR-35: Channels as blueprint instances
Date: 2026-09-29 · Status: Accepted (2026-09-29; copied to docs/DECISIONS.md)
Context: The portfolio (07) has 15 concepts in 5 categories, about 19 accounts with Spanish pairs, and it has to grow further. Designing each channel by hand doesn't scale, and YouTube's inauthentic-content rule penalizes templated sameness.
Decision:
- Each channel concept is a versioned blueprint (`blueprints/<name>.toml`): niche, pillars, rotating series formats, voice and visual briefs, platform defaults, money sources, a compliance profile, and prompt names.
- An account is a blueprint plus a language, persona, handles, posting profile, budget and review tier.
- Producers rotate series and structure per item and log the variation.
- EN/ES pairs share a blueprint and link through `paired_account_id`. The Spanish side is a native adaptation.
Consequences: A new account is one command plus platform sign-ups. Blueprint changes are reviewable diffs. The policy gate reads the compliance profile.

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

## ADR-38: Next.js as the operational dashboard, Notion as a one-way mirror
Date: 2026-09-29 · Status: Accepted (2026-09-29; copied to docs/DECISIONS.md)
Context: The owner wants one place to run the studio and a readable, shareable planning space. Notion's API is rate-limited (about 3 req/s), can't play R2 video, and allows manual schema edits. A two-way sync would create two sources of truth.
Decision: All operations (accounts, queue, review, thresholds, stats, money, costs) live in the Next.js dashboard over the FastAPI API and Postgres. A `notion_mirror` task writes the planning pack, SOPs and weekly reports to Notion one way, and never reads edits back. The pages say so.
Consequences: Notion is for reading, sharing and thinking. Every change goes through the dashboard or repo.

## ADR-39: AI model / influencer category with provenance kept
Date: 2026-09-29 · Status: Accepted (2026-09-29; copied to docs/DECISIONS.md)
Context: Lifestyle AI personas earn from brand deals and affiliate storefronts. Common playbooks strip AI metadata to pass as human, scrape real people's photos for training, and swap faces onto real people's videos.
Decision:
- Category E uses fully synthetic personas, trained only on their own generated images.
- Provenance metadata (C2PA/IPTC) and platform AI labels are always kept.
- "AI creator" goes in the bio.
- No face or body swaps onto real people's footage.
- Sponsored posts are disclosed. No sexual content.
- `ContentItem` gains media kinds `carousel` and `image`.
Consequences: Platform-compliant accounts that can take brand deals openly. Some "indistinguishable from real" growth tactics are deliberately off the table.

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
Consequences: Every video can be traced to the exact setup that made it, and experiments can isolate their accounts. The accounts table becomes a projection of the current version with one writer (ADR-41). Blueprint changes are reviewed as version diffs in the dashboard instead of file diffs. A `SETUP_SOURCE=db|off` switch lets producers fall back to today's constants. Updates ADR-35: channels are still blueprint instances, but blueprints live in the database.
