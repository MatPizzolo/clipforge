# Card 017: X0 — CI and repo hygiene

Status: done 2026-10-02 (PR #37)
Stream: X0 (tooling) · Branch: `x0/ci-speed` · Worktree: `../clipForge-x0` (created with `scripts/worktree.sh x0/ci-speed`)
Decision-log range: #380–#399 (append only; #380–#395 are taken, so #396–#399 are free: re-read the log, and use at most one row per lasting rule)
Model: mid-tier (workflow edits and a measured investigation)
Depends on: nothing. Runs alongside 010 (rollout, don't touch production), 018, 019, 020, 021
Cost cap: $0 (GitHub Actions minutes on this branch's own PR only; no Modal, no API spend)

## Context
CI is slow and noisy. `.github/workflows/ci.yml` runs on every `push` **and** every `pull_request`, so each commit on a PR branch runs the whole gate twice. A docs-only PR (most coordinator and design PRs) still installs ffmpeg, runs `uv sync` and the full pytest suite. `web.yml` uses workflow-level `paths:` filters, which is fine today but would leave a required check pending if branch protection ever required it. One fast test flakes under load (action 5).

**Production is out of bounds today.** Card 010 (the S1 rollout) runs its live steps at 22:00 New York time. This card never deploys, never touches `clipforge-secrets`, never runs Alembic against Neon, and doesn't change the `deploy` or `tag` jobs' behaviour: they keep running only on pushes to `main`, exactly as now (still off behind `DEPLOY_ENABLED`). `x0/` may never touch `src/` (a guardrail test in `tests/scripts/test_check_scope.py` enforces it).

Other sessions today: card 010 (rollout), 018 (S3c plan), 019 (S3 plan), 020 (hooks), 021 (S5, after PR #33). All of them are docs-only, so action 2 speeds up every one of their PRs.

## Read first
1. `CLAUDE.md`, `STATUS.md`
2. `.github/workflows/ci.yml`, `.github/workflows/web.yml`, `.github/workflows/manual.yml`
3. `scripts/check.sh` (its `--docs`, `--python`, `--web`, `--scope` modes), `scripts/check_scope.py` (how `scopes.toml` entries load: `log` is required and must be two integers), `scripts/scopes.toml`
4. `tests/dbfixture.py`, `tests/conftest.py`, `tests/pipeline/harness.py` (how DB tests get their schema), `tests/test_service.py` (the flaky test), `src/clipforge/service.py` and the `package_step` path that writes the `jobs` row (read only)
5. ADR-16 in `docs/DECISIONS.md`; log rows #108, #109, #212, #380, #381, #386, #395
6. `docs/reports/012-x4-*.md` (probes living outside the repo)

## Scope
- May edit, as `scripts/scopes.toml` allows for `x0/`: `.github/**` (workflows, the PR template, dependabot), `.gitignore`, `scripts/**` (including `scripts/scopes.toml`), `tests/scripts/**`, `tests/test_docs.py`, `tests/test_service.py` (only for action 5's test-side fix), `.claude/**` (not the Neon skills), `docs/ops/**`, `docs/templates/**`, `docs/cards/README.md`, `docs/studio/11-owner-runbook.md`, `CLAUDE.md`, `STATUS.md`, `README.md`, its own report, and log rows #396–#399.
- Must not edit: `src/**`, `web/**` (`web.yml` is under `.github/`, so it is in scope), `alembic/**`, `pyproject.toml` and `uv.lock` (see action 4: an adopted pytest-xdist needs an `s1/`/`s2a/` follow-up or an owner ruling to widen this scope), other cards, the decision log outside the range.

## Actions
1. **One run per commit.** In `ci.yml`, change the trigger to `push: branches: [main]` plus `pull_request`. The `deploy` and `tag` jobs keep their `if:` conditions (main pushes only). Keep the `concurrency` block as it is (never cancel on `main`).
2. **Docs-only fast path, without `paths:` filters.**
   - Add a first job `changes` (no third-party action): `actions/checkout` with `fetch-depth: 0`, then `git diff --name-only` against `origin/${{ github.base_ref }}` on a PR, or `${{ github.event.before }}` on a `main` push (when `before` is all zeros or missing, treat it as code). Output `code=true|false`. Docs-only means every changed path matches `docs/**`, `*.md` at any level (`**/*.md`), `STATUS.md`, `ROADMAP.md`, `.gitignore` or `docs/cards/**`; anything else is code.
   - `check` gets `needs: changes` and always runs, so it always reports a conclusion: with `code == 'false'` it runs only `scripts/check.sh --docs` (the docs tests run under `uv`: keep `setup-uv` with its cache and `uv sync --locked`, and measure whether a narrower sync is faster) and skips the ffmpeg install and pytest. With `code == 'true'` it runs today's steps.
   - `scope` keeps running on every PR (it is cheap) and keeps its job name.
   - **Job names stay `check` and `scope`**: branch protection will require them (owner step).
   - Never add workflow-level `paths:` to `ci.yml`. For `web.yml`: decide whether its `web` job should become a required check. If yes, move it to the same `changes`-job pattern (the job always runs and reports success when nothing under its paths changed). If no, leave the `paths:` filter and write why in a comment at the top of `web.yml` and in the report (a required check under `paths:` stays "pending" forever on PRs that don't match).
   - Tests in `tests/scripts/` for the classifier: put the path rule in a small script (`scripts/ci_changes.py` or a function in an existing script) that the workflow calls, so it is unit-tested: a docs-only diff is `false`; `src/x.py`, `scripts/check.sh`, `.github/workflows/ci.yml`, `pyproject.toml`, `web/app/page.tsx` and `prompts/x_v1.md` are `true`; `web/README.md` is `false`.
3. **Speed.**
   - ffmpeg: cache the apt install (for example `awalsh128/cache-apt-pkgs-action`, pinned by SHA, or an explicit `actions/cache` of the `.deb` files keyed on the runner image and package list), or use a static-ffmpeg action **only** if it gives the same major version and libass support as Ubuntu 24.04's ffmpeg 6.1 that the tests run on today. Print `ffmpeg -version | head -1` in the job either way, and state in the report that the version didn't change.
   - `web.yml`: cache Playwright browsers (`~/.cache/ms-playwright`, key on `web/package-lock.json`); on a cache hit run only `npx playwright install-deps chromium`.
   - Add `timeout-minutes` to every job in `ci.yml`, `web.yml` and `manual.yml` (for example `changes` 5, `check` 20, `scope` 5, `web` 20, `tag` 5; keep `deploy` at 60).
4. **pytest-xdist, measured.** Locally, time `uv run pytest -q -m "not gpu and not slow"` three times serially and three times with `uv run --with pytest-xdist pytest -q -n auto -m "not gpu and not slow"` (no lockfile change for the measurement). Check that DB tests are isolated per worker (per-test schemas in `tests/dbfixture.py`; session-scoped fixtures that write shared files or a shared Postgres database are the risk). Run the parallel suite at least 5 times in a row. Adopt it only if every run is green and the gain is worth it; adoption needs `pyproject.toml` and `uv.lock`, which `x0/` may not edit, so write the exact change (`pytest-xdist` in the dev group, the `scripts/check.sh` flag) as a follow-up for the owner to assign. Report the timings either way.
5. **The flaky test.** `tests/test_service.py::test_a_row_without_cost_rows_takes_the_breakdown_from_metadata` failed twice under load on 2026-10-02: the `jobs` row stayed `queued` with `metadata_path` None; it passes alone. Reproduce it (`-p no:randomly` if installed, a loop of 20 runs, the suite under `-n auto`, or CPU stress), then find the root cause with superpowers:systematic-debugging. One hypothesis to test first: `package_step`'s `jobs` row write is best-effort, so under load a 5 s statement timeout or a lock wait is swallowed and the row is never updated, and the test reads it without waiting for or checking that write. If the fix is only in the test (for example the harness runs a step asynchronously and the test must drain it), fix `tests/test_service.py`. If it needs `src/`, don't touch it: write the root cause, the evidence and the proposed fix in the report for an `s1/` or `s2a/` card, and mark the test with a comment pointing to it (no `skip`; DB tests never skip).
6. **PR template.** Add `.github/pull_request_template.md`: the card number and checkpoint, the `scripts/check.sh` summary lines, the owner steps after the merge (or "none"), and a reminder that the squash title is `NNN: <stream>: <what>` (coordinator PRs: `coord: <what>`).
7. **Dependabot for actions only.** Add `.github/dependabot.yml` with one `github-actions` ecosystem, weekly, all updates in one group. Add a `[prefix."dependabot/"]` entry to `scripts/scopes.toml` (stream `dependabot`, allow only `.github/workflows/**`). `check_scope.py` requires `log` as two integers; use an empty range `log = [0, -1]` (no number is ever in range) and add a test in `tests/scripts/test_check_scope.py` that a `dependabot/github_actions/...` branch may change a workflow and nothing else, and may not add log rows. Pin every third-party action in all workflows to a full commit SHA with a `# vX.Y.Z` comment (`actions/*` too; dependabot keeps the SHAs current).
8. **Scratch folder for spikes.** Add `scratch/**` to `.gitignore`. In `scripts/scopes.toml`, add `scratch/x2/**` to `x2/` and `scratch/x4/**` to `x4/`, and a comment that every future spike prefix (`x*/`) gets `scratch/<stream>/**`. Add a test that `x4/` may write under `scratch/x4/` and not `scratch/x2/`. The scope check only sees untracked files that aren't ignored, so the allow lines matter for the edit guard (`.claude/hooks/scope_guard.py`): confirm in a hook test that an Edit under `scratch/x4/` on an `x4/` branch is allowed.
9. **A test that collides with real prefixes.** `tests/scripts/test_check_scope.py::test_coord_may_edit_scopes_toml_but_no_other_script` appends a fake `[prefix."s5/"]` to a copy of `scopes.toml`, so a real `s5/` prefix breaks it (that is why card 021 uses `s5d/`). Rename the fake to a prefix that can never be real (for example `zz-test/`) and use a log range outside every real one.
10. `scripts/check.sh` green, the report with the timings (before and after, for a docs-only and a code PR), one log row for the CI rule (in range), stop.

## Checkpoints
- A: actions 1–10. Suggested commit: `017: x0: one CI run per commit, docs-only fast path, caches, timeouts, PR template, dependabot, scratch/`

## Done when
- `scripts/check.sh` is green (paste its summary lines).
- On this branch's own PR: a docs-only commit (push a one-line change to a `.md` file) shows the `check` job finishing in under a minute and green; a code commit runs the full gate **once** (one `check` run per commit, from the `pull_request` event only).
- The `check` and `scope` job names are unchanged; `deploy` and `tag` still only run on `main` pushes.
- `ffmpeg -version` in the CI log shows the same major version as before.
- The classifier and the `dependabot/` and `scratch/` scope rules have tests.
- The report has the xdist timings and either the flaky test's fix or its root cause with a follow-up for `s1/`/`s2a/`.

## Owner steps
- Before: `scripts/worktree.sh x0/ci-speed`, open a session in `../clipForge-x0`, paste `Run card docs/cards/017-x0-ci-speed.md`.
- At A: commit, `git push -u origin x0/ci-speed`, `gh pr create --fill`; push the docs-only test commit the report names and check the timings; squash-merge when green.
- After the merge:
  - Branch protection for `main` (Settings → Branches, or `gh api -X PUT repos/<owner>/clipForge/branches/main/protection` with the payload in the report): require a PR, require the `check` and `scope` status checks, block force pushes. It may need GitHub Pro on a private repo.
  - Delete merged branches automatically: `gh repo edit --delete-branch-on-merge` (or Settings → General → "Automatically delete head branches").
  - If the report recommends pytest-xdist, assign the `pyproject.toml`/`uv.lock` change to a code card.

## Hand-off
Write `docs/reports/017-x0-<YYYY-MM-DD>.md` from `docs/templates/handoff-report.md`. Don't commit: the owner does.
