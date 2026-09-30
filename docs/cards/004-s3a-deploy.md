# Card 004: S3a — local login and the Vercel deploy (Tasks 12–13)

Status: proposed (only after the owner's Vercel steps, runbook §5b)
Stream: S3a · Branch: `s3a/deploy` · Worktree: `../clipForge-web`
Decision-log range: #300–#319
Model: mid-tier
Depends on: card 001 merged; the owner's Vercel steps; merge after card 002 (both touch `CLAUDE.md`)
Cost cap: $0 Modal (Vercel Pro is $20/mo)

## Context
S3a stopped at the pause with every web check green. Tasks 12–13 of `docs/superpowers/plans/2026-09-29-studio-s3a.md` remain. A preview proves only the build and the redirect to `/login` (#83); GitHub login works on localhost and on the production domain. Deep links keep their target through login (#99).

## Read first
1. `CLAUDE.md`, `STATUS.md`, `web/README.md`
2. The S3a plan, Tasks 12–13, and runbook §5

## Scope
As `scripts/scopes.toml` allows for `s3a/`.

## Actions
1. **Task 12:** a real local GitHub login, using the local OAuth app, on the laptop.
2. **Task 13:** `vercel deploy` (a preview), then production only after the owner's OK. The owner logs in on the phone and on the laptop.
3. Before the production deploy, clear `npm audit`'s 4 high-severity findings in `web/` (seen 2026-09-30), or record why each one doesn't reach the deployed app.
4. Tick S3a in `docs/studio/04` and `ROADMAP.md`, add one `web/` line to `CLAUDE.md`, and fix the S3a plan's file map (it predates checkpoint G, the bypass, the fix card and the deep links).

## Done when
- `scripts/check.sh --web --e2e` is green.
- The production login works on the phone.

## Owner steps
- Before: the Vercel steps (runbook §5b). Then `scripts/worktree.sh s3a/deploy` and paste `Run card docs/cards/004-s3a-deploy.md`.

## Hand-off
The report goes in `docs/reports/004-s3a-<date>.md`. Don't commit.
