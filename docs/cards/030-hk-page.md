# Card 030: HK (HK-3) — the interim `/hooks?account=` page

Status: proposed
Stream: HK (HK-3) · Branch: `hk/page` · Worktree: `../clipForge-hk` (created with `scripts/worktree.sh hk/page`)
Decision-log range: #550–#579 (append only; shared in sequence by cards 028–030: re-read the log and take the next free number after card 029's rows)
Model: mid-tier (implementing a written plan on S3's admin client pattern)
Depends on: card 029 (HK-2) **deployed** AND card 022 (S3-1: the `admin` endpoint, `upstream.ts` and its route-handler pattern) **deployed**, each with its owner steps done. Per log #144, no other code card is on `main` undeployed when this one merges. **Skipped** if S3c's account workspace with its Hooks tab is deployed first (plan Part HK-3): then `/hooks?account=` redirects there and the coordinator marks this card superseded. Online use needs card 004
Cost cap: $0 of Modal/API spend (web unit and Playwright tests against the mocked API; no Modal runs)

## Context
Cards 028 and 029 deployed the hook library, the variants behind `HOOK_VARIANTS`, ranking, ratings and re-render, with routes under `/admin`. Card 022 deployed the `admin` endpoint and the dashboard's admin client (`web/lib/upstream.ts`, the `web/app/api/cf/` handlers). **This card builds HK-3, plan Task 12:** the interim page `/hooks?account=<id>` until S3c's account workspace has its Hooks tab (spec §7; 08 §2c "Hooks").

Since the plan was written:
- If card 029 mounted any hooks route on `web` as a fallback (card 022 not deployed then), card 022 or a later S3 card should have moved it to `admin`; check card 029's report and the deployed routes, and stop and ask the coordinator if the page would have to call a `web` route.
- Follow S3's handler pattern exactly: the page calls only `admin` through `upstream.ts`'s helpers, with the `X-Clipforge-Actor` header on writes.

## Read first
1. `CLAUDE.md`, `STATUS.md`
2. The hooks plan: Global Constraints (routes), Part HK-3 (Task 12, the owner steps and the rollback)
3. The hooks spec §5 (ranking, the suggestion), §7 (surfaces); `docs/studio/08-dashboard-and-operations.md` §2c "Hooks"
4. The S3 dashboard spec §7.10 (the link contract) and §11.2 (the `admin` endpoint)
5. Log rows #553, #556, #560–#562, #144, #146, #148
6. Cards 029's and 022's reports
7. The code it builds on: `web/lib/upstream.ts`, `web/app/api/cf/**`, `web/lib/api` (the generated client), `web/lib/mocks.ts`, the link-contract test, `web/README.md`
8. The `dataviz` skill (the approval-rate dots with their intervals)

## Scope
- May edit, as `scripts/scopes.toml` allows for `hk/`: `web/**` (the page `web/app/(app)/hooks/page.tsx`, `web/lib/hooks.ts`, the handlers under `web/app/api/cf/`, mocks, `web/tests/unit/hooks.test.ts`, `web/e2e/hooks.spec.ts`, the link-contract test), its own report, and log rows in #563–#579; `docs/studio/04-roadmap.md` and `ROADMAP.md` (the HK-3 tick only after the owner confirms the Vercel deploy).
- Must not edit: `src/**` and `tests/**` (no backend change in HK-3: if a route is missing, stop and ask), `alembic/`, `prompts/`, the hooks spec, `STATUS.md`, other cards, `web/lib/upstream.ts` except through the helpers S3 adds.
- **No new npm dependencies.** **The session never deploys or touches Vercel.**

## Actions
1. **Task 12, the page:** failing unit tests (`hookRows`, `suggestion`, the frozen view) and Playwright tests (phone and desktop, `MOCK_API`: the library table, the freeze notice hidden, "not found"); then the page: the table (pattern, version, status, scope, weight with ❄ when frozen, items, posted and reject rates, 👍 share, verdict), the approval-rate dot with its 90% interval and a direct label plus a "table view" toggle, the actions (Edit writing v+1, Approve, Retire, Share to blueprint, Weight pre-filled with `suggestion()` and a required reason), recent items with 👍/👎, the freeze notice, and the not-found, empty ("nothing rotates: approve a pattern") and API-unavailable states; server component for the first load, TanStack Query to refresh, no polling while hidden. Add `/hooks?account=<id>` to the link-contract test.
2. **Checkpoint HK-3** (plan Task 12 step 5): `scripts/check.sh --e2e`; `pr-reviewer` and `security-reviewer` (auth on the new handlers); fix what they find; the report with the owner steps below; stop.

Stop for the owner at the checkpoint below.

## Checkpoints
- A (HK-3): after actions 1–2. Suggested commit: `030: hk-3: interim hooks page`

## Done when
- `scripts/check.sh` and `scripts/check.sh --e2e` are green (paste the summary lines into the report).
- `pr-reviewer` and `security-reviewer` have no blocking findings, and the report lists what each said.
- The hooks unit and e2e tests pass on the phone and desktop projects, and the link-contract test includes `/hooks?account=<id>`.

## Owner steps
- Before: cards 029 and 022 deployed (above). `scripts/worktree.sh hk/page`, open a session in `../clipForge-hk`, paste `Run card docs/cards/030-hk-page.md`.
- At A: commit with the suggested message, `git push -u origin hk/page`, `gh pr create --fill`, squash-merge when CI is green.
- Deploy:
  0. **The #144 check:** no other code card is on `main` undeployed (`docs/ops/deploys.md` against `git log`), and card 022 is deployed.
  1. `uv run modal run src/clipforge/app.py::db_doctor` (the head is unchanged; HK-3 has no migration and no Modal deploy).
  2. The Vercel deploy as runbook §5b (only if card 004 is done; otherwise `npm --prefix web run dev` locally against `ADMIN_API_URL`). Open `/hooks?account=realtalk-clips-en` on the phone and the laptop.
  3. Tell the coordinator the deploy is done, for the roadmap tick.
- **Rollback:** revert the merge on `main`; Vercel redeploys the previous build. The backend is unchanged.

## Hand-off
Write `docs/reports/030-hk-<YYYY-MM-DD>.md` from `docs/templates/handoff-report.md` at the checkpoint, with the task's status, the reviewers' findings and the owner steps. Don't commit: the owner does. This closes the hooks build; remove the worktree after the merge (`scripts/worktree.sh --remove hk/page`).
