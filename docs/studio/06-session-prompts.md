# 06: Session prompts

**Since 2026-09-30, sessions start from a card file** (`docs/cards/`, started with `Run card docs/cards/NNN-….md`); the coordinator builds each card from the matching prompt and action card below, adding context, scope and the decision-log range. The prompts and action cards here are the templates.

Paste a prompt as the **first message** of a new Claude Code session in the repo root.

| Prompt | When |
|---|---|
| **A. Kickoff review** | Once, before any studio code |
| **B. Build a sub-project** | Every S* item. Fill `<ID>` and paste that item's **action card** (§D) under it |
| **C. Spike** | Every X* item, plus its action card |
| **D. Action cards** | One per roadmap item, pasted under B or C |
| **E. Launch an account** | Each time a blueprint becomes a live account |
| **F. Weekly ops review** | Weekly, once S7 has metrics |
| **G. Notion mirror sync** | After the kickoff review settles the pack, then whenever docs/studio changes |
| **H. Incident / debug** | Something broke in production |
| **I. Quick status** | Any time |

Rules shared by every prompt (already written into each one):
- **Process:** brainstorm → spec → plan → implement, with the owner's approval at each gate.
- **Git:** the owner handles it. Don't run git; use checkpoints.
- **Code rules:** CLAUDE.md rules 1–9, the license allowlist in 03, and disclosure fields on every item.
- **Cost:** a stated limit on Modal/API spend.
- **Close-out:** end every session with the close-out checklist.

---

## A. Kickoff review (first session only; no product code)

```
ROLE: senior architect + tech lead for "ClipForge Studio": turning ClipForge into a
multi-account short-video studio (5 categories: clips, AI stories, music bands,
AI-avatar affiliate, AI model/influencer; EN + ES; ~19 accounts; TikTok, Reels,
Shorts, Facebook Reels). All on Modal. Next.js dashboard on Vercel. Telegram for
review. Postgres (Neon). Upload-Post for publishing.

READ (in order, fully):
1. CLAUDE.md, docs/ARCHITECTURE.md, docs/DECISIONS.md, ROADMAP.md.
2. docs/studio/README.md, then 01 to 08. These are PROPOSALS (2026-09-29).
3. Code: src/clipforge/models.py, pipeline/steps.py, posting/*, bot/*, app.py,
   api/main.py, jobs.py, llm.py, config.py, and the latest plan in
   docs/superpowers/plans/ (plan C) with its status line.

ACTIONS:
1. Status: report what is actually done in S0 (plan C Tasks 4–6, deploy state).
   Mark anything the pack assumes that the code contradicts.
2. Gap review: for each of 02, 04, 05 and 08, list:
   (a) contradictions with the code or accepted ADRs
   (b) missing pieces: data migration, auth, secrets, error paths, tests, cost
       logging, rollback
   (c) risky assumptions
   (d) things to cut (YAGNI).
   Rank them by impact. Be blunt.
3. Fact re-check (web search, cite sources, date-stamp each). Check:
   - Modal pricing, Starter limits, Dict expiry, snapshots
   - Upload-Post pricing, TikTok public posting, AI-label fields, webhooks
   - Neon free tier
   - Vercel Hobby vs Pro terms
   - licenses of Qwen3-TTS, Kokoro, InfiniteTalk, Z-Image-Turbo, ACE-Step, Wan2.2
   - TikTok Creator Rewards, YPP, Facebook CMP thresholds
   - YouTube's July 2026 inauthentic-content policy
   - TypeSafe Jev access and pricing
   - Skool and Hotmart affiliate terms
   Put the results in a table: claim | pack says | now | source | action.
4. Dependency check of 04: draw the S/X dependency graph (mermaid) and flag
   ordering mistakes. Confirm S0 → S1 → S2 → S3 as the critical path, or
   propose a better one.
5. Cost sanity: recompute the monthly model in 03 with the verified prices. Show
   5-account and 19-account scenarios.
6. Owner checklist: every account, key, secret and sign-up needed for S0–S3,
   in order, with where each goes (Modal secret name or .env) and who does it.
7. Propose edits to docs/studio/* as diffs, grouped by file. WAIT for my approval.
8. After approval:
   - apply the edits;
   - copy the ADRs I accept from 05 into docs/DECISIONS.md (Status: Accepted,
     today's date) and mark them in 05 as accepted;
   - add "Phase 6: Studio" to ROADMAP.md, linking docs/studio/04;
   - update docs/ARCHITECTURE.md only for accepted decisions.
9. Recommend the next session: which prompt (B or C), which card, and which owner
   actions to finish first.

RULES:
- Use superpowers:brainstorming for any architectural change you propose.
- Stop at each gate.
- No product code, no Modal spend, no deploys.
- I handle git: don't run git.
- Save non-obvious decisions I make to project memory.

CLOSE-OUT: the session close-out checklist (see the end of 06).
```

---

## B. Build a sub-project (S*)

```
STUDIO BUILD: <ID> (<title from docs/studio/04-roadmap.md>)
[paste the <ID> action card from docs/studio/06 §D here]

READ FIRST:
- CLAUDE.md, docs/ARCHITECTURE.md, docs/DECISIONS.md (accepted ADRs are binding;
  proposed ones in docs/studio/05 are not).
- docs/studio/02, 03 and 08, plus the files named in the card.
- Specs and plans of earlier studio sub-projects in docs/superpowers/.
- The code the card touches: read it before designing.

STEP 0: PRECHECK (report, then continue unless blocked):
- Every dependency in the card is ticked in docs/studio/04. If not, STOP.
- The card's owner actions are done (keys in the Modal secret, accounts created).
  If not, list what's missing and STOP.
- Fast tests are green before starting:
  uv run pytest -q -m "not gpu and not slow"; uv run ruff check .; uv run mypy src

STEP 1: DESIGN
- superpowers:brainstorming, architectural path.
- Present 2–3 approaches with a recommendation, then the design in sections.
- Cover: contracts (models.py first), data (tables and migrations), Modal layer,
  error paths (ADR-15 style), cost logging, security/secrets, tests, rollout and
  rollback, docs to update.
- Write the spec to docs/superpowers/specs/<today>-studio-<id>-design.md.
  WAIT for my review.

STEP 2: PLAN
- superpowers:writing-plans → docs/superpowers/plans/<today>-studio-<id>.md.
- Tasks of 2–5 minutes each, TDD, exact files and commands, and a checkpoint
  after each task group.
- Ask me which execution method to use (subagent-driven or inline).

STEP 3: BUILD
- Follow the plan with superpowers:test-driven-development.
- For stages or contracts: run the pipeline-reviewer agent after each task group.
- Log cost in every new stage (rule 7). Put no secrets in code or logs (rule 8).
- Any Modal run must stay within the card's COST LIMIT. Ask before exceeding it.

STEP 4: VERIFY (superpowers:verification-before-completion)
- Fast tests, ruff, ruff format, mypy: paste the outputs.
- The card's DONE-WHEN checks, run for real where possible (modal serve/run),
  with evidence.
- superpowers:requesting-code-review on the full change, then fix or justify each
  finding.

STEP 5: DOCS
- Tick <ID> in docs/studio/04-roadmap.md and ROADMAP.md.
- Update docs/ARCHITECTURE.md and CLAUDE.md (layout, commands) if they changed.
- Add any new ADR to docs/DECISIONS.md.
- Update docs/studio/03 with measured numbers.

RULES:
- Stages stay Modal-free, contracts live in models.py, prompts are versioned files,
  LLM JSON is validated with one retry, and cost is logged.
- Licenses on the allowlist only.
- ContentItems carry ai_disclosure, sponsored and assets.
- No copyright- or provenance-evasion features.
- I handle git: don't run git; tell me when a checkpoint is ready to commit.

CLOSE-OUT: the session close-out checklist.
```

---

## C. Spike (X*): throwaway, output is numbers

```
STUDIO SPIKE: <ID> (<title>)
[paste the <ID> action card from docs/studio/06 §D here]

1. Restate the question, the candidates, the metrics and the COST LIMIT in 5 lines.
   WAIT for my nod.
2. Read docs/studio/03 (the license allowlist and candidates) and the matching
   modal-labs/modal-examples patterns.
3. Verify each candidate's license (code, weights, bundled dependencies) from the
   primary source before downloading anything. If one fails, drop it and say why.
4. Build the probe in scratch/<id>/ (never src/). Use Modal with a
   `clipforge-models` Volume for weights. Time the cold start separately from
   warm runs.
5. Run the card's test set. Record for each candidate:
   - quality: blind samples saved to scratch/<id>/samples; I rate them
   - GPU-seconds per output second, cold start, VRAM, $ per unit (from modal.com/pricing)
   - failures
6. Report: a table plus a recommendation (primary and fallback) and the risks.
   Put the samples somewhere I can open them.
7. After my verdict:
   - update docs/studio/03 (measured numbers replace the estimates; date them);
   - tick <ID> in 04;
   - add or adjust an ADR draft in 05 if the choice changed.
8. Leave scratch/<id>/ in place and tell me when it's safe to delete.

RULES: stay under the COST LIMIT (stop and ask before exceeding it); no product
code; I handle git: don't run git.

CLOSE-OUT: the session close-out checklist.
```

---

## D. Action cards

Paste the card under prompt B or C. For each card:
- **Owner** lists what you do before the session.
- **Cost** is the maximum Modal/API spend the session may make without asking.

### S0: Finish plan C and go live
Done 2026-09-29 (deployed and live; runbook §1). Only the 7-day background check in 04 is open. Kept as the record.
- **Depends:** nothing. **Owner:** approve the deploy.
- **Read:** docs/superpowers/plans/2026-09-28-c-telegram-assistant.md and its ledger in `.superpowers/sdd/…/progress.md`.
- **Actions:**
  1. Finish Task 4 (taps and commands), Task 5 (posting_tick cron and docs) and Task 6 (ADR-24 keep-alive and snapshot) with the plan's own process.
  2. Do the final review.
  3. Give me the exact deploy steps. After I deploy: guide `POSTING_CHAT_ID`, `POSTING_TIMEZONE`, `POSTING_SLOTS` and `POSTING_HASHTAGS` into the Modal secret, then `clipforge set-webhook` and `clipforge status --rebuild`.
  4. Run one real posting slot end to end.
  5. Write a 1-week observation checklist: reject reasons, posting pain, the keep-alive working.
- **Done when:** a clip reaches Telegram on schedule, the taps update the status, and the keep-alive runs.
- **Cost:** $2.

### S1: Foundations (accounts, database, content items, blueprints)
→ card 002 (S1 finish, stop before the rollout; PR #5). The rollout is runbook §4.
- **Depends:** S0's code finished (plan C Tasks 4–6 done; no week of posting needed; merged), and ADR-25, ADR-26 and ADR-35 accepted.
- **Owner:**
  - create a Neon project;
  - put the pooled `DATABASE_URL` in `.env` only; it goes into the `clipforge-secrets` Modal secret at rollout step 4c.2 (log #107, runbook §4);
  - decide the handles for founder.tapes and hombre.en.construccion.
- **Read:** 02 §2, §5, §7 and §10, 07 (the blueprint model), posting/* (including `keepalive.py`), bot/posting.py, inbox.py, the `channels.toml` format, and the deferred items listed under S1 in 04.
- **Actions:**
  1. Add SQLAlchemy 2, psycopg 3 and Alembic with `uv add`. Set up `db/` (engine, session, repositories) and the first migration.
  2. Add the contracts `Account`, `PlatformProfile`, `BrandKit`, `Persona`, `Blueprint`, `SeriesFormat`, `ComplianceProfile`, `AssetSource` and `ContentItem` (media_kind) to models.py.
  3. Create the tables: accounts, personas, sources, content_items, assets, posts, post_events, costs, budgets, and a task-markers table for the dispatcher.
  4. Migrate the posting queue from Dict `post:*` keys to `posts` rows, keeping the ADR-23 status rules. Add a one-off import command with a dry-run, and verify the counts. Keys missing from the Dict are taken from the newest daily snapshot (`/jobs/posting/snapshots/`, ADR-24, ADR-46). Backfill the `jobs` table from each job's `metadata.json`. Add a setting that switches reads between the Dict and Postgres for rollback.
  4b. Fix the two taps deferred from S0's final review: a tap reads only its clip's rows, and a tap on an older message of a re-sent clip redraws every message of that clip.
  5. Wrap the clip producer's output into ContentItems. realtalk.clipsdaily becomes account #1.
  6. Add `blueprints/*.toml` plus a loader, and write the three clip blueprints from 07. Add `clipforge account create --blueprint --lang --handle`.
  7. Add campaign sources: rules, required tags and links, deadline.
  8. Keep the existing crons (sweeper, posting_tick, and posting_keepalive, which becomes `posting_daily`, ADR-46). The dispatcher comes in S7 (ADR-27).
  9. Once the migration is verified, retire only the Dict touch in `posting_daily`; the rest of the cron stays (ADR-46).
  10. Tests: repositories against a local Postgres (`TEST_DATABASE_URL`, or Docker through testcontainers), a migration round-trip, and the queue rules preserved.
- **Done when:**
  - the existing posting works the same, with state in Postgres;
  - 3 accounts are defined from blueprints;
  - the fast tests are green.
- **Cost:** $3.

### S2: Publishing, review tiers, policy gate, ledger
- **Updated 2026-10-01 (card 009, ADR-48 to ADR-50):** 04's S2 list is the source: autopilot (`autopilot` table and history, the Review dial, the Publish switch, presets, ladder, demotions), the review windows (format 10, producer version 5 per ADR-49, first dubs 10), the brake's scope, one-tap only for items due within 2 h, publishing-failure rows, the dispatcher (accept ADR-27 here), the migration landing-order rule. founder.tapes and hombre.en.construccion are created just before this card (O3); the exit is realtalk auto-posting on its rung and the other two starting Hands-on. Read the S3 dashboard spec §8.6.
- **Depends:** S1, and ADR-28, ADR-29 and ADR-33 accepted.
- **Owner:**
  - create founder.tapes and hombre.en.construccion first (O3's handles; `clipforge account create`), then the Upload-Post Professional plan; connect the three accounts on TikTok, IG, YT and FB;
  - `UPLOAD_POST_API_KEY` and the webhook secret;
  - a Whop account for campaigns.
- **Read:** 02 §5, §5b and §6, 08 §1, 03 (Upload-Post, media hosting).
- **Actions:**
  1. The `Publisher` protocol, with `UploadPostPublisher` and `AssistedPublisher` (today's Telegram flow).
  2. Signed, expiring per-file media links from the Volume for Upload-Post (R2 only if these prove unreliable).
  3. The signed webhook route, which updates `posts` and `post_events`.
  4. Map AI disclosure per platform (`is_aigc`, `containsSyntheticMedia`, `is_ai_generated`, `facebook_is_ai_generated`).
  5. Policy gate v1:
     - disclosure
     - #ad
     - credits
     - license manifest
     - cross-account duplicates
  6. Review tiers (review / sample / auto): Telegram approve, fix copy, reject with reason, and a daily digest.
  7. Tracking links: `GET /go/<slug>`, click logging, sub-ids.
  8. Tests: fake Publisher and golden cases for the gate. (Judge, ledger, lanes and the morning message move to S6.)
- **Done when:**
  - realtalk.clipsdaily auto-posts to 4 platforms on its rung; founder.tapes and hombre.en.construccion start Hands-on on S2's flow;
  - a gate failure lands in review;
  - the daily digest arrives.
- **Cost:** $5 (plus real posts).

### S3: Dashboard v1 (Next.js on Vercel)
- **Updated 2026-10-01 (card 009, ADR-48 to ADR-50):** the pages, API and data are in the S3 dashboard spec §7 and §10.2 and 04's S3 list (inbox-first Home with "needs me" and the attention meter, `/act`, Results, Settings, Accounts → Compare, the Overview/Autopilot/Activity tabs, the link-contract test); mockups in `docs/design/dashboard/`. Caps are shown, not enforced. Its exit is the 20-minute phone check-in.
- **Depends:** S1 and S3a, and ADR-38 accepted. Runs alongside S2; approve-to-publish in the inbox lands when S2 does.
- **Owner:**
  - Vercel Pro;
  - a GitHub OAuth app (or email provider) for Auth.js;
  - a Modal proxy-auth token;
  - the owner's email for the allowlist.
- **Read:** 08 §2, api/main.py, 02 §8.
- **Actions:**
  1. API: endpoints for accounts, personas, items, posts, calendar, review actions, decisions and costs, with pagination and auth. Export OpenAPI to a file in CI (the docs routes stay off).
  2. `web/`: Next.js App Router, TypeScript, Auth.js with a single owner, a TanStack Query client generated by hey-api, and a UI kit chosen in the design step.
  3. Pages: Home, Review inbox (video from a signed Volume link, gate answers, approve/edit/reject; **until S2 it is a queue manager, D8**: skip, reject with a reason, reorder the queue, and correct a posted mark, each through `posting/actions.py` with actor `web:<login>` (S1 builds `skip`, `reject`, `set_reason` and `set_posted`; S3 adds the reorder action there); it never sends, so it isn't a second posting flow), Calendar, Sources (permission records, expiry, history, add/edit), Produce (submit a clip job from a source, batch planner), Costs. (Decisions comes in S6.) **Accounts is not built here:** the studio map and account workspaces are S3c (owner decision, 2026-09-30); keep S1's `/accounts` routes as they are.
  4. Vercel server route handlers call a separate `admin` Modal endpoint with proxy auth and the bearer token; the public `web` endpoint keeps the webhooks, download links and `/go`. No direct database access. S3c builds its routes on this `admin` endpoint, so keep it generic (a router per area). **D9:** `admin` is a second `@modal.asgi_app(requires_proxy_auth=True)` function in `app.py` that reuses `create_app` with an admin router added, and checks its own bearer token, `ADMIN_API_TOKEN` (a new key in `clipforge-secrets`; a missing token answers 503, never runs open). The route handlers send `X-Clipforge-Actor: web:<login>`.
  5. Phone and laptop layouts for every page (08 §2), using S3a's responsive shell.
  6. Tests: API tests in pytest; one Playwright smoke test for login, inbox and approve.
  7. Deploy to Vercel. Write the environment docs in `web/README.md`.
- **Done when:** the owner runs the wave-1 accounts from the dashboard plus the phone.
- **Cost:** $2.

### S3c: Account workspaces (versioned categories, blueprints and accounts; experiments; notes)
- **Updated 2026-10-01 (card 009, ADR-48 to ADR-50):** apply the S3 dashboard spec §10.3: the review tier and budget leave the versioned setup (ADR-48), `system:<component>` actors, the Style/Hooks/Activity tabs, the Map next to Compare, hook metrics on the Hooks tab (ADR-50).
→ card 003 (the design revision, done 2026-09-30, PR #6). No build card yet.
- **Depends:** S1 finished (all tasks; 0001 frozen) and S3's `admin` endpoint (S3 action 4). ADR-42 accepted. S3c-2 needs S1 Tasks 14, 15, 17 and 21 live. Soft: land S3c-2 before S6, so the story producer reads `EffectiveSetup` from its first version.
- **Owner:** none beyond S1 and S3 (Neon and Vercel already set up). Edit the drafted category playbooks in the dashboard after S3c-1.
- **Read:** the S3c spec (docs/superpowers/specs/2026-09-30-studio-s3-workspaces-design.md, revised by card 003), ADR-42 in docs/DECISIONS.md, 08 §2 and §2b, the S1 spec §6, card 002's `posting/actions.py`, S1's final `models.py` (`Account`, `Blueprint`, `ContentItem`), `db/tables.py`, `accounts/`, `hashing.py`, `stages/highlights.py` and `captions.py`.
- **Actions:**
  1. Plan first (superpowers:writing-plans) on S1's final schema; confirm the open points in spec §7.
  2. **S3c-1:** migration 0002 (with `post_events.actor`, backfilled from `data.actor`; spec §5.3); the resolver (`accounts/setup.py`) and the field registry with change classes; the versions service (append-only `*_versions`, `accounts` as a projection, `expected_version` → 409); `clipforge setup import [--dry-run]` and `setup verify` (0 differences); `POST /setup/preview`, the one dry run every save, restore and apply calls (spec §3.4); admin routes for categories, blueprints, account setup, versions, diff, restore and notes; the Accounts page and the category, blueprint and account workspaces at the spec §2.9 paths (phone and laptop). `SETUP_SOURCE=off`.
  3. **S3c-2:** `create_job` reads and stamps `JobInput.setup`; `content_items.setup_version` at enqueue; `post_events.data.setup_version` at send; caption preset in the captions key only when not `default` (pinned-value test); prompts from released versions; the language-mismatch hold; a test that the setup version is in no cache key. Regenerate `web/openapi.json` in the same checkpoint (#49). Switch `SETUP_SOURCE=db` after `verify`.
  4. **S3c-3:** experiments (draft, running, needs a decision derived on read, done, stopped) and the experiment page `/experiments/<id>`, the only place to keep or revert; the re-cut estimate in the preview (`config.Prices`, source hours from `jobs`), one running per account (partial unique index), the edit block during a run, the metric registry (metrics available now), before/during with the Wilson verdict and the 10-item floor, the Experiments nav item and Home's "Needs a decision" card, learnings in the playbook.
  5. Tests: pure, DB (local Postgres), API and pipeline tests as in spec §5.5; Playwright phone and desktop against a mocked admin API. Checks run locally and in production (previews are build-only).
- **Done when:** the owner changes realtalk's max clip length through an experiment, sees before and during for reject rate and posted rate, chooses Keep, and the learning shows in the clips playbook, all from the dashboard on phone and laptop.
- **Cost:** ~$1 (tests and one smoke run). A backlog re-cut, if ticked, is priced in the form before it runs.

### S3a: Dashboard shell
→ card 004 (local login and the Vercel deploy; the shell itself is built).
- **Depends:** nothing. It runs in its own worktree (`../clipForge-web`, branch `s3a/deploy`, from `scripts/worktree.sh`), owns only `web/` and `scripts/export_openapi.py`, and never deploys `app.py`.
- **Owner:**
  - Vercel Pro;
  - a GitHub OAuth app for Auth.js (callback `https://<vercel-domain>/api/auth/callback/github`);
  - your GitHub email for the allowlist.
- **Read:** 08 §2, 02 §8, api/main.py, models.py (`PostingOverview`, `JobView`).
- **Actions:**
  1. Design step (brainstorming): the UI kit, the layout, and the Home and job pages on a phone.
  2. `web/`: Next.js App Router, TypeScript, Auth.js with one allow-listed owner, TanStack Query.
  3. A script that exports the OpenAPI file from `create_app` without running Modal, and hey-api generating the client from it.
  4. Server route handlers call the deployed API with the bearer token (`CLIPFORGE_API_URL`, `API_TOKEN` as Vercel env). No database, no browser-side token.
  5. Pages: Home (posting progress per channel, polled every 5 s) and a job page. Everything else is a placeholder. `GET /posting` is live only after S0's deploy; until then, build against the exported OpenAPI with mock data.
  6. Tests: a Playwright smoke test for login and Home; `npm run build` and lint in CI.
  7. Deploy to Vercel, and write `web/README.md` (env vars, local dev).
- **Done when:** you log in on the phone and see live posting progress from the deployed API.
- **Cost:** $0 of Modal (Vercel Pro $20/mo).

### S3b: Notion mirror (right after the kickoff review)
- **Depends:** the kickoff review is approved. **Owner:** pick the Notion parent page.
- **Actions:**
  1. Use the Notion connector (or an integration token in the Modal secret for the automated version) to create "ClipForge Studio" with one page per docs/studio file. Each page starts with a banner: "read-only mirror, edit in repo".
  2. Only with the weekly report (after S7): `clipforge notion sync-docs`, which creates or replaces pages. Never read back.
  3. A weekly report task (built after S7).
- **Done when:** the pages are readable on the phone and match the repo.
- **Cost:** $0.

### S4: Timeline renderer
→ card 006.
- **Depends:** S0, and ADR-31 accepted (it doesn't need the database, so it runs alongside S1–S3). **Read:** stages/render.py, captions.py, reframe.py, ADR-18/19/20/21.
- **Actions:**
  1. Add the `Timeline` contract: visual segments (source crop, still with Ken Burns, video, talking head), audio tracks (source, narration, music with ducking), captions with the hook title card in one ASS overlay (log #340) and asset sources.
  2. Generalize render and bump `render.STAGE_VERSION`.
  3. Move clips onto the Timeline, with ffprobe asserts that the properties don't change.
  4. Add two-pass loudnorm.
  5. Add a synthetic Timeline fixture test (stills, narration, music).
- **Done when:** clips are unchanged on ffprobe checks, and the synthetic Timeline renders 1080x1920, under 50 MB, at -14 LUFS.
- **Cost:** $2.

### S5: Media servers and producer registry
- **Depends:** S4, X1 and X4, and ADR-30 accepted.
- **Owner:** a Hugging Face token, if any model is gated. Langfuse keys.
- **Actions:**
  1. `media/` protocols plus `registry.toml`, with a license-allowlist test.
  2. The `clipforge-models` Volume and weight-download functions.
  3. `modal.Cls` servers for TTS, aligner, image and music, with memory snapshots, `@modal.batched` and step methods inside the classes.
  4. A pipeline registry that drives `dispatch` and `resume`. Split app.py into a `modal_app/` package (still the only Modal importer).
  5. LLM tracing in Langfuse. (The bulk-level router, ADR-32, is deferred.)
  6. A "hello" producer that proves the GPU step pattern.
- **Done when:** clips run through the registry, the hello producer runs end to end, and a registry test fails on a banned license.
- **Cost:** $10.

### S6: Story producer (wave 2: untold.archive + historias.ocultas)
- **Updated 2026-10-01 (card 009, ADR-48 to ADR-50):** add the queue filler (`produce/filler.py`, clips adapter) and, if no earlier card did, the hard caps in `service.create_job` (ADR-48); story hook variants use the hooks card's interface (ADR-50). Two-pass loudnorm already shipped in S4 (ADR-47).
- **Depends:** S5, S2 and X1, and ADR-36 and ADR-37 accepted. **Owner:** confirm the niche, a Pexels key, and create both accounts in Upload-Post.
- **Actions:**
  1. Write the blueprints (EN and ES) with 4+ series formats and the retention script structure from 07.
  2. Build the steps: brief → research (sources stored) → script (versioned prompts, rotating structures, 61–90 s) → pre-check → TTS (persona voice) → align → shot plan → stills (plus optional b-roll) → music → Timeline → render → gate → item.
  3. Persona voice design for both accounts.
  4. A variation log per item.
  5. The weekly trend job (xAI X Search plus YouTube mostPopular).
  6. RIFE for any generated video, and caption presets (pycaps effects ported to ASS, Noto Emoji).
  7. A script eval set of 20 topics (promptfoo gate plus owner ratings).
  8. A batch planner endpoint: N scripts per account per week.
  9. The `Judge` protocol with ClaudeJudge (versioned prompts, validated JSON), the `decisions` ledger, lanes with fail-closed rules and disagreement escalation, the banned-claims gate check, ~5% audit sampling of `publish`, and the Telegram morning message (moved from S2).
- **Done when:** both accounts post 1–2 videos a day in `review` tier, at under $0.10 per video (measured).
- **Cost:** $15.

### S7: Analytics and money
- **Updated 2026-10-01 (card 009, ADR-48 to ADR-50):** the hard caps are enforced in `create_job` (ADR-48), so S7 keeps reporting and burn-down; its pull and checks run on S2's dispatcher; hook ranking adds the 3-second hold and views at 24 h (ADR-50).
- **Depends:** S2 and S3. **Owner:** a Sentry DSN, YouTube OAuth for the Analytics API, ClickBank and Hotmart API credentials.
- **Actions:**
  1. A daily analytics pull (Upload-Post plus YouTube Analytics) into metrics tables.
  2. A `programs` table with editable thresholds, and progress per account.
  3. Conversion imports: ClickBank and Hotmart APIs, CSV for Skool, Amazon and TikTok Shop.
  4. Winner detection (top decile after 7 days).
  5. Budget enforcement before a job starts.
  6. Sentry, plus the Stats, Money and Personas pages, and a weekly report generator (feeds S3b).
- **Done when:** cost, views, clicks and revenue show per account and per item, and a job over budget is refused.
- **Cost:** $3.

### S8: Avatar producer + personas (wave 3: profe.ia.ingles, ai.tools.lab)
- **Depends:** S6, X2, X3 and S2's tracking links. **Owner:** affiliate accounts (Babbel/Preply, Hotmart, Skool, SaaS programs) and the offers chosen.
- **Actions:**
  1. The persona producer: face (Z-Image with a LoRA from X3), voice, and a consistency score.
  2. The avatar producer:
     - offer brief with a tracking link;
     - a script that never claims first-person use;
     - a claims pre-check;
     - talking head for presenter segments only;
     - b-roll, render;
     - a gate that requires #ad and the AI flag.
  3. The Personas page.
- **Done when:** both accounts post daily at under $0.30 per video, with tracked links.
- **Cost:** $25.

### S9: Band producer (wave 4: neverheard.from, radar.indie.latino)
- **Depends:** S6. **Owner:** a MusicBrainz User-Agent contact, SubmitHub/Groover curator sign-ups.
- **Actions:**
  1. Research (MusicBrainz, Wikidata, Wikipedia).
  2. Commons photos with attribution, and a promo-material intake with the permission recorded.
  3. Art generation (no photoreal images of real people).
  4. A music-free master plus `suggested_sound`, and collab tags.
  5. A gate that requires a license for every asset.
- **Done when:** both accounts post daily, and every asset has a license record.
- **Cost:** $10.

### S10: Dub winners (EN ↔ ES)
- **Updated 2026-10-01 (card 009, ADR-48 to ADR-50):** dubs only to a paired account, only when the source permission allows translation, under the target account's dial and budget, the first 10 in a pair to review (ADR-48).
- **Depends:** S7, S6 (and S8 for avatars). **Owner:** the ES partner accounts exist.
- **Actions:**
  1. Winner → translate within a timing budget → target persona voice → align → re-time → (re-run the talking head for avatars) → render → gate → item for the paired account.
  2. python-audio-separator for sources that have music.
- **Done when:** a top-decile EN item appears on its ES partner within 48 h.
- **Cost:** $10.

### S11: Local fetch helper
- **Depends:** S0 (and S1 for the sources table). **Owner:** install Deno locally.
- **Actions:**
  1. `clipforge fetch <url> --channel <c>`: yt-dlp with Deno and the bgutil PO-token plugin, saving into `videos/<channel>/`.
  2. Check the permission against the sources before downloading.
  3. Document it in CLAUDE.md.
- **Done when:** a permitted video downloads and `clipforge clip` submits it.
- **Cost:** $0.

### S12: The Desk
- **Depends:** S7 and S2 (Judge and ledger). **Owner:** a shared inbox address, and the list of DM/comment sources to enable.
- **Actions:**
  1. Event sources.
  2. Judge questions (lane, urgency, evidence, money) with guards.
  3. Claude drafts into the queue, never sent automatically.
  4. A 1% audit of `ignore`.
  5. The Desk page.
- **Done when:** inbound for all accounts is handled from one page, and the audit shows the false-ignore rate.
- **Cost:** $3.

### S13: AI model / influencer producer (wave 6)
- **Depends:** S8 (personas) and S4. **Owner:** the persona brief, and target brands.
- **Actions:**
  1. Media kinds `carousel` and `image`, plus a carousel renderer.
  2. LoRA scenes with a consistency check.
  3. Motion reels from Wan2.2 image-to-video.
  4. Provenance metadata kept (write a test for it).
  5. The compliance profile: AI bio and labels, synthetic-only training data, sponsored disclosure, no health or diet claims.
- **Done when:** one persona posts daily carousels and reels in `review` tier.
- **Cost:** $20.

### S14: Funnel and own products
- **Depends:** S7 and S3. **Owner:** choose an email provider and a Hotmart producer account.
- **Actions:**
  1. Bio pages per account (Vercel, Umami).
  2. Email capture and a sequence builder.
  3. Sales import and the Funnel page.
  4. Lesson video production for the first product, with the guardrails in 08 §5.
- **Done when:** one product is live with a tracked funnel.
- **Cost:** $10.

### X1: Voice bake-off
- **Question:** Which TTS gives the best EN and ES narration per dollar?
- **Candidates:** Qwen3-TTS 1.7B (VoiceDesign, then Base clone), Kokoro-82M, Chatterbox Multilingual.
- **Test set:** 10 scripts (5 EN, 5 ES), 60–90 s each, and 3 designed voices.
- **Metrics:**
  - blind owner rating (1–5);
  - word error rate via faster-whisper;
  - GPU-seconds per audio-second on L4, batched and unbatched;
  - cold start.
- **Cost:** $10.

### X2: Talking-head bake-off
→ card 005 (resume from step 5, after the owner rules on O7). Partial results: [spikes/x2-talking-head.md](spikes/x2-talking-head.md).
- **Question:** Which open model makes a convincing presenter in 9:16?
- **Candidates:** InfiniteTalk (480p, 4–8-step LoRA), LongCat-Video-Avatar 1.5, EchoMimicV3.
- **Test set:** 3 synthetic portraits × a 20 s EN clip plus a 20 s ES clip.
- **Metrics:**
  - lip sync (owner rating plus a sync-offset check);
  - identity drift;
  - GPU-seconds per output second on H100 or A100-80;
  - the upscale path to 1080x1920 (Real-ESRGAN) and RIFE to 30 fps;
  - **a check that no InsightFace weights are used.**
- **Cost:** $30.

### X3: Persona consistency
- **Question:** Can Z-Image-Turbo plus a LoRA keep one identity across 30 scenes?
- **Actions:**
  1. Generate a portrait, then 30–40 synthetic training shots.
  2. Train a LoRA on H100 (modal-examples `diffusers_lora_finetune.py` pattern).
  3. Generate 30 test scenes.
- **Metrics:** a face-embedding similarity score, **using a commercially usable embedder** (not InsightFace packs); the owner's rating; time and cost per persona.
- **Cost:** $15.

### X4: Visuals and music
- **Question:** What do stills, b-roll and music beds cost, and are they good enough?
- **Candidates:**
  - Z-Image-Turbo on L4 FP8 vs L40S;
  - Qwen-Image-2512 for images with text;
  - Wan2.2 TI2V-5B vs A14B with lightx2v for 5 s b-roll;
  - ACE-Step 1.5 for 60 s beds.
- **Metrics:** $ per unit, time per unit, owner rating.
- **Cost:** $15.

### X5: Judge (Jev vs Haiku)
- **Question:** Is TypeSafe Jev more accurate and better calibrated than Haiku for our decisions?
- **Owner:** Jev early-access key (`TYPESAFE_API_KEY` in `.env`). Install the TypeSafe skill:
  ```
  claude plugin marketplace add typesafe-ai/skills
  claude plugin install typesafe@typesafe-ai
  ```
- **Test set:** about 200 labeled items: owner verdicts from S0/S2 plus synthetic policy cases (health claim, earnings claim, missing #ad, first-person testimonial, prompt injection in the copy), EN and ES.
- **Metrics:** accuracy, calibration (a reliability curve), disagreement rate, latency, $ per 1K decisions.
- **Output:** the default judge per decision, plus thresholds.
- **Cost:** $5.

### X6: Hero shots (optional)
- **Question:** Is Grok Imagine Video 1.5 worth paying for over Wan2.2 on story hero shots?
- **Owner:** an xAI API key.
- **Test set:** 10 story shots from S6 scripts.
- **Metrics:** owner rating, $ per second, license terms. Retention A/B later in S7.
- **Cost:** $10.

---

## E. Launch an account

```
STUDIO ACCOUNT LAUNCH: blueprint <name>, language <en|es>, handle <handle>.

1. Read docs/studio/07 (the concept), the blueprint file, and docs/studio/08 (review
   tiers).
2. Check the handle ideas are available on TikTok, IG, YouTube and FB (web search
   plus manual check notes). Propose 3 alternatives if one is taken.
3. Draft the bio per platform: AI disclosure when the category requires it, credit
   or affiliate disclosure, and a link (a /go link or the bio page).
4. Run `clipforge account create --blueprint <name> --lang <l> --handle <h>`.
   Confirm the persona job (voice, and face where needed) and show me the samples
   to approve.
5. Guide me through connecting the account in Upload-Post (profile id into the
   account row). Warm up the account by normal use for 3–5 days (no fake
   engagement).
6. Produce the first batch (5–10 items) in `review` tier. I approve them in the
   inbox.
7. Set the cadence and budget, and schedule the first week.
8. Record the launch in docs/studio/09-account-registry.md (status, final handle), in docs/studio/10-decision-log.md, and in project memory.

RULES: no fake engagement, disclosure per the compliance profile. I handle git.
```

---

## F. Weekly ops review (after S7)

```
STUDIO WEEKLY REVIEW for the week ending <date>. Use the API or dashboard data only
(no production changes without my OK).

1. Per account: posts, views, followers, retention (where available), clicks,
   revenue, cost, cost per 1K views, budget burn, and program progress.
2. Winners (top decile) and losers. What the winners share: series, hook,
   length, topic.
3. Decisions: escalation rate, audit false-pass and false-ignore, threshold
   changes last week and their effect. Propose ONE threshold change.
4. Pipeline health: failed jobs, stalled steps, cold-start cost, and errors from
   Sentry.
5. Recommend: 3 actions (clone a series, dub a winner, pause an account, change
   cadence or budget), each with the expected impact.
6. Write the report to docs/studio/reports/<date>.md, and (after S3b) sync it to
   Notion.

I handle git.
```

---

## G. Notion mirror sync (after the kickoff review settles the pack)

```
Sync docs/studio/* to Notion as a READ-ONLY mirror.

1. Use the Notion connector. Find or create the parent page "ClipForge Studio"
   (private) in <location I name>.
2. One child page per docs/studio file, same title, content converted to Notion
   blocks. Start each page with the callout "Read-only mirror of the repo; edit in
   docs/studio, not here. Synced <date>."
3. Replace existing pages' content. Never read edits back into the repo.
4. Add an "Index" page with the roadmap status (ticked or unticked) and links.
5. Report the page links.
```

---

## H. Incident / debug

```
STUDIO INCIDENT: <what's wrong, which account/job/post ids, since when>.

Use superpowers:systematic-debugging. Read-only first:
1. Reproduce from evidence: job and post records (API), the decisions ledger, Modal
   logs (`modal app logs`), Sentry, and the webhook events.
2. Find the root cause before any fix. State the hypothesis and the evidence.
3. Contain it: pause the affected account's posting (tell me the command) if bad
   content could go out.
4. Fix with a failing test first, then the fix. Deploy only with my OK.
5. Write a 5-line postmortem in docs/studio/reports/incidents.md, and add a guard
   or test so it can't recur silently.

I handle git.
```

---

## I. Quick status

```
Read docs/studio/04-roadmap.md, ROADMAP.md and the latest plans' status lines, and
look at what's actually in src/, web/ and blueprints/. Report:
- done
- in progress (with its next task)
- blocked (and on what, including owner actions)
- the single next step and which prompt/card to use.
Don't change anything.
```

---

## Session close-out checklist (every session ends with this)

1. **Evidence:** the `scripts/check.sh` summary (log #380).
2. **Docs updated:** roadmap ticks, ARCHITECTURE, CLAUDE.md commands/layout, 03 numbers, ADRs, a row in docs/studio/10-decision-log.md for every decision made or changed, docs/studio/09-account-registry.md for any account change, and docs/studio/11-owner-runbook.md for any owner step or command that changed. Add to docs/studio/10 only by appending rows (re-read it first; never rewrite it).
3. **Owner actions:** what you must do next (keys, sign-ups, deploy, a commit checkpoint with a suggested message).
4. **Memory:** save non-obvious decisions and preferences from the session.
5. **Next session:** which prompt and card, and what must be true first.
