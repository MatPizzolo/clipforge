# Card 027: S3 (S3-5b) — the Telegram retirements and the CLI cut-over to `admin`

Status: proposed · Updated 2026-10-05 (ADR-54): the `REVIEW_BATCH` step is removed (the setting no longer exists)
Stream: S3 (S3-5b) · Branch: `s3b/cutover` · Worktree: `../clipForge-s3b` (created with `scripts/worktree.sh s3b/cutover`)
Decision-log range: #630–#679 (append only; shared in sequence by cards 022–027: re-read the log and take the next free number after card 026's rows)
Model: most capable (the cut-over removes every bearer route from the public endpoint)
Depends on: card 026 (S3-5) **deployed** with its owner steps done, AND its 7-day windows (#617, #623): Task 22 only after S3-4's Produce and the job page's Resume have been used online (card 004 done) for 7 days; Task 23 only after `admin` has been live for 7 days (from card 022's deploy). If only one window is over, the card does that task and the report names the other. (`REVIEW_BATCH` was removed by ADR-54, 2026-10-05.) Per log #144, no other code card is on `main` undeployed when this one merges
Cost cap: $2 of Modal/API spend (fast tests; no Modal runs needed). The owner's deploy is not session spend

## Context
Cards 022–026 built and deployed the dashboard v1. **This card is S3-5b, plan Tasks 22–23**, the bridges' end (spec §11.9, §11.2):
- **Task 22:** `/clip` answers "Clip jobs start in Produce now: <DASHBOARD_URL>/produce" and creates nothing; `/status <job_id>` and `/resume <id>` answer with the job page's link. `/status` with no argument and `clipforge status <id>` / `clipforge resume <id>` on the laptop stay. Without `DASHBOARD_URL` the commands keep working as today.
- **Task 23, the CLI cut-over (#618):** the CLI talks to `admin` (`CLIPFORGE_ADMIN_URL`, `MODAL_PROXY_KEY`, `MODAL_PROXY_SECRET`, `ADMIN_API_TOKEN` in the laptop's `.env`) for every route of `cli_router`; it refuses to start an admin call without the settings, naming the missing ones. Uploads keep `modal volume put`, `--fetch` keeps `ModalCliDownloader`, and `set-webhook` talks to Telegram with the public `web` URL.

**Owner ruling, 2026-10-02 (log #146), which settles the plan's proposal (#623):** at the cut-over **every** bearer route leaves `web`: S2's `/admin/*` **and S1's `/accounts` and `/sources` routes (writes included)**, with `/jobs`, `/jobs/backfill` and `/posting*`. `cli_router` is mounted on `admin` only; **no** `s1_router` split. `web` ends **public-only**: `/telegram/webhook`, `/jobs/{id}/download`, `/webhooks/upload-post`, `/media/{item}.mp4` and `/go/{slug}` (the last three as far as S2b and S2c have landed them). `API_TOKEN` retires from `clipforge-secrets` a week after the deploy.

Since the plan was written: the plan's Task 23 test `test_web_serves_only_public_routes_after_cut_over` is the binding check; its `PUBLIC_PATHS` lists only the public routes on `main` at landing.

## Read first
1. `CLAUDE.md`, `STATUS.md`
2. Card 026's report (and cards 022 and 025's for the endpoint and Produce)
3. The S3 plan: Global Constraints (Security), Part S3-5b (Tasks 22–23, owner steps, rollback), Deployable steps
4. The S3 dashboard spec §11.2 (the endpoint, the cut-over), §11.9 (the bridges), §11.3
5. `docs/DECISIONS.md`: ADR-2, ADR-38, ADR-44
6. Log rows #610, #617, #618, #623, #144–#146
7. The code it changes: `src/clipforge/bot/commands.py`, `cli.py`, `config.py`, `api/main.py`; `docs/ops/secrets.md`; runbook §2 and §5b

## Scope
- May edit, as `scripts/scopes.toml` allows for `s3b/`: `src/**`, `tests/**`, `.env.example`, `pyproject.toml`, `uv.lock`, `web/**` (only if the OpenAPI export or the generated client changes), `scripts/export_openapi.py`, `docs/ARCHITECTURE.md`, `docs/ops/secrets.md` (the laptop's CLI variables; `API_TOKEN`'s retirement), `docs/superpowers/plans/*s3-dashboard*` (task ticks), `docs/studio/04-roadmap.md` and `ROADMAP.md` (the Phase 1 Telegram item, and the S3 ticks only after the owner confirms the exit), `docs/studio/11-owner-runbook.md` (**§2's Telegram commands text, plan Task 22, and §5b**), `CLAUDE.md` (Commands: the CLI talks to `admin`), its own report, and log rows in #630–#679.
- Must not edit: the spec, `STATUS.md`, other cards, `prompts/`, stage modules, `alembic/`.
- **No new dependencies.** **Only `app.py` imports `modal`.** **The session never deploys, changes a secret (`API_TOKEN`) or touches Vercel**: the owner does.

## Actions
Each task follows the plan: failing tests first, then the implementation, then its checks, then "check and record".
1. **Check the windows** with the owner's dates (cards 024 and 025's owner steps; card 022's deploy in `docs/ops/deploys.md`). Write in the report which tasks this run does.
2. **Task 22, the Telegram retirements** (if its window is over): `bot/commands.py` (`/clip` points to Produce, `/status <id>` and `/resume <id>` to `<DASHBOARD_URL>/jobs/<id>`, `/status` alone unchanged, all unchanged without `DASHBOARD_URL`); the four tests in `tests/bot/test_commands.py`; runbook §2 (jobs start in Produce or with `clipforge clip` for local files; [Resume] stays; `clipforge status <id>` and `clipforge resume <id>` on the laptop; `/status` still summarizes posting); `ROADMAP.md`'s Phase 1 Telegram item (`/clip` retired per ADR-44).
3. **Task 23, the CLI cut-over** (if its window is over), per the owner ruling above: `config.py` (`clipforge_admin_url`, `modal_proxy_key`, `modal_proxy_secret`, read by the CLI only), `cli.py` (`ApiClient(base_url, token, proxy)`, the proxy headers and `ADMIN_API_TOKEN` on every `cli_router` route; exit 2 naming missing settings), `api/main.py` (`cli_router` on `admin` only; `web` mounts only the public routes); `tests/test_cli.py` and `tests/api/admin/test_surfaces.py` (`test_web_serves_only_public_routes_after_cut_over`: no `/admin/*`, no `/accounts`, `/sources`, `/jobs` other than the download, `/posting`); `.env.example`, `docs/ops/secrets.md` (the laptop's second proxy token; `API_TOKEN` removed a week after the deploy), `CLAUDE.md` Commands.
4. **Checkpoint S3-5b** (plan Task 23 step 3): the full `scripts/check.sh` and `scripts/check.sh --e2e`; `docs/ARCHITECTURE.md` (the overview diagram and Security: `web` public-only, the CLI on `admin`); `pr-reviewer`, `security-reviewer` (nothing but public routes left on `web`; the CLI's secrets never printed) and `docs-auditor`; fix what they find; the report; stop. Tick S3 in `ROADMAP.md` and `docs/studio/04-roadmap.md` only after the owner confirms the exit (owner step 6).

Stop for the owner at the checkpoint below.

## Checkpoints
- A (S3-5b): after actions 1–4. Suggested commit: `027: s3-5b: telegram retirements, CLI on admin, web public-only`

## Done when
- `scripts/check.sh` and `scripts/check.sh --e2e` are green (paste the summary lines into the report).
- `pr-reviewer`, `security-reviewer` and `docs-auditor` have no blocking findings, and the report lists what each said.
- `test_web_serves_only_public_routes_after_cut_over` passes: `web` mounts no bearer route, S1's `/accounts` and `/sources` included; every CLI route works on `admin` in the tests.
- The CLI names the missing settings and exits 2 without them; no test or log line prints a token.
- The report says which of Task 22 and Task 23 ran, and the date the other can.

## Owner steps
- Before: card 026 deployed with its owner steps, and the windows above. After 026's merge, `scripts/worktree.sh --remove s3b/results`, then `scripts/worktree.sh s3b/cutover`, open a session in `../clipForge-s3b`, paste `Run card docs/cards/027-s3b-cutover.md`.
- ~~`REVIEW_BATCH` off~~: removed by ADR-54 (2026-10-05). There is no 09:00 review batch and no `REVIEW_BATCH` setting; nothing to turn off.
- At A: commit with the suggested message, `git push -u origin s3b/cutover`, `gh pr create --fill`, squash-merge when CI is green.
- Deploy (from `main`, after the merge, outside the blackout):
  0. **Pre-deploy check (#623):** no other code card is on `main` undeployed (`docs/ops/deploys.md` against `git log`), and `uv run modal run src/clipforge/app.py::db_doctor` shows S3's head (or a later one, if another card's migration deployed since).
  1. Add `CLIPFORGE_ADMIN_URL`, `MODAL_PROXY_KEY`, `MODAL_PROXY_SECRET` and `ADMIN_API_TOKEN` to the laptop's `.env`, using a **second** Modal proxy token for the laptop, so the laptop and Vercel can be revoked separately. Keep the old `CLIPFORGE_API_URL` and `API_TOKEN` until the cut-over has run for a week.
  2. `scripts/deploy.sh --dry-run`, then `scripts/deploy.sh --reason "S3-5b: retirements, CLI on admin, web public-only"`.
  3. `uv run clipforge autopilot show realtalk-clips-en` and `uv run clipforge source list` (both through `admin`). Then `curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer <API_TOKEN>" <web url>/admin/review` → `404`, and the same for `<web url>/sources` and `<web url>/accounts` → `404`.
  4. In Telegram: `/clip <link>` answers with the Produce link; `/status` still summarizes posting.
  5. **A week later:** remove `API_TOKEN` from `clipforge-secrets` (the `docs/ops/secrets.md` procedure) and from the laptop's `.env`, then `scripts/deploy.sh --reason "API_TOKEN retired"`.
  6. **The exit (04's S3):** for a week, the daily check-in from the phone in under 20 minutes, and every Telegram alert opens its row in `/act`. Tell the coordinator; then S3 is ticked.
  7. Commit the `docs/ops/deploys.md` lines.
- **Rollback:** a revert deploy (`git revert` of the merge, `scripts/deploy.sh --dry-run`, `scripts/deploy.sh --reason "revert S3-5b"`). Then `/clip` creates jobs again, `web` mounts the bearer routes again, and the CLI's old `CLIPFORGE_API_URL` and `API_TOKEN` work again (which is why they stay in `.env` for a week).

## Hand-off
Write `docs/reports/027-s3b-<YYYY-MM-DD>.md` from `docs/templates/handoff-report.md` at the checkpoint, with which tasks ran, the reviewers' findings and the owner steps. Don't commit: the owner does. After the merge, `scripts/worktree.sh --remove s3b/cutover`. S3c's build (card 018's plan) builds on the same `admin` endpoint.
