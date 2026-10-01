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
| [006](006-s4-timeline.md) | S4 Timeline renderer | sent 2026-10-01 (PR #13) | 002 merged |
| [007](007-cleanup-docs.md) | Docs: audit and refresh every Markdown file to match main; propose removing unused files | done 2026-10-01 (PR #11) | 002 merged |
| [008](008-x0-followups.md) | X0: `deploy.py` checks the migration head, CI deploys tagged, Stop hook on main/coord | done 2026-10-01 (PR #14) | 002 merged |
| [009](009-s3-dashboard-design.md) | S3: the dashboard as the studio's control room (brainstorm, IA, autopilot model, mockups, spec; design only) | proposed | — |
