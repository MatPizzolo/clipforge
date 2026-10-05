# Status

The one page that says where things stand. The coordinator updates it after every merged PR and every report. Detail lives in the linked files; this page only summarizes, and closed items move out (their record is in `docs/reports/` and the decision log).

Last updated: 2026-10-05 (cards 018, 020 and 021 merged; build cards 028–038 written; the rollout is set for 2026-10-05 16:30 New York).

## Now

**Production.** The `clipforge` Modal app runs the code of `dea435d` (deployed 2026-10-02 02:10 UTC; restarted from `6e832a7`, docs-only changes, at 03:14 UTC), Dict-only (`STATE_READS=dict`, `DATABASE_URL` not in `clipforge-secrets`). `posting_tick` runs every 5 minutes; deploy blackout in runbook §1. The first clean night is in: `posting_daily` ran at 07:00 UTC on 2026-10-02 (420 keys touched, a 36-key snapshot, rebuild 0), and the 08:00 and 10:30 slots sent. Two clips wait on the owner's taps, so the tick says "waiting" until they're answered. On 2026-10-03, `posting_daily` ran at 07:00 UTC (426 keys touched, a 42-key snapshot, rebuild 0), but the tick has said "waiting" since the 2026-10-02 13:00 slot: two clips sent without a tap, so no slot sends until the owner answers them. As of 2026-10-05, posting is still waiting on those two clips (unchanged since 2026-10-03). Card 010's rollout (checkpoint B) is set for 2026-10-05 at 16:30 New York time.

**Incident, 2026-10-02 (fixed 03:14 UTC):** `DATABASE_URL` was in the secret before rollout step 1's migration, so every read of `sources` or `jobs` hit an empty database: `GET /posting` answered 500, and `/next` and Telegram taps that send the next clip failed (the Dict stayed primary; nothing was lost). The owner removed the key and redeployed (`docs/ops/deploys.md`). Card 010 now checks the key is absent before step 1.

**Deployed 2026-10-02 02:10 UTC** (`deploy-20261002-0210`, `dea435d`): cards 002 (S1) and 006 (S4), and `tzdata`:
- replaces the `posting_keepalive` cron with `posting_daily` (same 07:00 UTC slot; a daily idempotent rebuild; the sticky `posting:outage` flag);
- adds ⚠️ ops alerts (failed channel and CLI jobs, tick and daily errors, within ADR-45's limits) and `db_doctor`, and mounts `blueprints/`;
- switches render to the Timeline (version 4, two-pass loudness, ADR-47): every clip re-renders on its next job;
- installs `tzdata` in every image, so alerts from GPU steps work.

**Decided today (card 009):** the dashboard is the studio's control room, inbox-first, for a ~20-minute daily phone check-in. Each account runs on autopilot as far as it has earned: three switches and a review dial, a graduation ladder where promotions are always the owner's tap (ADR-48). A new producer version opens only a 5-item review window (ADR-49). Hooks get a versioned library with rotation (ADR-50). founder.tapes and hombre.en.construccion launch with S2, which is now the next big step after S1's rollout.

**Open PRs:** none. Card 010's live steps (checkpoint B) are set for 2026-10-05 at 16:30 New York time.

## Waiting on the owner (most important first)

1. ✅ Neon moved (2026-10-02): a new empty project in AWS us-east-2 (Ohio, about 10–12 ms from Modal's us-east); both `.env` files hold its pooled and direct strings, checked (connects, 0 tables). The São Paulo project is deleted.
1. ✅ O5 collected (2026-10-01). You type the facts into `clipforge source edit` at rollout step 4; they live only in the database.
2. ✅ Cards 002 + 006 + tzdata deployed (2026-10-02 02:10 UTC). Check tomorrow's first `posting_daily:` log line (07:00 UTC).
3. **Answer the 2 clips waiting since 10:30** (✅, ⏭ or 🗑). The rest of the **S0 checks**: `/status`, `/next`, ✅ on and off, ⏭, 🗑 + reason, `/pause`, `/go`, and one scheduled slot end to end.
4. **O3, the handles for founder.tapes and hombre.en.construccion** (checked free on TikTok, Instagram, YouTube and Facebook): now needed **before card 016 (S2c)**, not before the rollout.
5. **O7, WenetSpeech-pretrained models (gates card 005):** **treat as "needs review"; prefer LongCat 1.5 unless a wav2vec model is clearly better in the X2 blind test.**
6. **Branch protection for `main`:** require a PR and the `check` and `scope` checks; block force pushes (may need GitHub Pro on a private repo).
7. **The Vercel steps (runbook §5b), when you want the dashboard online:** they unlock card 004.
8. **X2's ~227 GB on the Volume:** **keep it if card 005 runs within a couple of weeks**, else `uv run modal volume rm -r clipforge-models x2`.
9. ✅ O4 closed (2026-10-02, log #139): Upload-Post **Basic** now (buy it at card 015's R5 step), Professional at the 6th account. Still before S2's auto-posting: O6 (clip series formats).
10. When you want CI to deploy: the GitHub secrets and variables, then `DEPLOY_ENABLED=true` (runbook §8 "still left").
11. ADR-53 (Langfuse tracing) is drafted in 05: accept or reject when you want tracing (an optional card after S6).

## Next cards (in order)

| Card | What | Can start | Runs alongside |
|---|---|---|---|
| [010](docs/cards/010-s1-rollout.md) | S1 rollout (Task 22) with the owner: two small fixes, then runbook §4c step by step, then evidence | **ready**: clean night and slot sends on 2026-10-02 (O5 ✅); start checkpoint A now, the live steps outside a blackout | — |
| [014](docs/cards/014-s2a-dispatch-gate.md) | S2a: rails (migration 0002, the dispatcher, the brake, autopilot on Hands-on, the gate log-only, routing; plan Tasks 1–8) | after card 010 is fully done: step 7 (`STATE_READS=postgres`) verified, `posting verify` at 0, `db_doctor` schedule copies, Neon head `0001` | hooks, S3 (one migration at a time) |
| [031](docs/cards/031-s5-split.md) | S5-1: `app.py` split into `modal_app/`, nothing live changes (S5 plan Task 1) | right after 014 is deployed, **before 015 or 022 starts** (#591) | — (015 and 022 wait for its deploy) |
| [015](docs/cards/015-s2b-publishing.md) | S2b: Upload-Post for realtalk on Hands-on (R5's real call first; plan Tasks 9–20) | after 014 is deployed and one clean day, and after 031 is deployed (#591); Basic bought for R5; the deploy needs the profile, webhook and both secrets | S3 |
| [022](docs/cards/022-s3b-admin.md) | S3-1: the `admin` endpoint, proxy auth, S3's migration (numbered at landing, after 0002), Settings, `upstream.ts` on `admin` (plan Tasks 1–5) | after card 010 is done **and** card 014 is deployed with its owner steps (#144), and after 031 is deployed (#591); online after 004 | 015's development (merges and deploys one at a time) |
| [016](docs/cards/016-s2c-ladder-launch.md) | S2c: ladder, digest, failure rows, tracking links; founder.tapes and hombre launch (plan Tasks 21–26) | after 015 is deployed and a day on Hands-on with verify 0; O3, one permitted source each, two more profiles | S3 |
| [023](docs/cards/023-s3b-needs.md) | S3-2: "needs me", Home, `/act`, the link contract, alert Open buttons (Tasks 6–11) | after 022 is deployed | S2 cards (one deploy at a time) |
| [024](docs/cards/024-s3b-review.md) | S3-3: Review (Queue, Review lane), move to the front, Calendar (Tasks 12–15) | after 023 is deployed; the lane has rows once 015 is deployed; Re-render waits for the hooks build | S2 cards |
| [025](docs/cards/025-s3b-produce.md) | S3-4: Produce with batches, the Jobs tab, Resume, Sources (Tasks 16–18) | after 024 is deployed | S2 cards |
| [026](docs/cards/026-s3b-results.md) | S3-5: Results → Costs, Compare, the account view (Tasks 19–21) | after 025 is deployed; strikes and Promote need 016 deployed | S2 cards |
| [027](docs/cards/027-s3b-cutover.md) | S3-5b: Telegram retirements, the CLI on `admin` and `web` public-only (#146), `REVIEW_BATCH` off (Tasks 22–23) | after 026 is deployed and each 7-day window (Produce online; `admin` live; Review online) | any |
| [028](docs/cards/028-hk-library.md) | HK-1: hook library tables (migration numbered at landing), seeds, rotation on jobs, control stamps, `clipforge hooks` (Tasks 1–6) | after 010 is done and 014 is deployed (#144) | S2 and S3 cards (one deploy at a time) |
| [029](docs/cards/029-hk-variants.md) | HK-2: `keywords_v3` variants behind `HOOK_VARIANTS`, ranking, ratings, re-render (Tasks 7–11); the flag flip is a separate redeploy | after 028 is deployed; fallbacks where 015, 016, 022, 023 or 024 isn't | S2 and S3 cards |
| [030](docs/cards/030-hk-page.md) | HK-3: the interim `/hooks?account=` page (Task 12) | after 029 and 022 are deployed; skipped if S3c's Hooks tab ships first | any |
| [032](docs/cards/032-s5-registry.md) | S5-2: the producer registry and one engine, clips unchanged (Tasks 2–6) | after 031 is deployed, slotted between deployed cards, never with 025 or the caps change open (#603) | S2 and S3 cards |
| [033](docs/cards/033-s5-media.md) | S5-3: `media/`, `registry.toml`, the media stages, renderer additions (Tasks 7–11); deploys alone (#601) | after 032 is deployed | S2 and S3 cards |
| [034](docs/cards/034-s5-servers.md) | S5-4: weights, three media servers, hello on an L4 (Tasks 12–15; $5 cap) | after 033 is deployed | any |
| [035](docs/cards/035-s3c-data.md) | S3c-1a: versioned setup: migration (numbered at landing), preview, `setup import`/`verify`, routes (Tasks 1–7) | after 010 is done and 014 and 022 are deployed | S3 cards (one deploy at a time) |
| [036](docs/cards/036-s3c-pages.md) | S3c-1b: the Accounts Map and the workspaces (Tasks 8–10) | after 035 and 026 are deployed | any |
| [037](docs/cards/037-s3c-wiring.md) | S3c-2: the clip producer reads the setup; `SETUP_SOURCE=db` a separate redeploy (Tasks 11–16) | after 036 is deployed | any |
| [038](docs/cards/038-s3c-experiments.md) | S3c-3: experiments and results (Tasks 17–21) | after 037 and 016 are deployed | any |
| [004](docs/cards/004-s3a-deploy.md) | S3a local login and Vercel deploy | after the owner's Vercel steps | any |
| [005](docs/cards/005-x2-resume.md) | X2 talking-head spike, resume | after O7 is ruled | any |

Migration-writing cards (S2, hooks, S3, S3c) take migrations in landing order, one at a time (S3 dashboard spec §8.7), and every code card is deployed before the next code card merges (#144). Migrations are numbered at landing (S2a's 0002 first, then whichever of hooks, S3 and S3c lands next; log #141, #620). Build order after the rollout (log #148): 014 → 031 → 015 and 022 → the rest, one deploy at a time.

Done: [001](docs/cards/001-x0-tooling.md) X0 tooling (PR #3) · [002](docs/cards/002-s1-finish.md) S1 code (PR #5) · [003](docs/cards/003-s3c-revision.md) S3c design (PR #6) · [006](docs/cards/006-s4-timeline.md) S4 Timeline renderer (PR #13) · [007](docs/cards/007-cleanup-docs.md) docs refresh (PR #11) · [008](docs/cards/008-x0-followups.md) X0 follow-ups (PR #14) · [009](docs/cards/009-s3-dashboard-design.md) dashboard design (PR #20) · [011](docs/cards/011-s2-design.md) S2 design and plan (PR #27) · [012](docs/cards/012-x4-visuals-music.md) X4 visuals and music spike (PR #28, #33) · [013](docs/cards/013-x0-small-fixes.md) X0 merge-aware scope check (PR #26) · [017](docs/cards/017-x0-ci-speed.md) X0 CI speed and repo hygiene (PR #37) · [019](docs/cards/019-s3-dashboard-plan.md) S3 dashboard v1 plan (PR #38) · [018](docs/cards/018-s3c-plan.md) S3c spec revision and plan (PR #44) · [020](docs/cards/020-hk-hooks-design.md) HK hook library spec and plan (PR #42) · [021](docs/cards/021-s5-media-design.md) S5 spec and plan (PR #41). Full list: [docs/cards/](docs/cards/README.md).

## Workstreams

| Workstream | Status | Continues at |
|---|---|---|
| **S0** posting assistant (plan C) | Live since 2026-09-29 (Dict-only) | Owner checks (above, item 3) |
| **S1** database, accounts, sources | Code merged and deployed Dict-only (2026-10-02); database not wired yet | **Task 22, the rollout** (runbook §4, step 6b before step 7), after O5 |
| **S2** publishing and autopilot | Designed (card 011, PR #27); ADR-27 and ADR-33 accepted; build cards written | Cards 014 → 015 → 016 after the rollout; 015's code waits for R5's real call |
| **HK** hook library | Designed and planned (card 020, PR #42); build cards 028–030 written | Card 028 after the rollout and card 014's deploy, before S6 |
| **S3** dashboard v1 | Designed (card 009) and planned (card 019, PR #38); build cards 022–027 written | Card 022 after the rollout and card 014's deploy, then one card per deploy |
| **S3a** dashboard shell | About 92% (68 unit, 21 Playwright tests) | Card 004, after the owner's Vercel steps |
| **S3c** account workspaces | Spec revised and planned (card 018, PR #44); build cards 035–038 written | Card 035 after cards 014 and 022 are deployed |
| **S4** Timeline renderer | Done (card 006, PR #13); deployed 2026-10-02 (render v4) | — (S5 next on this path) |
| **X0** working environment | Cards 001 and 008 done | Small items below |
| **X1** voice | Done (Qwen3-TTS primary, Kokoro fallback; `docs/studio/spikes/x1-voice.md`) | S5 (the TTS server) |
| **X2** talking head | Stopped at ~25% (~$0.40 of $30) | Card 005, after O7 |
| **S5** media servers and producer registry | Designed and planned (card 021, PR #41); build cards 031–034 written | Card 031 right after card 014's deploy |
| **X3–X6, S6+** | Not started | 06's cards |

## Open follow-ups (assigned, not yet done)

| Item | Goes to |
|---|---|
| A manual `clipforge status --rebuild` isn't blocked by the outage flag | card 010, checkpoint A |
| `DEPLOY_DB_CHECK` in `.env.example` (`s1/`'s file) | card 010, checkpoint A |
| The first new migration carries `jobs.error`, the `post_events.actor` column (backfilled from `data.actor`) and a pause actor on `posting_state` | card 014 (S2a's migration 0002), unless the hooks card or S3c lands a migration first |
| The `keywords_v1` comments in captions code and tests (the code loads `keywords_v2`) | the hooks card (it changes the captions prompt) |
| S4's deferred minors: the filter check doesn't run inside the Modal image; a `%` in a still's path reads as an image-sequence pattern; short b-roll padding; 1 ms string rounding; a loudness-mode label boundary | S5/S6 (stills and b-roll) |
| `gpu_doctor` should confirm `ZoneInfo` loads in the GPU image | card 010, checkpoint A |
| `web/scripts/pin-versions.mjs` undocumented; 4 high `npm audit` findings | card 004 |
| `--rollout-step 4c.7` dropped from `deploy.py` once Postgres reads are permanent | an X0 card at S1 Task 23 |
