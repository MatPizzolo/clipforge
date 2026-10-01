# Status

The one page that says where things stand. The coordinator updates it after every merged PR and every report. Detail lives in the linked files; this page only summarizes, and closed items move out (their record is in `docs/reports/` and the decision log).

Last updated: 2026-10-01.

## Now

**Production.** The `clipforge` Modal app runs the code deployed on 2026-09-30, Dict-only (`STATE_READS=dict`, no database wired). `posting_tick` runs every 5 minutes; deploy blackout in runbook §1.

**Merged but not deployed:** card 002 (S1). The next `scripts/deploy.sh`:
- replaces the `posting_keepalive` cron with `posting_daily` (same 07:00 UTC slot; a daily idempotent rebuild; the sticky `posting:outage` flag);
- adds ⚠️ ops alerts (failed channel and CLI jobs, tick and daily errors, within ADR-45's limits) and `db_doctor`;
- mounts `blueprints/`.

The database stays unwired until `DATABASE_URL` is back in the Modal secret at rollout step 2 (runbook §4).

**Open PRs:**

| PR | What | State |
|---|---|---|
| #13 | Card 006, S4 Timeline renderer | Group 1 done (CP2: contracts, clip builder, filtergraph builders; render unchanged in production); Group 2 next (two-pass loudness, render on the Timeline, version 4) |

## Waiting on the owner (most important first)

1. **O3 and O5: the only blockers for S1's rollout (Task 22).** O3: the final handles for founder.tapes and hombre.en.construccion, checked free on TikTok, Instagram, YouTube and Facebook. O5: Billy Garton Jr.'s permission record (granted when and by whom, where the agreement is stored, monetization yes/no, translations yes/no, any expiry). Then the coordinator writes the rollout card.
2. **Take `DATABASE_URL` out of `clipforge-secrets`** (Modal dashboard → Secrets → Edit → delete that key only; never recreate the secret from `.env`). Do it before the next deploy.
3. **O7, WenetSpeech-pretrained models (gates card 005):** **treat as "needs review"; prefer LongCat 1.5 unless a wav2vec model is clearly better in the X2 blind test.**
4. **The S0 checks:** the phone test (`/status`, `/next`, ✅ on and off, ⏭, 🗑 + reason, `/pause`, `/go`), one scheduled slot end to end, and the 07:00 UTC daily log line with its snapshot (`uv run modal app logs clipforge`).
5. **Branch protection for `main`:** require a PR and the `check` and `scope` checks; block force pushes (may need GitHub Pro on a private repo).
6. **The Vercel steps (runbook §5b), when you want the dashboard online:** they unlock card 004.
7. **X2's ~227 GB on the Volume:** **keep it if card 005 runs within a couple of weeks**, else `uv run modal volume rm -r clipforge-models x2`.
8. **Deploy card 002's code** whenever you like, after step 2 and outside the blackout: `scripts/deploy.sh --dry-run`, then `scripts/deploy.sh --reason "card 002"`.
9. Before S2: O4 (Upload-Post plan) and O6 (clip series formats).
10. When you want CI to deploy: the GitHub secrets and variables, then `DEPLOY_ENABLED=true` (runbook §8 "still left" has the `gh` commands).

## Next cards

| Card | What | Can start | Runs alongside |
|---|---|---|---|
| [006](docs/cards/006-s4-timeline.md) | S4 Timeline renderer | **sent 2026-10-01** (plan approved; Group 1 done, CP2) | 004, 005 |
| rollout (to write) | S1 Task 22, run with the owner: migrate, deploy, accounts, sources, import, verify, switch reads | after O3 and O5 | — |
| S3c plan (to write) | S3c implementation plan, on S1's final schema | now (card to write) | 006 |
| [004](docs/cards/004-s3a-deploy.md) | S3a local login and Vercel deploy | after the owner's Vercel steps | 006, 005 |
| [005](docs/cards/005-x2-resume.md) | X2 talking-head spike, resume | after O7 is ruled | 004, 006 |

Done: [001](docs/cards/001-x0-tooling.md) X0 tooling (PR #3) · [002](docs/cards/002-s1-finish.md) S1 code (PR #5) · [003](docs/cards/003-s3c-revision.md) S3c design (PR #6) · [007](docs/cards/007-cleanup-docs.md) docs refresh (PR #11) · [008](docs/cards/008-x0-followups.md) X0 follow-ups (PR #14). Full list: [docs/cards/](docs/cards/README.md).

## Workstreams

| Workstream | Status | Continues at |
|---|---|---|
| **S0** posting assistant (plan C) | Live since 2026-09-29 (Dict-only) | Owner checks only (above, item 4) |
| **S1** database, accounts, sources | Code finished and merged (card 002, PR #5; 1057 fast tests at merge) | **Task 22, the rollout** (runbook §4, step 6b before step 7), after O3 and O5 |
| **X0** working environment | Cards 001 and 008 done: the gate, scopes, worktree and deploy scripts (blackout, migration head behind `DEPLOY_DB_CHECK`), CI deploy tags, guardrails, failing-step log | Small items below |
| **S2** publishing | Not started | After S1's rollout. 04 S2 lists the ADR-44/45 items |
| **S3a** dashboard shell | About 92% (68 unit, 21 Playwright tests) | Card 004, after the owner's Vercel steps |
| **S3** dashboard v1 | Not started | 06's S3 card, after S1. Owns the `admin` endpoint (D9) and the pre-S2 Review page (D8) |
| **S3c** account workspaces | Design accepted (ADR-42) | A plan card now that S1 is final; its migration 0002 also carries the items below |
| **S4** Timeline renderer | Spec approved (ADR-47) | Card 006: the plan, then the build |
| **X1** voice | Done (Qwen3-TTS primary, Kokoro fallback; `docs/studio/spikes/x1-voice.md`) | S5 (the TTS server) |
| **X2** talking head | Stopped at ~25% (~$0.40 of $30) | Card 005, after O7 |
| **X3–X6, S5+** | Not started | 06's cards |

## Open follow-ups (assigned, not yet done)

| Item | Goes to |
|---|---|
| A manual `clipforge status --rebuild` isn't blocked by the outage flag | the rollout card |
| `DEPLOY_DB_CHECK` in `.env.example` (card 008's flag; `.env.example` is `s1/`'s file) | the rollout card |
| Migration 0002: a `jobs.error` column, the `post_events.actor` column (backfilled from `data.actor`), a pause actor on `posting_state` | the S3c plan |
| The `keywords_v1` comments in captions code and tests (the code loads `keywords_v2`) | card 006 |
| `web/scripts/pin-versions.mjs` undocumented; 4 high `npm audit` findings | card 004 |
| `--rollout-step 4c.7` dropped from `deploy.py` once Postgres reads are permanent | an X0 card at S1 Task 23 |
| The scope check reports `main`'s files as out of scope during an uncommitted merge (seen in card 008) | that X0 card |
| The S1 addendum (A1–A6) and S3c's D1–D10 | **closed**: card 002's report and the S3c spec's status block; D8 and D9 are in 06's S3 card |
