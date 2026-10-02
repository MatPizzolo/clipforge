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
| [017](017-x0-ci-speed.md) | X0: one CI run per commit, docs-only fast path, caches and timeouts, xdist measured, the flaky service test, PR template, dependabot, `scratch/` | proposed | — |
| [018](018-s3c-plan.md) | S3c: spec revised for ADR-48, ADR-50 and the migration order, then the implementation plan (no code) | proposed | — (the build: 010 done, S3's `admin` endpoint) |
| [019](019-s3-dashboard-plan.md) | S3: dashboard v1, the spec delta after S2's plan and the build plan in card-sized checkpoints (no code) | proposed | — (the build: 010 done, after 014's routes; online: 004) |
| [020](020-hk-hooks-design.md) | HK: the hook library, spec and plan (no code) | proposed | — (the build: 010 done, its migration after 014's) |
| [021](021-s5-media-design.md) | S5: media servers and producer registry, spec and plan (no code) | proposed | PR #33 (card 012) merged |
