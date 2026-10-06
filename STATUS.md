# Status

The one page that says where things stand. The coordinator updates it after every merged PR and every report. Detail lives in the linked files; this page only summarizes, and closed items move out (their record is in `docs/reports/` and the decision log).

Last updated: 2026-10-06 18:50 UTC (S2a PR 2 deployed 18:09 UTC, one-day watch running; HK-1a merged (#54), its deploy next; S2a PR 1 deployed 02:27 UTC; card 004 done, the dashboard is online; S2a PR 2 in review as PR #52; O7 ruled, card 005 unblocked; Task 23 after 2 clean verifies, card 040).

## Now

**Production.** The `clipforge` Modal app runs `9857082` (`deploy-20261006-1809`: S2a PR 2, the dispatcher replaces `posting_tick`, the brake, autopilot on Hands-on, the log-only gate; `policy dry-run`: 24 queued, 0 would be held). Neon's head is `0002`; HK-1a's `0003` (PR #54, merged) is applied just before its deploy. **S1 is live:** Neon (us-east-2) holds accounts, sources, the queue and job records, reads come from Postgres (`STATE_READS=postgres`), and every write is still mirrored to the Dict until card 040 (S1 Task 23), which merges after 2 clean daily verifies (log #154). One account, `realtalk-clips-en`; one source, `billy-garton`, with its permission facts not recorded (owner's decision, #225). **Posting is paused** (ADR-54): realtalk posts nothing until S2b publishes through Upload-Post, after the dashboard's Review page (card 024). `posting_daily` runs at 07:00 UTC; ops alerts are live. `clipforge status`: about 4.5 s on the server (target under 3 s; a follow-up, not urgent). Every deploy still needs `--rollout-step 4c.7` until card 040.

**Dashboard online** (card 004, PR #50): https://clipforge-web-brown.vercel.app, GitHub login for the owner only, Home over today's API (log #300–#302).

**Open PRs:** none. Sessions running: card 040 (S1 Task 23, `../clipForge-s1`), card 005 (X2, `../clipForge-x2`), card 028's PR 2 (`../clipForge-hk`, after PR 1 is deployed).

## Waiting on the owner (most important first)

1. **HK-1a deploy (PR #54):** `alembic upgrade head` (0003; migration review: safe, expand-only), then the deploy with `--rollout-step 4c.7`. A rollback keeps 0003's files (runbook §6 Rollback). **S2a's watch:** tomorrow after 07:00 UTC, one "Brake key … was missing; restored" alert is expected, and `posting verify` must show 0 differences (that's also clean verify 2 of 2 for card 040, if today's was clean).
2. **Next session:** card 031 (S5-1, the `modal_app/` split) can start now; it merges after HK-1a is deployed (#144).
3. **Billy Garton Jr.'s permission basis** (log #225): the source says `creator_agreement` but no facts are recorded; you credit him in descriptions. Before S2b publishes automatically, either get a one-line written OK from him (then `clipforge source edit billy-garton …`) or record the real basis. Nothing is held meanwhile.
4. **Dashboard follow-ups (card 004):** log in on your phone and compare Home with `/status`; before the next preview, `cd web && vercel env add MOCK_API preview ""` (value `1`).
5. **O3, the handles for founder.tapes and hombre.en.construccion** (checked free on TikTok, Instagram, YouTube and Facebook): needed **before card 016 (S2c)**.
6. **Branch protection for `main`:** require a PR and the `check` and `scope` checks; block force pushes (may need GitHub Pro on a private repo).
7. **X2's ~227 GB on the Volume:** keep it while card 005 runs, else `uv run modal volume rm -r clipforge-models x2`.
8. Before S2's auto-posting: O6 (clip series formats). Upload-Post **Basic** is bought at card 015's R5 step (O4, #139).
9. When you want CI to deploy: the GitHub secrets and variables, then `DEPLOY_ENABLED=true` (runbook §8 "still left").
10. ADR-53 (Langfuse tracing) is drafted in 05: accept or reject when you want tracing (an optional card after S6).
11. `git config user.name` is still the placeholder `<your name>`, so `deploy.sh` writes it into `docs/ops/deploys.md` (the coordinator fixes the rows). Set it once: `git config --global user.name "<your name>"`.

## Next cards (in order)

| Card | What | Can start | Runs alongside |
|---|---|---|---|
| [014](docs/cards/014-s2a-dispatch-gate.md) | S2a: rails (migration 0002, the dispatcher, the brake, autopilot on Hands-on, the gate log-only, routing; plan Tasks 1–8) | PR 1 deployed 2026-10-06; **PR 2 is #52**: merge, deploy, one clean day | card 028, 005, 040 (development) |
| [040](docs/cards/040-s1-task23.md) | S1 Task 23: retire the Dict posting store, `STATE_READS`, `POSTING_*` and the keep-alive; `deploy.py` drops `--rollout-step` | develop after #52 merges; **merge** after 2 clean verifies and #52 deployed with its clean day (#154) | 031, 028 (development) |
| [031](docs/cards/031-s5-split.md) | S5-1: `app.py` split into `modal_app/`, nothing live changes (S5 plan Task 1) | right after 014 is deployed, **before 022 or 015 starts** (#591) | — (022 and 015 wait for its deploy) |
| [022](docs/cards/022-s3b-admin.md) | S3-1: the `admin` endpoint, proxy auth, S3's migration (numbered at landing, after 0002), Settings, `upstream.ts` on `admin` (plan Tasks 1–5) | after card 010 is done **and** cards 014 and 031 are deployed with their owner steps (#144, #591); online after 004 | — (one deploy at a time) |
| [023](docs/cards/023-s3b-needs.md) | S3-2: "needs me", Home, `/act`, the link contract, alert Open buttons; every "needs me" row reaches Telegram as a notification with Open (Tasks 6–11) | after 022 is deployed | hooks, S5 (one deploy at a time) |
| [024](docs/cards/024-s3b-review.md) | S3-3: Review (Queue, Review lane), move to the front, Calendar (Tasks 12–15); **gates S2b** (ADR-54) | after 023 is deployed; the lane has rows once 015 is deployed; Re-render waits for the hooks build | hooks, S5 (one deploy at a time) |
| [015](docs/cards/015-s2b-publishing.md) | S2b: Upload-Post for realtalk on Hands-on, reviewed on the dashboard (R5's real call first; plan Tasks 9–19; Task 20 removed by ADR-54) | after 014 and 031 are deployed with one clean day, **and after 024 is deployed** (ADR-54); Basic bought for R5; the deploy needs the profile, webhook and both secrets | S3 cards after 024 (one deploy at a time) |
| [016](docs/cards/016-s2c-ladder-launch.md) | S2c: ladder, digest, failure rows, tracking links; founder.tapes and hombre launch (plan Tasks 21–26) | after 015 is deployed and a day on Hands-on with verify 0; O3, one permitted source each, two more profiles | S3 cards |
| [025](docs/cards/025-s3b-produce.md) | S3-4: Produce with batches, the Jobs tab, Resume, Sources (Tasks 16–18) | after 024 is deployed | S2 cards (after 015) |
| [026](docs/cards/026-s3b-results.md) | S3-5: Results → Costs, Compare, the account view (Tasks 19–21) | after 025 is deployed; strikes and Promote need 016 deployed | S2 cards |
| [027](docs/cards/027-s3b-cutover.md) | S3-5b: Telegram retirements, the CLI on `admin` and `web` public-only (#146) (Tasks 22–23; `REVIEW_BATCH` removed by ADR-54) | after 026 is deployed and each 7-day window (Produce online; `admin` live) | any |
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
| [005](docs/cards/005-x2-resume.md) | X2 talking-head spike, resume | **ready** (O7 ruled, log #153) | any |

Migration-writing cards (S2, hooks, S3, S3c) take migrations in landing order, one at a time (S3 dashboard spec §8.7), and every code card is deployed before the next code card merges (#144). Migrations are numbered at landing (S2a's 0002 first, then whichever of hooks, S3 and S3c lands next; log #141, #620). Build order after the rollout (ADR-54, log #149; replaces #148's): 014 → 031 → 004 → 022 → 023 → 024 → 015 → 016 → the rest, one deploy at a time (#144). S5-2 onward and the hooks and S3c cards slot in by their own dependencies.

Done: [001](docs/cards/001-x0-tooling.md) X0 tooling (PR #3) · [002](docs/cards/002-s1-finish.md) S1 code (PR #5) · [003](docs/cards/003-s3c-revision.md) S3c design (PR #6) · [006](docs/cards/006-s4-timeline.md) S4 Timeline renderer (PR #13) · [007](docs/cards/007-cleanup-docs.md) docs refresh (PR #11) · [008](docs/cards/008-x0-followups.md) X0 follow-ups (PR #14) · [009](docs/cards/009-s3-dashboard-design.md) dashboard design (PR #20) · [011](docs/cards/011-s2-design.md) S2 design and plan (PR #27) · [012](docs/cards/012-x4-visuals-music.md) X4 visuals and music spike (PR #28, #33) · [013](docs/cards/013-x0-small-fixes.md) X0 merge-aware scope check (PR #26) · [017](docs/cards/017-x0-ci-speed.md) X0 CI speed and repo hygiene (PR #37) · [019](docs/cards/019-s3-dashboard-plan.md) S3 dashboard v1 plan (PR #38) · [018](docs/cards/018-s3c-plan.md) S3c spec revision and plan (PR #44) · [020](docs/cards/020-hk-hooks-design.md) HK hook library spec and plan (PR #42) · [021](docs/cards/021-s5-media-design.md) S5 spec and plan (PR #41). · [010](docs/cards/010-s1-rollout.md) S1 rollout, live on Postgres (PR #47) · [039](docs/cards/039-s1-followups.md) S1 follow-ups (deployed 2026-10-05) · [004](docs/cards/004-s3a-deploy.md) dashboard online (PR #50) · Full list: [docs/cards/](docs/cards/README.md).

## Workstreams

| Workstream | Status | Continues at |
|---|---|---|
| **S0** posting assistant (plan C) | Live since 2026-09-29 (Dict-only); **paused 2026-10-05 (ADR-54)**, dormant code until removed | — (Upload-Post replaces it in S2b) |
| **S1** database, accounts, sources | Live on Postgres since 2026-10-05 (card 010), follow-ups deployed (card 039) | Card 040 (Task 23) after 2 clean verifies (#154) |
| **S2** publishing and autopilot | S2a PR 1 deployed 2026-10-06 (0002); PR 2 is #52 | Card 014's PR 2; 015 after card 024 is deployed (ADR-54), its code after R5's real call; then 016 |
| **HK** hook library | Designed and planned (card 020, PR #42); build cards 028–030 written | Card 028 after the rollout and card 014's deploy, before S6 |
| **S3** dashboard v1 | Designed (card 009) and planned (card 019, PR #38); build cards 022–027 written | Card 022 after cards 014, 031 and 004; 022 → 023 → 024 now come before S2b (ADR-54) |
| **S3a** dashboard shell | Done: online at https://clipforge-web-brown.vercel.app (card 004, PR #50) | — (S3 continues it, card 022) |
| **S3c** account workspaces | Spec revised and planned (card 018, PR #44); build cards 035–038 written | Card 035 after cards 014 and 022 are deployed |
| **S4** Timeline renderer | Done (card 006, PR #13); deployed 2026-10-02 (render v4) | — (S5 next on this path) |
| **X0** working environment | Cards 001 and 008 done | Small items below |
| **X1** voice | Done (Qwen3-TTS primary, Kokoro fallback; `docs/studio/spikes/x1-voice.md`) | S5 (the TTS server) |
| **X2** talking head | Stopped at ~25% (~$0.40 of $30) | Card 005, ready (O7 ruled, #153) |
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
| `--rollout-step 4c.7` dropped from `deploy.py` once Postgres reads are permanent | card 040 (log #154) |
