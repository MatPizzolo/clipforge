# Status

The one page that says where things stand. The coordinator updates it after every merged PR and every report. Detail lives in the linked files; this page only summarizes, and closed items move out (their record is in `docs/reports/` and the decision log).

Last updated: 2026-10-02 (cards 002 + 006 + tzdata deployed; Dict-only restart at 03:14 UTC; card 013 merged; 011 at checkpoint A, 012 running).

## Now

**Production.** The `clipforge` Modal app runs the code of `dea435d` (deployed 2026-10-02 02:10 UTC; restarted from `6e832a7`, docs-only changes, at 03:14 UTC), Dict-only (`STATE_READS=dict`, `DATABASE_URL` not in `clipforge-secrets`). `posting_tick` runs every 5 minutes; deploy blackout in runbook §1. The first clean night is in: `posting_daily` ran at 07:00 UTC on 2026-10-02 (420 keys touched, a 36-key snapshot, rebuild 0), and the 08:00 and 10:30 slots sent. Two clips wait on the owner's taps, so the tick says "waiting" until they're answered.

**Incident, 2026-10-02 (fixed 03:14 UTC):** `DATABASE_URL` was in the secret before rollout step 1's migration, so every read of `sources` or `jobs` hit an empty database: `GET /posting` answered 500, and `/next` and Telegram taps that send the next clip failed (the Dict stayed primary; nothing was lost). The owner removed the key and redeployed (`docs/ops/deploys.md`). Card 010 now checks the key is absent before step 1.

**Deployed 2026-10-02 02:10 UTC** (`deploy-20261002-0210`, `dea435d`): cards 002 (S1) and 006 (S4), and `tzdata`:
- replaces the `posting_keepalive` cron with `posting_daily` (same 07:00 UTC slot; a daily idempotent rebuild; the sticky `posting:outage` flag);
- adds ⚠️ ops alerts (failed channel and CLI jobs, tick and daily errors, within ADR-45's limits) and `db_doctor`, and mounts `blueprints/`;
- switches render to the Timeline (version 4, two-pass loudness, ADR-47): every clip re-renders on its next job;
- installs `tzdata` in every image, so alerts from GPU steps work.

**Decided today (card 009):** the dashboard is the studio's control room, inbox-first, for a ~20-minute daily phone check-in. Each account runs on autopilot as far as it has earned: three switches and a review dial, a graduation ladder where promotions are always the owner's tap (ADR-48). A new producer version opens only a 5-item review window (ADR-49). Hooks get a versioned library with rotation (ADR-50). founder.tapes and hombre.en.construccion launch with S2, which is now the next big step after S1's rollout.

**Open PRs:** #27 (card 011, S2 spec, revised after the coordinator's review; checkpoint B, the plan, next) · #28 (card 012, X4 checkpoint A; merges after checkpoint B).

## Waiting on the owner (most important first)

1. ✅ O5 collected (2026-10-01). You type the facts into `clipforge source edit` at rollout step 4; they live only in the database.
2. ✅ Cards 002 + 006 + tzdata deployed (2026-10-02 02:10 UTC). Check tomorrow's first `posting_daily:` log line (07:00 UTC).
3. **Answer the 2 clips waiting since 10:30** (✅, ⏭ or 🗑). The rest of the **S0 checks**: `/status`, `/next`, ✅ on and off, ⏭, 🗑 + reason, `/pause`, `/go`, and one scheduled slot end to end.
4. **O3, the handles for founder.tapes and hombre.en.construccion** (checked free on TikTok, Instagram, YouTube and Facebook): now needed **before S2**, not before the rollout.
5. **O7, WenetSpeech-pretrained models (gates card 005):** **treat as "needs review"; prefer LongCat 1.5 unless a wav2vec model is clearly better in the X2 blind test.**
6. **Branch protection for `main`:** require a PR and the `check` and `scope` checks; block force pushes (may need GitHub Pro on a private repo).
7. **The Vercel steps (runbook §5b), when you want the dashboard online:** they unlock card 004.
8. **X2's ~227 GB on the Volume:** **keep it if card 005 runs within a couple of weeks**, else `uv run modal volume rm -r clipforge-models x2`.
9. Before S2: O4 (Upload-Post plan) and O6 (clip series formats).
10. When you want CI to deploy: the GitHub secrets and variables, then `DEPLOY_ENABLED=true` (runbook §8 "still left").

## Next cards (in order)

| Card | What | Can start | Runs alongside |
|---|---|---|---|
| [010](docs/cards/010-s1-rollout.md) | S1 rollout (Task 22) with the owner: two small fixes, then runbook §4c step by step, then evidence | **ready**: clean night and slot sends on 2026-10-02 (O5 ✅); start checkpoint A now, the live steps outside a blackout | — |
| hooks (to write) | HK: the hook library (ADR-50): pattern versions, item stamps, clip hook variants, rotation, ranking, the Hooks tab | after the rollout | S3c plan |
| [011](docs/cards/011-s2-design.md) | S2 design and plan (no code): publishing, autopilot (ADR-48, 49), the dispatcher (ADR-27), the gate, tracking links | **checkpoint A: spec under the coordinator's review** (`../clipForge-s2`) | 010, 012 |
| [012](docs/cards/012-x4-visuals-music.md) | X4 spike: stills, b-roll, music beds ($15 cap); feeds S5 → S6 | **running** (`../clipForge-x4`) | 010, 011 |
| S2 build (to write) | From card 011's plan; founder.tapes and hombre launch | after the rollout, card 011 and O3 | hooks, S3 |
| S3 (to write) | Dashboard v1 from card 009's spec: Home "needs me", `/act`, Review, Produce, Results, Settings, Compare | after the rollout | S2 |
| S3c plan (to write) | S3c implementation plan, with the S3 dashboard spec §10.3 applied | now (card to write) | hooks |
| [004](docs/cards/004-s3a-deploy.md) | S3a local login and Vercel deploy | after the owner's Vercel steps | any |
| [005](docs/cards/005-x2-resume.md) | X2 talking-head spike, resume | after O7 is ruled | any |

Migration-writing cards (S2, hooks, S3c) take migrations in landing order, one at a time (S3 dashboard spec §8.7).

Done: [001](docs/cards/001-x0-tooling.md) X0 tooling (PR #3) · [002](docs/cards/002-s1-finish.md) S1 code (PR #5) · [003](docs/cards/003-s3c-revision.md) S3c design (PR #6) · [006](docs/cards/006-s4-timeline.md) S4 Timeline renderer (PR #13) · [007](docs/cards/007-cleanup-docs.md) docs refresh (PR #11) · [008](docs/cards/008-x0-followups.md) X0 follow-ups (PR #14) · [009](docs/cards/009-s3-dashboard-design.md) dashboard design (PR #20) · [013](docs/cards/013-x0-small-fixes.md) X0 merge-aware scope check (PR #26). Full list: [docs/cards/](docs/cards/README.md).

## Workstreams

| Workstream | Status | Continues at |
|---|---|---|
| **S0** posting assistant (plan C) | Live since 2026-09-29 (Dict-only) | Owner checks (above, item 3) |
| **S1** database, accounts, sources | Code merged and deployed Dict-only (2026-10-02); database not wired yet | **Task 22, the rollout** (runbook §4, step 6b before step 7), after O5 |
| **S2** publishing and autopilot | Not started; grew with ADR-48/49 and the dispatcher | Its card after the rollout; 04's S2 list is the source |
| **HK** hook library | Designed (ADR-50, S3 dashboard spec §8.5) | Its card after the rollout, before S6 |
| **S3** dashboard v1 | Designed (card 009: spec and mockups in `docs/design/dashboard/`) | Its card after the rollout, alongside S2 |
| **S3a** dashboard shell | About 92% (68 unit, 21 Playwright tests) | Card 004, after the owner's Vercel steps |
| **S3c** account workspaces | Design accepted (ADR-42), amended by ADR-48 and ADR-50 | A plan card |
| **S4** Timeline renderer | Done (card 006, PR #13); deployed 2026-10-02 (render v4) | — (S5 next on this path) |
| **X0** working environment | Cards 001 and 008 done | Small items below |
| **X1** voice | Done (Qwen3-TTS primary, Kokoro fallback; `docs/studio/spikes/x1-voice.md`) | S5 (the TTS server) |
| **X2** talking head | Stopped at ~25% (~$0.40 of $30) | Card 005, after O7 |
| **X3–X6, S5+** | Not started | 06's cards |

## Open follow-ups (assigned, not yet done)

| Item | Goes to |
|---|---|
| A manual `clipforge status --rebuild` isn't blocked by the outage flag | card 010, checkpoint A |
| `DEPLOY_DB_CHECK` in `.env.example` (`s1/`'s file) | card 010, checkpoint A |
| The first new migration carries `jobs.error`, the `post_events.actor` column (backfilled from `data.actor`) and a pause actor on `posting_state` | whichever of S2, hooks or S3c writes the first migration |
| The `keywords_v1` comments in captions code and tests (the code loads `keywords_v2`) | the hooks card (it changes the captions prompt) |
| S4's deferred minors: the filter check doesn't run inside the Modal image; a `%` in a still's path reads as an image-sequence pattern; short b-roll padding; 1 ms string rounding; a loudness-mode label boundary | S5/S6 (stills and b-roll) |
| `gpu_doctor` should confirm `ZoneInfo` loads in the GPU image | card 010, checkpoint A |
| `web/scripts/pin-versions.mjs` undocumented; 4 high `npm audit` findings | card 004 |
| `--rollout-step 4c.7` dropped from `deploy.py` once Postgres reads are permanent | an X0 card at S1 Task 23 |
