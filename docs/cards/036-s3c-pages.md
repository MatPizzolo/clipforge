# Card 036: S3c (S3c-1b) — the Accounts Map and the workspaces

Status: proposed
Stream: S3c (S3c-1b) · Branch: `s3c/pages` · Worktree: `../clipForge-s3c` (created with `scripts/worktree.sh s3c/pages`)
Decision-log range: #250–#299 (append only; shared in sequence by cards 035–038: re-read the log and take the next free number after card 035's rows)
Model: mid-tier (implementing a written plan on S3's dashboard patterns)
Depends on: card 035 (S3c-1a) **deployed** with its owner steps done (`setup verify` at 0) AND card 026 (S3-5: Compare and the minimal `/accounts/<id>` read view) **deployed** (log #263). Per log #144, no other code card is on `main` undeployed when this one merges. Online use needs card 004
Cost cap: $0 of Modal/API spend (web unit and Playwright tests against the mocked admin API; no Modal runs)

## Context
Card 035 deployed S3c-1a: versioned categories, blueprints and accounts, the preview, import and verify, notes, and the `/admin/` setup routes on the `admin` endpoint (`SETUP_SOURCE=off`). Card 026 deployed S3's Accounts → Compare and the account read view (Overview, Autopilot, Activity, Sources tabs). **This card builds S3c-1b, plan Tasks 8–10:** the typed admin client for the setup routes, the Accounts Map next to Compare, the category and blueprint workspaces, and the account workspace's Style and Setup & History tabs with notes. It edits S3-5's files, which is why it waits for card 026 (#258, #263). The backend doesn't change.

## Read first
1. `CLAUDE.md`, `STATUS.md`
2. The S3c plan: Global Constraints (routes, tests), Part S3c-1b (Tasks 8–10, the owner steps and the rollback)
3. The S3c spec §2 (pages: §2.2 Map and Compare, §2.3–§2.5 the workspaces, §2.9 links), §3.4 (the preview the edit dialog shows)
4. The S3 dashboard spec §7 (patterns, §7.7 dataviz, §7.10 the link contract) and §11.2; `docs/studio/08-dashboard-and-operations.md` §2 and §2c
5. Log rows #252, #257, #258, #263, #144, #148
6. Cards 035's and 026's reports
7. The code it builds on: `web/lib/upstream.ts`, `web/app/api/cf/**`, `web/lib/links.ts`, `web/lib/mocks.ts`, `web/app/(app)/accounts/page.tsx`, `web/app/(app)/accounts/[id]/page.tsx`, `web/components/accounts/{Compare,Overview}.tsx`, the link-contract test

## Scope
- May edit, as `scripts/scopes.toml` allows for `s3c/`: `web/**` (Tasks 8–10's files, including S3-5's `accounts/page.tsx`, `accounts/[id]/page.tsx`, `components/accounts/Compare.tsx` and `Overview.tsx`, `web/lib/links.ts`, `web/lib/mocks.ts`, the link-contract test), `docs/ARCHITECTURE.md`, `docs/superpowers/plans/*s3c*`, `docs/studio/04-roadmap.md` and `ROADMAP.md` (the S3c-1 tick only after the owner confirms the deploy), its own report, and log rows in #264–#299.
- Must not edit: `src/**`, `tests/**` and `alembic/` (no backend change: if a route is missing or wrong, stop and ask), the S3c spec, `STATUS.md`, other cards, `web/lib/upstream.ts` except through S3's helpers.
- **No new npm dependencies.** **The session never deploys or touches Vercel.**

## Actions
1. **Task 8, the admin client, mocks and the Map:** `web/lib/admin/setup.ts` on S3's `upstream.ts` (with zod schemas), the handlers under `web/app/api/cf/setup/**`, `MapView.tsx`, the `view` switch on `/accounts` (`map` default, `compare` S3's), Compare's two new columns (versions, ⚗ experiment), mocks.
2. **Task 9, the category and blueprint workspaces:** `/categories/<code>` and `/blueprints/<name>`, the shared `SetupTable`, `EditDialog` (preview → note → save), `PreviewBlock`, `History` (pick two → diff, restore), `DiffView`, `ApplyToAccounts`, `NotesPanel`.
3. **Task 10, the account workspace and the link contract:** S3's read view becomes the workspace shell, keeping its tabs; `?tab=style|setup`, `?tab=setup&from=&to=`, `?tab=history` redirecting; the notes panel and `+ Note`; the spec §2.9 paths `exists: true` in the link contract; `docs/ARCHITECTURE.md`.
4. **Checkpoint S3c-1b** (plan Task 10 step 5): `scripts/check.sh --e2e`; `pr-reviewer` and `docs-auditor`; fix what they find; the report with the owner steps below; stop.

Stop for the owner at the checkpoint below.

## Checkpoints
- A (S3c-1b): after actions 1–4. Suggested commit: `036: s3c-1b: Accounts map and workspaces`

## Done when
- `scripts/check.sh` and `scripts/check.sh --e2e` are green (paste the summary lines into the report).
- `pr-reviewer` and `docs-auditor` have no blocking findings, and the report lists what each said.
- `workspaces.spec.ts` passes on the phone and desktop projects: Map and Compare; edit → preview → save → diff → restore; origins and Reset; not found.

## Owner steps
- Before: cards 035 and 026 deployed; nothing else undeployed on `main`. `scripts/worktree.sh s3c/pages`, open a session in `../clipForge-s3c`, paste `Run card docs/cards/036-s3c-pages.md`.
- At A: commit with the suggested message, `git push -u origin s3c/pages`, `gh pr create --fill`, squash-merge when CI is green.
- Deploy:
  0. **The #144 check:** no other code card is on `main` undeployed (`docs/ops/deploys.md` against `git log`). The backend is unchanged (no Modal deploy).
  1. The Vercel deploy follows `main` (runbook §5b; only if card 004 is done, else `npm --prefix web run dev` locally).
  2. Open `/accounts` on the phone and the laptop; edit the clips playbook.
  3. Change one hashtag on realtalk, then check that `/status` in Telegram shows it at the next slot (a live field reaches production with `SETUP_SOURCE=off`, spec §5.6).
  4. `uv run clipforge setup verify`: `0 differences`. Tell the coordinator, for the tick.
- **Rollback:** revert the web deploy on Vercel (or the merge on `main`); the backend is unchanged.

## Hand-off
Write `docs/reports/036-s3c-<YYYY-MM-DD>.md` from `docs/templates/handoff-report.md` at the checkpoint, with each task's status, the reviewers' findings and the owner steps. Don't commit: the owner does. The next card is 037 (S3c-2), after this deploy; remove this worktree after the merge (`scripts/worktree.sh --remove s3c/pages`).
