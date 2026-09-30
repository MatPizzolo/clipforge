# Status

The one page that says where things stand. The coordinator updates it after every merged PR and every report. Detail lives in the linked files; this page only summarizes.

Last updated: 2026-09-30 (the pause, tag `pause-2026-09-30`). Production: the `clipforge` Modal app is live and Dict-only (`STATE_READS=dict`, no database wired); `posting_tick` runs every 5 minutes; deploy blackout in runbook §1.

## Next cards (in order)

| Card | What | Can start | Runs alongside |
|---|---|---|---|
| [001](docs/cards/001-x0-tooling.md) | X0: check.sh, scope check, docs tests, CI, worktree and deploy scripts, and `.claude/` guardrails (hooks, permissions, agents, skills) | now (after `gh` is installed) | nothing (everyone else needs its scripts) |
| [002](docs/cards/002-s1-finish.md) | S1 finish, stop before the rollout | after 001 is merged | 003, 005 |
| [003](docs/cards/003-s3c-revision.md) | S3c design revision (D3, D4, D10) | after 001 is merged | 002, 004, 005 |
| [004](docs/cards/004-s3a-deploy.md) | S3a local login and Vercel deploy | after the owner's Vercel steps | 002, 003, 005 (merge after 002) |
| [005](docs/cards/005-x2-resume.md) | X2 talking-head spike, resume | after O7 is ruled | 002, 003, 004 |
| [006](docs/cards/006-s4-timeline.md) | S4 Timeline renderer | after 002 is merged | 003, 004, 005 |

## Workstreams
| Workstream | Status | Last finished | Continues at |
|---|---|---|---|
| **S0** posting assistant (plan C) | Live since 2026-09-29, redeployed 2026-09-30 (Dict-only). The session ended long ago | Plan C Tasks 1–6 and its final review | Owner checks only (below): phone test, one scheduled slot, the 07:00 UTC keep-alive line and first snapshot |
| **S1** database, accounts, sources | About 80%, stopped cleanly. Fast suite 736 passed | Tasks 1–20, fix card 1 (13b), checkpoint D fixes, addendum A1 (ADR-43 derived `producer_version`, one sanitizer) | card 002: the plan's STATUS block, then A2 → A6, Task 21b, the final review; **stop before Task 22** |
| **S2** publishing | Not started | — | After S1's rollout (Task 22). 04 S2 lists the ADR-44/45 items added on 2026-09-30 |
| **S3a** dashboard shell | About 92%. 68 unit tests, 21 Playwright tests pass | Tasks 1–11, checkpoint G (laptop layout), the audit fix card, deep links (#99) | `docs/superpowers/plans/2026-09-29-studio-s3a.md` Task 12 (a real local GitHub login, needs the local OAuth app) and Task 13 (Vercel deploy), both waiting on the owner's Vercel steps (§5b) |
| **S3** dashboard v1 | Not started | — | 06's S3 card, after S1. It owns the `admin` endpoint (D9) and the pre-S2 Review page (D8) |
| **S3c** account workspaces | Design written, **awaiting the owner's review** (spec sections 1–6 approved in chat) | `docs/superpowers/specs/2026-09-30-studio-s3-workspaces-design.md`; the ADR-42 draft in 05 | card 003 (revise for D3, D4, D10), then the owner's review, then a plan only after S1's final review |
| **S4+** (Timeline, media servers, producers) | Not started | — | card 006, after card 002 is merged (S4 edits `models.py` and `stages/`) |
| **X1** voice | Done | Qwen3-TTS primary, Kokoro fallback (#69); report `docs/studio/spikes/x1-voice.md` | Continues in S5 (the TTS server and its guard, #72) |
| **X2** talking head | Stopped at ~25% (licenses checked, no clips, ~$0.40 of $30) | `docs/studio/spikes/x2-talking-head.md` | card 005, after the owner rules on O7 |
| **X3–X6** | Not started | — | 06's cards |

## Addendum tracker
S1's plan names its own addendum steps A1–A6 by task. The coordinator's items map onto them:

| Item | S1 plan step | Status |
|---|---|---|
| Derived `producer_version` (ADR-43), `build` = git SHA | A1 | done (#111; `clips:14fcf790` at the pause) |
| One sanitizer (`sanitize.clean` / `redact`) | A1 | done (R29: split into two audiences) |
| Task 21 split: 21a (blueprints mounted, read-only `db_doctor`, `.env.example`) / 21b (DB wired, deployed only at 4c.2) | A2 = 21a; 21b | open (21a's brief is written) |
| Platforms = account ∩ permission, account from the source | Task 14 | built; the "frozen per item" test is still to add (A3) |
| Slot guard from sends (#77) | A3 | open |
| Slot computed before any DB call, schedule copy in the Dict | A3 | open |
| Hashtags from the account in postgres mode | Task 15 / A3 | partly done; test the postgres-mode path in A3 |
| `add_send` failure rollback | Task 15 | done (#95) |
| `posting/actions.py`, actor on every write, DB-down answers, `statement_timeout` | A4 | open (the per-account chat check is done, Task 16) |
| Bot URL buttons from `DASHBOARD_URL` (ADR-44 deep links) | A4 (added by the coordinator at the pause) | open |
| Job view and overview from the `jobs` table, additive fields | A5 | open |
| `ops_alert` + `posting_daily` (ADR-45, ADR-46) | A6 | open (`verify_daily` exists to build on) |
| Task 23 deletion conditions | plan addendum | done (written; enforced at Task 23) |
| Ledger rulings copied into the log | — | done |
| S3c D1 one setup id | S3c | **closed**: `(account_id, account_version)` with pinned parents (#88) |
| S3c D2 `PATCH /accounts` saves a version with an actor | S3c spec §5.1 | done in design |
| S3c D3 `post_events.actor` column in 0002 | S3c | open (card 2) |
| S3c D4 one dry-run preview for save and experiment start | S3c | open (card 2) |
| S3c D5 edits apply to new items only | S3c spec §3.2 | done in design |
| S3c D6 home tasks / Telegram role per page | 08 §2 | done at the pause (08 §2 column and §2b) |
| S3c D7 keep/revert only on the experiment page | S3c spec §2.6 | mostly done; state it explicitly (card 2) |
| S3c D8 pre-S2 Review page as a queue manager | S3 | open (in 08 §2; the S3 card must build it) |
| S3c D9 `admin` = second ASGI app with its own `ADMIN_API_TOKEN` | S3 | open (S3's decision; card 2 adds it to 06's S3 card) |
| S3c D10 deep-link formats, `DASHBOARD_URL` | 08 §2b; S1 A4; S3c | formats written in 08 §2b; the bot side is S1 A4 |
| S3a fix card 2, deep-link card | S3a | done (#82, #83, #99) |

## Owner: open decisions and steps (recommendations in bold)
1. ✅ Done at the pause: `web/openapi.json` regenerated, 68 web tests green.
2. ✅ The pause commit `405c8ec`, the tag and the push are done. Still open: check that CI is green at https://github.com/MatPizzolo/clipforge/actions (`check` green, `deploy` skipped, `web` green), and take `DATABASE_URL` out of `clipforge-secrets` (§8 step 5; **the dashboard way**).
3. Read-only git for the coordinator: **allow it**, so audits compare the tree against commits.
4. The S0 checks: the phone test (`/status`, `/next`, ✅ on and off, ⏭, 🗑 + reason, `/pause`, `/go`), one scheduled slot end to end, and the 07:00 UTC keep-alive log line with its first snapshot (`uv run modal app logs clipforge`).
5. O3, the handles for founder.tapes and hombre.en.construccion, and O5, Billy Garton Jr.'s permission facts. **Collect both before S1's rollout (Task 22).**
6. O7, WenetSpeech-pretrained models: **treat as "needs review"; prefer LongCat 1.5 unless a wav2vec model is clearly better in the X2 blind test.**
7. Review the S3c spec and accept ADR-42 (after card 003): **accept once D3, D4 and D10 are in.**
8. X2's ~227 GB on the Volume: **keep it if X2 resumes within a couple of weeks**, else `uv run modal volume rm -r clipforge-models x2`.
9. The Vercel steps (§5b), when you want the dashboard online: they unlock S3a Task 12/13.
10. O4 (Upload-Post plan) and O6 (clip series formats): before S2.
11. Later, not now: the Actions secrets and `DEPLOY_ENABLED` (§8 "still left").

