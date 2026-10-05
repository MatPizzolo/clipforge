# Cards

A card is the complete brief for one session: context, scope, numbered actions, checkpoints, "done when", owner steps and a cost cap. The coordinator writes cards; the owner commits them and starts a session with one line:

```
Run card docs/cards/NNN-<stream>-<topic>.md
```

- **Numbering:** three digits, never reused. The file name keeps its number when the status changes.
- **Status line** (first lines of each card): `proposed` → `sent YYYY-MM-DD` → `done YYYY-MM-DD (report: …)`, or `superseded by NNN`. The coordinator updates it.
- **Template:** `docs/templates/card.md`. Stop cards: `docs/templates/stop-card.md`.
- **Reports:** every card's session writes `docs/reports/NNN-<stream>-<YYYY-MM-DD>.md` (template `docs/templates/handoff-report.md`).
- **Scope:** a card's "may edit" list must match `scripts/scopes.toml` for its branch prefix; CI's scope check enforces it.

| Card | Stream | Status | Depends on |
|---|---|---|---|
| [001](001-x0-tooling.md) | X0 working environment and controls (incl. `.claude/` hooks, permissions, agents, skills) | done 2026-09-30 (PR #3) | `gh` installed |
| [002](002-s1-finish.md) | S1 finish (stop before the rollout) | done 2026-10-01 (PR #5) | 001 merged |
| [003](003-s3c-revision.md) | S3c design revision | done 2026-09-30 (PR #6) | 001 merged |
| [004](004-s3a-deploy.md) | S3a local login and Vercel deploy | proposed | 001 merged, the owner's Vercel steps, merge after 002 |
| [005](005-x2-resume.md) | X2 talking-head spike, resume | proposed | 001 merged, O7 ruled |
| [006](006-s4-timeline.md) | S4 Timeline renderer | done 2026-10-01 (PR #13) | 002 merged |
| [007](007-cleanup-docs.md) | Docs: audit and refresh every Markdown file to match main; propose removing unused files | done 2026-10-01 (PR #11) | 002 merged |
| [008](008-x0-followups.md) | X0: `deploy.py` checks the migration head, CI deploys tagged, Stop hook on main/coord | done 2026-10-01 (PR #14) | 002 merged |
| [009](009-s3-dashboard-design.md) | S3: the dashboard as the studio's control room (brainstorm, IA, autopilot model, mockups, spec; design only) | done 2026-10-01 (PR #20) | — |
| [010](010-s1-rollout.md) | S1: the rollout (Task 22) with the owner: two small fixes, then runbook §4c step by step, then evidence | A merged (PR #31); B next | 002 + 006 deployed, one clean night, O5 |
| [011](011-s2-design.md) | S2: publishing and autopilot, design and plan (no code) | done 2026-10-02 (PR #27) | — |
| [012](012-x4-visuals-music.md) | X4: stills, b-roll and music beds: licenses, cost, quality, one end-to-end Timeline | done 2026-10-02 (PR #28, #33) | — |
| [013](013-x0-small-fixes.md) | X0: scope check aware of merges in progress | done 2026-10-02 (PR #26) | — |
| [014](014-s2a-dispatch-gate.md) | S2a: rails: migration 0002, the dispatcher, the brake, autopilot on Hands-on, the gate (log-only) and routing (plan Tasks 1–8) | proposed | 010 done (step 7 verified, verify 0, schedule copies, Neon head 0001) |
| [015](015-s2b-publishing.md) | S2b: Upload-Post publishing for realtalk on Hands-on: R5's real call first, then publish state, webhook, reconcile, review cards, hand-off (plan Tasks 9–20) | proposed | 014 deployed + one clean day; Basic bought; R5 read by the owner |
| [016](016-s2c-ladder-launch.md) | S2c: the ladder, the digest, failure rows, tracking links; founder.tapes and hombre launch (plan Tasks 21–26) | proposed | 015 deployed + a day on Hands-on; O3; one permitted source each; two more profiles |
| [017](017-x0-ci-speed.md) | X0: one CI run per commit, docs-only fast path, caches and timeouts, xdist measured, the flaky service test, PR template, dependabot, `scratch/` | done 2026-10-02 (PR #37) | — |
| [018](018-s3c-plan.md) | S3c: spec revised for ADR-48, ADR-50 and the migration order, then the implementation plan (no code) | done 2026-10-05 (PR #44) | — (the build: cards 035–038) |
| [019](019-s3-dashboard-plan.md) | S3: dashboard v1, the spec delta after S2's plan and the build plan in card-sized checkpoints (no code) | done 2026-10-02 (PR #38) | — (the build: cards 022–027) |
| [020](020-hk-hooks-design.md) | HK: the hook library, spec and plan (no code) | done 2026-10-05 (PR #42) | — (the build: cards 028–030) |
| [021](021-s5-media-design.md) | S5: media servers and producer registry, spec and plan (no code) | done 2026-10-05 (PR #41) | PR #33 (card 012) merged (the build: cards 031–034) |
| [022](022-s3b-admin.md) | S3-1: the `admin` endpoint, proxy auth, S3's migration, Settings, `upstream.ts` on `admin` (plan Tasks 1–5) | proposed | 010 done; 014 deployed with its owner steps; online: 004 |
| [023](023-s3b-needs.md) | S3-2: "needs me", runway, scoreboard and slots, Open buttons and alert redraw, Home, `/act`, the link contract (plan Tasks 6–11) | proposed | 022 deployed |
| [024](024-s3b-review.md) | S3-3: Review (Queue and Review lane), move to the front, batch approve, pause, Calendar (plan Tasks 12–15) | proposed | 023 deployed; lane rows need 015 deployed; Re-render waits for the hooks build |
| [025](025-s3b-produce.md) | S3-4: Produce with batches and estimates, the Jobs tab, Resume, Sources (plan Tasks 16–18) | proposed | 024 deployed |
| [026](026-s3b-results.md) | S3-5: Results → Costs, Compare, the account read view (plan Tasks 19–21) | proposed | 025 deployed; strikes and Promote need 016 deployed |
| [027](027-s3b-cutover.md) | S3-5b: `/clip`, `/status <id>` and typed `/resume` retired; the CLI on `admin`, `web` public-only (#146); `REVIEW_BATCH` off (plan Tasks 22–23) | proposed | 026 deployed, then each 7-day window |
| [028](028-hk-library.md) | HK-1: the hook library: migration (numbered at landing), seeds, rotation on jobs, control stamps, `/admin` hooks routes and `clipforge hooks` (plan Tasks 1–6) | proposed | 010 done; 014 deployed |
| [029](029-hk-variants.md) | HK-2: `keywords_v3` hook variants behind `HOOK_VARIANTS`, ranking, ratings, re-render (plan Tasks 7–11); the flag flip is a separate owner redeploy (ADR-49 window) | proposed | 028 deployed; fallbacks where 015, 016, 022, 023, 024 aren't |
| [030](030-hk-page.md) | HK-3: the interim `/hooks?account=` page (plan Task 12) | proposed | 029 and 022 deployed; skipped if S3c's Hooks tab ships first |
| [031](031-s5-split.md) | S5-1: `app.py` split into `modal_app/`, nothing live changes (plan Task 1) | proposed | 014 deployed; before 015 or 022 starts (#591) |
| [032](032-s5-registry.md) | S5-2: the producer registry and one engine, clips unchanged under a golden test, `hello` on CPU (plan Tasks 2–6) | proposed | 031 deployed; slotted between deployed cards, never with 025 or the caps change open (#603) |
| [033](033-s5-media.md) | S5-3: `media/` protocols and `registry.toml`, `narrate`/`stills`/`music` stages, renderer additions; deploys alone (plan Tasks 7–11) | proposed | 032 deployed |
| [034](034-s5-servers.md) | S5-4: weights, the Narrator, stills and music servers, hello end to end on an L4 (plan Tasks 12–15) | proposed | 033 deployed |
| [035](035-s3c-data.md) | S3c-1a: versioned setup: migration (numbered at landing), resolver, versions service, preview, `setup import`/`verify`, routes, `PATCH` (plan Tasks 1–7) | proposed | 010 done; 014 and 022 deployed |
| [036](036-s3c-pages.md) | S3c-1b: the Accounts Map and the category, blueprint and account workspaces (plan Tasks 8–10) | proposed | 035 and 026 deployed |
| [037](037-s3c-wiring.md) | S3c-2: the clip producer reads the setup; `SETUP_SOURCE=db` is a separate owner redeploy (plan Tasks 11–16) | proposed | 036 deployed (014 for `FormatWindowSource`) |
| [038](038-s3c-experiments.md) | S3c-3: experiments and results, the digest line, the needs row, the hooks freeze (plan Tasks 17–21) | proposed | 037 and 016 deployed |
