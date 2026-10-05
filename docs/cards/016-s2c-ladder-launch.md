# Card 016: S2c — the ladder, the digest, failure rows, tracking links; founder.tapes and hombre launch

Status: proposed · Updated 2026-10-05 (ADR-54): Telegram is notifications only; the digest ends with "N items need review → Open" and sends no cards; no assisted fallback
Stream: S2 (S2c) · Branch: `s2c/ladder-launch` · Worktree: `../clipForge-s2c` (created with `scripts/worktree.sh s2c/ladder-launch`)
Decision-log range: #530–#549 (append only, in this range)
Model: mid-tier (implementing a written plan)
Depends on: card 024 (the Review page) deployed (ADR-54; before card 015), and card 015 merged and deployed, with realtalk a day on Hands-on through Upload-Post and `posting verify` at 0. Owner steps before the launch: O3 (the handles, warmed up per runbook §6), one permitted source each for founder.tapes and hombre.en.construccion (with its permission record), and two more Upload-Post profiles (3 of Basic's 5)
Cost cap: $3 of Modal/API spend (smoke runs, and clipping one episode per new source with Haiku). Upload-Post stays on the owner's Basic subscription

## Context
Cards 014 (S2a) and 015 (S2b) are deployed: the dispatcher, the brake, autopilot on Hands-on, the gate (on, after the dry run), and realtalk.clipsdaily publishing through Upload-Post, reviewed on the dashboard's Review page (ADR-54: no review cards, no batch). **This card builds S2c, plan Tasks 21–26**, and supports the launch of founder.tapes and hombre.en.construccion. Read card 015's report first, especially R5's results and any deviation.

Decisions that bind this card:
- **Promotions are the owner's tap** (ADR-48): until S3 it is `clipforge autopilot promote <account>` (actor `cli:<user>`, a reason generated from the ladder's criteria); a ready promotion is a digest line, never a Telegram button (#449). Demotions are automatic (`system:demotion`).
- **Strikes are entered by hand** (`clipforge autopilot strike`): Upload-Post documents no strike event (#450).
- **No assisted-card tap counts** toward the ladder, the spot checks or the producer window (R2, R6, #454); only review-service decisions from S2b on, made on the dashboard (ADR-54).
- **The digest** is one message at 09:00 in the owner's time zone, ending with "N items need review → Open" (no cards follow, ADR-54); anomalies first; lines with nothing to say are left out (#443, #455; spec §7.2). Plan Task 23 now registers the `digest` task itself (Task 20 is removed).
- **Tracking links (ADR-33, accepted 2026-10-02):** `GET /go/<slug>` logs a click (never the IP or user agent) and redirects with a sub-id; bio and affiliate links are wrapped at hand-off; campaign `required_links` stay verbatim (#452, #456). Conversion import is draft ADR-51, for S7: not here.
- **The two new accounts start Hands-on** and launch on S2's flow (ADR-48, #135). They are created by the owner (`clipforge account create`), never by the session.
- **S2c adds no migration.**

Other sessions: possibly S3 (the dashboard) and the hooks card. S3's `GET /needs` turns this card's `open_problems()` into rows; this card serves the data only.

## Read first
1. `CLAUDE.md`, `STATUS.md`
2. `docs/reports/014-s2a-*.md` and `docs/reports/015-s2b-*.md`
3. The S2 plan: Global Constraints, Part S2c (Tasks 21–26, the owner launch steps and the rollback after Task 26), and the coverage tables at the end
4. The S2 spec: §5.2, §5.4, §5.5 (the ladder and demotions), §7.2 (the digest), §7.3 (failure rows), §7.4 (tracking links), §9 (S2c and the exit)
5. `docs/DECISIONS.md`: ADR-33, ADR-44, ADR-45, ADR-48, ADR-49, ADR-54
6. Log rows #440–#461, #138–#140, and the S2a and S2b rows (#480–#529)
7. `docs/studio/09-account-registry.md` (the two accounts), runbook §2, §2a and §6

## Scope
- May edit, as `scripts/scopes.toml` allows for `s2c/`: `src/**`, `tests/**`, `alembic/**` (none expected), `alembic.ini`, `.env.example`, `pyproject.toml`, `uv.lock`, `web/openapi.json`, `web/lib/api/**`, `web/lib/mocks.ts` and `web/tests/unit/summaries.test.ts` (only if an additive API field reaches them), `docs/ops/secrets.md`, `docs/ARCHITECTURE.md`, `docs/superpowers/plans/*-studio-s2*`, `docs/studio/04-roadmap.md` and `ROADMAP.md` (S2 ticks), `CLAUDE.md` (Commands and Layout: the new modules and commands), its own report, and log rows #530–#549.
- Must not edit: the spec, the runbook, `STATUS.md`, `docs/studio/09-account-registry.md` (tell the coordinator the handles and ids to record), other cards, stage modules, `prompts/`.
- **The session never deploys, creates accounts or sources, connects profiles, or changes a secret**: the owner does, from the commands below. Never write permission facts or evidence links into any file or report.

## Actions
Each task follows the plan: failing tests first, then the implementation, then its checks, then "check and record".
1. **Task 21:** the ladder, promotions, strikes and automatic demotions (`accounts/ladder.py`, pure over counted stats; `promote`, `record_strike`, `check_demotion` in `accounts/autopilot.py`; `review/service.py` calls `check_demotion` on a spot-check reject; `clipforge autopilot promote|strike`; the admin promote and ladder routes).
2. **Task 22:** the `sample` and `auto` dials end to end (auto-lane approval and the spot-check state per account in `dispatch/plan.py`; the floor of 1 in 10 and 3 a week).
3. **Task 23** (amended 2026-10-02, log #142: `gather` takes a tuple of `DigestProvider`s from `runtime.build_deps`, none in S2, a failing provider skipped, so S3c-3 adds its line without editing `dispatch/digest.py`): the 09:00 digest message (`build_digest`, `send_digest`; the `digest` task, registered here, sends the digest and no batch, ADR-54), including the attention arithmetic (review decisions only) and the promote command line.
4. **Task 24:** failure rows and alerts (`publishing/problems.py`, `open_problems()` over `failed` and `final_failed` rows, `alert_problem` used by reconcile's final check, the webhook and autopilot (no assisted fallback, ADR-54); "publishing broken across accounts" breaks through quiet hours).
5. **Task 25:** tracking links (`tracking.py`, `db/tracking.py`, `GET /go/{slug}`, the admin link routes, `clipforge link add|list`, `link_for` passed to `copy_for` at hand-off).
6. **Task 26:** launch support and the docs: account create warns over `UPLOAD_POST_PROFILE_LIMIT`; `docs/ARCHITECTURE.md`, `.env.example` and `CLAUDE.md` (Commands and Layout) updated; tick S2 items in `docs/studio/04-roadmap.md` and `ROADMAP.md` (the S2 line itself only after the exit below is met).
7. **Checkpoint S2c** (plan Task 26 step 3): `web/openapi.json` regenerated if routes changed; run `pr-reviewer`, `security-reviewer` (`/go`, click logging, no personal data) and `docs-auditor`; `scripts/check.sh` green; the report; stop.
8. **After the owner's launch steps:** record the exit evidence in the report (below), with no secrets, URLs with signatures, or permission details, and give the coordinator the handles and account ids for 09.

## Checkpoints
- A (S2c): after actions 1–7. Suggested commit: `016: s2c: ladder, digest, failure rows, tracking links; launch support`
- B (launch evidence): after action 8, a report-only update. Suggested commit: `016: s2c: launch evidence; S2 ticked`

## Done when
- `scripts/check.sh` is green at A and B (paste the summary lines).
- `pr-reviewer`, `security-reviewer` and `docs-auditor` have no blocking findings.
- **04's S2 exit, with evidence in the report:**
  - realtalk posts to all 4 platforms through Upload-Post on its rung;
  - founder.tapes and hombre.en.construccion run Hands-on on S2's flow, each with a queue from one permitted source;
  - the 09:00 digest arrives;
  - a gate failure lands in review (one sponsored item without `#ad`);
  - every post and click is recorded (`posts`, `post_events`, `clicks`).

## Owner steps
- Before: card 015 deployed and a day on Hands-on; O3 done (the handles warmed up per runbook §6); one permitted source each lined up. `scripts/worktree.sh s2c/ladder-launch`, open a session in `../clipForge-s2c`, paste `Run card docs/cards/016-s2c-ladder-launch.md`.
- At A: commit, `git push -u origin s2c/ladder-launch`, `gh pr create --fill`, squash-merge when CI is green. Then the launch:
  1. `scripts/deploy.sh --dry-run`, then `scripts/deploy.sh --reason "S2c: autopilot, digest, links"`, outside the blackout (runbook §1).
  2. `uv run clipforge account create --blueprint founder-tapes --lang en --handle <O3 handle>` and `uv run clipforge account create --blueprint hombre-en-construccion --lang es --handle <O3 handle>`. Both start Hands-on.
  3. One permitted source each: `uv run clipforge source add …` with its permission record, then clip at least one episode (`uv run clipforge clip videos/<source>/<file> --fetch`).
  4. One Upload-Post profile each (`founder-tapes-en`, `hombre-en-construccion-es`; 3 of Basic's 5), connected as in S2b. Then `uv run clipforge account edit <id> --publisher-profile <id> --facebook-page-id <id>` and `uv run clipforge publisher check <id>`.
  5. Optional: `uv run clipforge link add realtalk-clips-en <bio url> --kind bio`, then put the printed `/go/<slug>` link in the bio.
  6. Check the exit (Done when) over the next days and paste the outputs back to the session for B.
- At B: commit, push, squash-merge.
- **Rollback:**
  - A new account: `uv run clipforge account edit <id> --clear-publisher` (it then posts nothing; no assisted fallback, ADR-54), or `/pause <id>`.
  - A promotion: `uv run clipforge autopilot preset <id> hands_on --reason "<why>"`.
  - A tracking link: remove it from the bio. `/go` keeps redirecting, so links already posted never break.
  - The whole step: a revert on `main`, then `scripts/deploy.sh --dry-run` and `scripts/deploy.sh --reason "revert S2c"`. S2c adds no migration.

## Hand-off
Write `docs/reports/016-s2c-<YYYY-MM-DD>.md` from `docs/templates/handoff-report.md` at each checkpoint. Don't commit: the owner does. After B the coordinator ticks S2 in STATUS and records the two accounts in 09.
