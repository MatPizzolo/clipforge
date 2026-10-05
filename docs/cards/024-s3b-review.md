# Card 024: S3 (S3-3) — Review (Queue and Review lane), move to the front, Calendar

Status: proposed · Updated 2026-10-05 (ADR-54): this card now runs **before** S2b and **gates it**: card 015 starts only after this card is deployed, because review decisions happen only on this page; `REVIEW_BATCH` no longer exists
Stream: S3 (S3-3) · Branch: `s3b/review` · Worktree: `../clipForge-s3b` (created with `scripts/worktree.sh s3b/review`)
Decision-log range: #630–#679 (append only; shared in sequence by cards 022–027: re-read the log and take the next free number after card 023's rows)
Model: mid-tier (implementing a written plan); most capable for the pin's interplay with `pick_next`, the Dual repo and `posting verify`
Depends on: card 023 (S3-2) **deployed** with its owner steps done. Per log #144, no other code card is on `main` undeployed when this one merges. The Review lane shows rows only once card 015 (S2b) is **deployed** with its owner steps done; under ADR-54's order (024 before 015) the lane ships with its "The review lane arrives with publishing (S2b)" empty state and no batch approve route, and card 015 adds `POST /admin/review/batch` with its review service. Re-render stays disabled until the hooks build. Online use needs card 004
Cost cap: $2 of Modal/API spend (fast tests and the local Postgres). The owner's deploy is not session spend

## Context
Cards 022 and 023 deployed the `admin` endpoint, S3's migration, Settings, the needs API, Home, `/act` and the link contract. Read card 023's report first (the providers registered and any S2 follow-ups). **This card builds S3-3, plan Tasks 12–15:** Review with two tabs, the pin ("move to the front"), the queue, pause and batch approve routes, and Calendar (spec §11.4, D8).

Rules that bind this card:
- **Queue** is D8's queue manager for assisted accounts (Publish off, or no connected profile): next up, Move to the front, Skip, Reject with a reason, posted corrections, all through `posting/actions.py` with `web:<login>`. It never sends.
- **The pin** (#621): `posting/actions.pin` is the only writer of `content_items.queue_pin` and writes `pinned`/`unpinned` `post_events`. A pin is active only while it is later than the item's last send, so the send path never clears it. **Postgres only:** the Dict repo raises `PinUnsupported` and the route answers 409 "needs the database"; Dual calls the primary only; `posting verify` excludes `queue_pin` and the pin events on purpose. On Upload-Post accounts a pin made after the 08:50 plan takes effect at the next plan, and the Queue tab says so.
- **Review lane** calls S2's `/admin/review` routes (reused, never re-implemented) and, **only if S2b's review service is on `main`**, S3's `POST /admin/review/batch`. **Re-render** is a disabled button titled "arrives with the hooks build" (#619).
- **Calendar has no drag-to-reschedule** (log #146, Open table): the page says "Rescheduling comes later; pause an account or edit its slots with `clipforge account edit`". The writers of a later card would be `dispatch/plan.py` (one slot) and the accounts service (an account's schedule).
- **A pin or approve while the brake or the outage flag is on** is recorded and sends nothing (Review Focus 4, pinned by `test_pin_while_braked_records_and_sends_nothing`).
- **`REVIEW_BATCH` is gone** (ADR-54, log #150): there is no 09:00 Telegram batch to turn off. This page is the only place review decisions are made; Telegram only sends "N items need review → Open" linking here, so card 015 (S2b) waits for this deploy.

## Read first
1. `CLAUDE.md`, `STATUS.md`
2. Card 023's report, and card 015's if it has merged
3. The S3 plan: Global Constraints, Review Focus (item 4), Part S3-3 (Tasks 12–15, owner steps, rollback)
4. The S3 dashboard spec §11.4 (Review before and after S2b), §11.1 (the routes S2 owns), §11.9 (the bridges; `REVIEW_BATCH` removed by ADR-54), §11.11; §7 (the Review and Calendar pages); mockup `docs/design/dashboard/review.html`
5. `docs/DECISIONS.md`: ADR-14, ADR-23, ADR-41, ADR-44, ADR-54
6. Log rows #613, #617, #619, #621, #623, #144–#146
7. The code it changes: `posting/repo.py`, `posting/queue.py`, `posting/actions.py`, `posting/migrate.py`, `db/posting.py`, `api/admin/`, `web/components/nav.ts`, `web/lib/links.ts`, `web/lib/mocks.ts`

## Scope
- May edit, as `scripts/scopes.toml` allows for `s3b/`: `src/**`, `tests/**`, `.env.example`, `pyproject.toml`, `uv.lock`, `web/**`, `scripts/export_openapi.py`, `docs/ARCHITECTURE.md`, `docs/ops/secrets.md`, `docs/superpowers/plans/*s3-dashboard*` (task ticks), `docs/studio/04-roadmap.md` and `ROADMAP.md` (ticks only after the owner confirms the deploy), `docs/studio/11-owner-runbook.md` (**§5b only**), `CLAUDE.md` (Commands and Layout), its own report, and log rows in #630–#679.
- Must not edit: the spec, `STATUS.md`, other cards, `prompts/`, stage modules, `alembic/` (S3-3 has no migration; `queue_pin` landed in card 022), S2 modules that aren't on `main`.
- **No new dependencies.** **Only `app.py` imports `modal`.** **The session never deploys, migrates Neon, changes a secret or touches Vercel.**

## Actions
Each task follows the plan: failing tests first, then the implementation, then its checks, then "check and record".
1. **Task 12, move to the front:** `PostRecord.pinned_at`, `PostingRepo.set_pin` (Dict raises `PinUnsupported`; Dual calls the primary only), `db/posting.py` reads `queue_pin`, `actions.pin`, `active_pin`, `pick_next` prefers active pins (oldest first; the video and channel rule still applies), `posting/migrate.py`'s verify excludes pins. Pinning tests: `test_old_pin_after_rollback_does_not_jump`, `test_pin_while_braked_records_and_sends_nothing`, verify at 0 with pins present.
2. **Task 13, queue routes, batch approve and pause:** `QueueRow`, `QueueView` in `models.py`; `api/admin/posting.py` (`GET /admin/posting/queue`, pin and unpin, skip, reject, reason, posted, each redrawing Telegram through `actions.redraw_all`); `POST /admin/accounts/{id}/pause` through `posting/actions.pause`; `api/admin/review.py` with `POST /admin/review/batch` only if S2b's `ReviewService` is on `main` (otherwise the report names it as card 015's follow-up).
3. **Task 14, the Review page:** `/review?tab=queue|lane&account=`, the Queue and Review lane tabs, the batch bar (laptop only), the disabled Re-render, phone lists opening `/act/...`; the route handlers; `links.ts` flips `/review?account=<id>`; `review.spec.ts` (including "lane without S2b says when it arrives" and "re-render is disabled until the hooks build").
4. **Task 15, Calendar:** `/calendar?week=YYYY-Www&account=` over `GET /admin/slots` with a Pause/Go toggle per account, and the "Rescheduling comes later" note; `calendar.spec.ts`; nav.
5. **Checkpoint S3-3** (plan Task 15 step 3): the full `scripts/check.sh` and `scripts/check.sh --e2e`; `docs/ARCHITECTURE.md` (the pin, the queue routes); `pr-reviewer`, and `migration-reviewer` for the posting repo and `posting verify` changes (the plan asks for it here: Dual, verify and rollback behaviour, though there is no migration); fix what they find; the report; stop.

Stop for the owner at the checkpoint below.

## Checkpoints
- A (S3-3): after actions 1–5. Suggested commit: `024: s3-3: review (queue and lane), move to the front, calendar`

## Done when
- `scripts/check.sh` and `scripts/check.sh --e2e` are green (paste the summary lines into the report).
- `pr-reviewer` and `migration-reviewer` have no blocking findings, and the report lists what each said.
- With pins present, `posting verify` (the test) reports 0 differences; in dict mode the pin answers 409 and writes nothing.
- No route duplicates S2's review, policy, autopilot or link routes; the Review lane and Re-render states above are pinned by Playwright.

## Owner steps
- Before: card 023 deployed with its owner steps. After 023's merge, `scripts/worktree.sh --remove s3b/needs`, then `scripts/worktree.sh s3b/review`, open a session in `../clipForge-s3b`, paste `Run card docs/cards/024-s3b-review.md`.
- At A: commit with the suggested message, `git push -u origin s3b/review`, `gh pr create --fill`, squash-merge when CI is green.
- Deploy (from `main`, after the merge, outside the blackout):
  0. **Pre-deploy check (#623):** no other code card is on `main` undeployed (`docs/ops/deploys.md` against `git log`), and `uv run modal run src/clipforge/app.py::db_doctor` shows S3's head.
  1. `scripts/deploy.sh --dry-run`, then `scripts/deploy.sh --reason "S3-3: review and calendar"`. There is no migration.
  2. `uv run clipforge posting verify`: still 0 differences (pins are excluded).
  3. Online (card 004 is done before this card under ADR-54's order; redeploy the dashboard from `main`): Review → Queue, move one clip to the front, and check that it shows first (posting stays paused until S2b, so no slot sends it). Calendar shows the week.
  4. Tell the coordinator: card 015 (S2b) can start (ADR-54).
  5. Commit the `docs/ops/deploys.md` line and tell the coordinator the deploy is done.
- **Rollback:** a revert deploy (`git revert` of the merge, `scripts/deploy.sh --dry-run`, `scripts/deploy.sh --reason "revert S3-3"`). `queue_pin` values stay, and the old `pick_next` ignores them. In Vercel, promote the previous dashboard deployment.

## Hand-off
Write `docs/reports/024-s3b-<YYYY-MM-DD>.md` from `docs/templates/handoff-report.md` at the checkpoint, with each task's status, whether the batch approve route shipped (S2b on `main` or not), the reviewers' findings and the owner steps. Don't commit: the owner does. The next card is 015 (S2b), after this deploy (ADR-54); 025 (S3-4) follows one deploy at a time.
