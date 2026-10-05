# Card 025: S3 (S3-4) — Produce with batches, the Jobs tab, Resume, Sources

Status: proposed
Stream: S3 (S3-4) · Branch: `s3b/produce` · Worktree: `../clipForge-s3b` (created with `scripts/worktree.sh s3b/produce`)
Decision-log range: #630–#679 (append only; shared in sequence by cards 022–027: re-read the log and take the next free number after card 024's rows)
Model: mid-tier (implementing a written plan); most capable for batch approval (the conditional update) and the input path and URL checks
Depends on: card 024 (S3-3) **deployed** with its owner steps done. Per log #144, no other code card is on `main` undeployed when this one merges. S2a's `autopilot` row (deployed before card 022) supplies the batch line and the monthly cap. Online use needs card 004
Cost cap: $2 of Modal/API spend (fast tests and the local Postgres; no real jobs are needed: `service.create_job` is tested with fakes). The owner's deploy and test job (~$0.10) are not session spend

## Context
Cards 022–024 deployed the `admin` endpoint, Settings, the needs API, Home, `/act`, Review and Calendar. Read card 024's report first. **This card builds S3-4, plan Tasks 16–18:** Produce creates clip jobs from the phone with the cost first (spec §11.5, #614), the Jobs tab, Resume on the job page, and the Sources pages over S1's routes.

Rules that bind this card:
- **`POST /admin/batches/preview` writes nothing.** `POST /admin/batches` (actor required) creates one job per input through `service.create_job` under the account's line, with the same `JobInput` fields `clipforge clip` sends; over the line it writes a `batches` row (`status='pending'`) and returns its `spend_line` row, which Home and `/act` approve or decline. `produce/batches.py` is the only writer of `batches`.
- **Inputs:** episodes already on the Volume under `JOBS_ROOT/uploads/` (passing `jobs`' path checks) or direct links; 1–50 per batch. **`source_id` is required and validated for every input**: unknown or another account's → 400; held by `sources.py`'s rules → 409 naming the rule (the preview lists held sources). Fetching stays local until S11 (ADR-34).
- **Approving a pending batch is a conditional update** (`pending` → `approved`); only the caller whose update matched creates the jobs (`test_double_approve_creates_jobs_once`, Review Focus 1).
- **One source for the line and the cap:** S2's `autopilot` row (`batch_line_usd`, `monthly_cap_usd`); `settings` holds only the fleet cap. **Caps are shown, never enforced** (ADR-48, #435; `test_caps_shown_not_enforced`).
- **Sources pages** call S1's `/sources` routes on `admin`, whose writes require `X-Clipforge-Actor` (#623).
- The 7-day clock for retiring `/clip`, `/status <id>` and typed `/resume` starts when Produce is used online (card 027, #617).

## Read first
1. `CLAUDE.md`, `STATUS.md`
2. Card 024's report
3. The S3 plan: Global Constraints, Review Focus (item 1), Part S3-4 (Tasks 16–18, owner steps, rollback)
4. The S3 dashboard spec §11.5 (Produce), §11.1 (`spend_line`, `job_failed`), §11.9; §7 (Produce, Sources); §2.6 and §2.7; mockup `docs/design/dashboard/produce.html`
5. `docs/DECISIONS.md`: ADR-8, ADR-10, ADR-14, ADR-22, ADR-48
6. Log rows #614, #617, #623, #144–#146
7. The code it changes and calls: `service.py` (`create_job`, `resume_job`), `inbox.py` (how `clipforge clip` builds `JobInput`), `sources.py`, `jobs.py` (path checks), `ffmpeg.py` (`probe_info`), `config.Prices`, `accounts/autopilot.py`, `accounts/runway.py`, `needs/providers.py`, `web/app/(app)/jobs/[id]/page.tsx`

## Scope
- May edit, as `scripts/scopes.toml` allows for `s3b/`: `src/**`, `tests/**`, `.env.example`, `pyproject.toml`, `uv.lock`, `web/**`, `scripts/export_openapi.py`, `docs/ARCHITECTURE.md`, `docs/ops/secrets.md`, `docs/superpowers/plans/*s3-dashboard*` (task ticks), `docs/studio/04-roadmap.md` and `ROADMAP.md` (ticks only after the owner confirms the deploy), `docs/studio/11-owner-runbook.md` (**§5b only**), `CLAUDE.md` (Commands and Layout), its own report, and log rows in #630–#679.
- Must not edit: the spec, `STATUS.md`, other cards, `prompts/`, stage modules, `alembic/` (S3-4 has no migration; `batches` landed in card 022).
- **No new dependencies.** **Only `app.py` imports `modal`.** **The session never deploys, migrates Neon, changes a secret or touches Vercel.**

## Actions
Each task follows the plan: failing tests first, then the implementation, then its checks, then "check and record".
1. **Task 16, the batch planner:** `BatchInput`, `BatchRequest`, `StageEstimate`, `BatchPreview`, `HeldInput`, `BatchCreated` in `models.py`; `produce/estimate.py` (the account's median USD per source hour over its last 20 done jobs, `Prices` before any history, links counted as 1 h "estimated", `review_minutes` at the account's rung, line and cap from `AutopilotService.get`, month spend from `jobs.costs`); `produce/batches.py` (`preview`, `create`, `approve`, `decline`, `UnknownSource` → 400, `SourceHeld` → 409); `SpendLineProvider` in `needs/providers.py`.
2. **Task 17, produce, jobs and episodes routes:** `api/admin/produce.py`: `POST /admin/batches/preview`, `POST /admin/batches`, `GET /admin/jobs?account=&status=&limit=50`, `GET /admin/accounts/{id}/sources`, `GET /admin/accounts/{id}/episodes`; `web/openapi.json` and the client regenerated.
3. **Task 18, the pages:** `/produce?account=&tab=plan|jobs` (the planner with the live preview, "Queue N jobs" or "Ask me on Home"), the Jobs tab, Resume on a failed job's page (`POST /jobs/{id}/resume`), `/sources` and `/sources/<id>` (list, permission record and history, add and edit); nav (Produce, Sources; Jobs leaves the top level); `links.ts` flips `/sources/<id>` and `/jobs/<id>`; `produce.spec.ts` and `sources.spec.ts` at phone and desktop sizes.
4. **Checkpoint S3-4** (plan Task 18 step 3): the full `scripts/check.sh` and `scripts/check.sh --e2e`; `docs/ARCHITECTURE.md` (Produce, `batches`) and `CLAUDE.md` (Layout: `produce/`); `pr-reviewer` and `security-reviewer` (input paths and URLs for job creation: `JOBS_ROOT/uploads/` containment, SSRF rules for links, source ownership, the actor on S1's writes); fix what they find; the report; stop.

Stop for the owner at the checkpoint below.

## Checkpoints
- A (S3-4): after actions 1–4. Suggested commit: `025: s3-4: produce with batches, jobs tab and resume, sources`

## Done when
- `scripts/check.sh` and `scripts/check.sh --e2e` are green (paste the summary lines into the report).
- `pr-reviewer` and `security-reviewer` have no blocking findings, and the report lists what each said.
- `test_double_approve_creates_jobs_once` and `test_caps_shown_not_enforced` pass; a preview writes nothing; an input outside `JOBS_ROOT/uploads/`, an unknown or foreign source, and a held source are refused with the codes above.

## Owner steps
- Before: card 024 deployed with its owner steps. After 024's merge, `scripts/worktree.sh --remove s3b/review`, then `scripts/worktree.sh s3b/produce`, open a session in `../clipForge-s3b`, paste `Run card docs/cards/025-s3b-produce.md`.
- At A: commit with the suggested message, `git push -u origin s3b/produce`, `gh pr create --fill`, squash-merge when CI is green.
- Deploy (from `main`, after the merge, outside the blackout):
  0. **Pre-deploy check (#623):** no other code card is on `main` undeployed (`docs/ops/deploys.md` against `git log`), and `uv run modal run src/clipforge/app.py::db_doctor` shows S3's head.
  1. `scripts/deploy.sh --dry-run`, then `scripts/deploy.sh --reason "S3-4: produce"`. There is no migration.
  2. Online (after card 004; redeploy the dashboard from `main`): Produce → one imported episode → Queue 1 job; it appears in the Jobs tab and finishes as with `clipforge clip`.
  3. Try a batch over $2: it shows up on Home as a spend row; approve it there.
  4. **Note the date:** the 7-day clock for `/clip`, `/status <id>` and typed `/resume` starts with Produce used online (card 027).
  5. Commit the `docs/ops/deploys.md` line and tell the coordinator the deploy is done.
- **Rollback:** a revert deploy (`git revert` of the merge, `scripts/deploy.sh --dry-run`, `scripts/deploy.sh --reason "revert S3-4"`). `batches` rows stay; pending ones are inert without the code. In Vercel, promote the previous dashboard deployment.

## Hand-off
Write `docs/reports/025-s3b-<YYYY-MM-DD>.md` from `docs/templates/handoff-report.md` at the checkpoint, with each task's status, the reviewers' findings and the owner steps. Don't commit: the owner does. The next card is 026 (S3-5), after this deploy.
