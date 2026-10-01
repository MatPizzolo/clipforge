# Card 008: X0 — deploy and hook follow-ups from card 002

Status: done 2026-10-01 (report: docs/reports/008-x0-2026-10-01.md; PR #14)
Stream: X0 (tooling) · Branch: `x0/followups` · Worktree: `../clipForge-x0` (created with `scripts/worktree.sh x0/followups`)
Decision-log range: #380–#399 (append only, in this range; #380–#390 are taken, re-read the log)
Model: mid-tier
Depends on: card 002 merged (PR #5). Can run alongside cards 006 and 007 (007 edits Markdown only; this card's Markdown is limited to the runbook commands and `docs/ops/`)
Cost cap: $0 (no Modal runs, no deploys)

## Context
Card 002 finished S1's code and stopped before the rollout. Its final review and the coordinator's reviews left three changes in X0's scope (`scripts/`, `.github/workflows/`, `.claude/`):
- `scripts/deploy.py` deploys even when the database is behind the code's migrations. That matters from the first migration after 0001 (S3c's 0002).
- CI's deploy job (still off behind `DEPLOY_ENABLED`) doesn't do what `scripts/deploy.sh` does after a deploy: no `deploy-YYYYMMDD-HHMM` tag, no line in `docs/ops/deploys.md`. Deploys from CI would be missing from the deploy history.
- The Stop hook asks every session for a card report. The coordinator works on `main` or on `coord/` branches and has no card report, so the hook blocks it at every stop.

## Read first
1. `CLAUDE.md`, `STATUS.md`
2. `scripts/deploy.py`, `scripts/deploy.sh`, `.github/workflows/ci.yml` (the deploy job), `docs/ops/deploys.md`
3. `src/clipforge/db/doctor.py` (`EXPECTED_HEAD`), `alembic/`
4. `.claude/hooks/stop_check.py`, `.claude/settings.json`, decision log #382, #387

## Scope
- May edit: as `scripts/scopes.toml` allows for `x0/`.
- Must not edit: `src/`, `alembic/`, other tests, `web/`, any spec or plan.

## Actions
1. **Migration head in `deploy.py`:** a new check, "database at the code's migration head".
   - It compares the database's `alembic_version` with the newest revision in `alembic/versions/`, read-only, through `DATABASE_URL_UNPOOLED` from `.env`.
   - When `.env` has no database URL, or production doesn't use the database yet (`DATABASE_URL` isn't in the Modal secret before rollout step 4c.2), the check passes with that reason. Use a `.env` flag `DEPLOY_DB_CHECK=on|off`, default `off`, and say in the runbook to set it `on` at step 4c.2.
   - Unit tests with the facts faked, as the existing checks do: behind refuses, at head passes, off passes with the reason.
2. **CI deploys leave a record:** after a successful `modal deploy`, the CI job pushes the same `deploy-YYYYMMDD-HHMM` tag. A deploy line can't be committed to `main` from CI without a write token, so instead:
   - the job writes the line into its run summary (`$GITHUB_STEP_SUMMARY`);
   - `docs/ops/deploys.md` says CI deploys are listed by their tags (`git tag -l 'deploy-*'`).
   The job needs `contents: write` only for the tag push; keep every other permission read-only.
3. **The Stop hook and the coordinator:** on `main` and on `coord/` branches, the Stop hook still asks for a green `scripts/check.sh` after changes, but no longer asks for a report in `docs/reports/`. Test both branches and a card branch.
4. **Runbook and ops docs (commands only):**
   - runbook §8 "still left": card 007 wrote that the condition for `DEPLOY_ENABLED` "is met". Correct it: it also needs the repository variables `POSTING_SLOTS` and `POSTING_TIMEZONE` (identical to `clipforge-secrets`), the secret `DATABASE_URL_UNPOOLED`, `MODAL_TOKEN_ID`/`MODAL_TOKEN_SECRET`, and this card's tag step; CI deploys are recorded by tag;
   - rollout step 2 in §4 (the deploy that first has `DATABASE_URL` in the secret): set `DEPLOY_DB_CHECK=on` in `.env`.

5. **Keep a failing step's output:** when a `check.sh` step fails, also save its full output to `.superpowers/check-last-fail.log` (ignored by git) and print that path. On 2026-10-01 the fast tests failed once on `main` and passed on two reruns, and the failing test couldn't be identified because only the last 60 lines reach the terminal. Look for tests that read the real clock (the quiet hours, 23:00–08:00 New York, caught two in card 002) and fix any you find, with the clock pinned.

## Checkpoints
- A: actions 1–5. Suggested commit: `008: x0: deploy.py migration head, CI deploy tags, Stop hook on main/coord`

## Done when
- `scripts/check.sh` is green, with the new tests.
- `scripts/deploy.sh --dry-run` on `main` lists the migration check with its reason.

## Owner steps
- Before: `scripts/worktree.sh x0/followups`, open a session in `../clipForge-x0`, paste `Run card docs/cards/008-x0-followups.md`.
- After: commit, `git push -u origin x0/followups`, `gh pr create --fill`, squash-merge when CI is green.

## Hand-off
Write `docs/reports/008-x0-<YYYY-MM-DD>.md` from `docs/templates/handoff-report.md`. Don't commit: the owner does.
