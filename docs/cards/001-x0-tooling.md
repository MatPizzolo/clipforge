# Card 001: X0 — working environment and controls

Status: proposed (send first, before cards 002–006)
Stream: X0 (tooling) · Branch: `x0/tooling` · Worktree: `../clipForge-x0`
Decision-log range: #380–#399
Model: most capable (it defines the rules every later session runs under)
Depends on: `gh` installed and logged in (owner step). Nothing else.
Cost cap: $0 (no Modal runs, no deploys)

## Context
On 2026-09-30 the studio moved from sessions sharing one folder to git worktrees and pull requests (decision log #123 and later). Several failures that day had one root cause: nothing enforced the rules.
- A session rewrote the decision log and erased another session's rows.
- A stale `web/openapi.json` passed every session's own checks.
- File ownership was guessed.
- The posting deploy blackout (#108) existed only as a rule in the runbook.

This card builds the checks and scripts that enforce them, so every later card (002–006) uses them. Production is live and Dict-only (`STATE_READS=dict`); `posting_tick` runs every 5 minutes; `DATABASE_URL` is not in the Modal secret.

## Read first
1. `CLAUDE.md`, `STATUS.md`, `docs/templates/*.md`, `docs/cards/README.md`
2. `docs/studio/11-owner-runbook.md` §1 (the blackout), §3 (sessions and hand-off), §8 (git)
3. `.github/workflows/ci.yml`, `.github/workflows/web.yml`, `scripts/export_openapi.py`, `web/package.json` scripts
4. `docs/studio/10-decision-log.md`: its structure (tables, the Open table, "superseded by N")
5. `src/clipforge/config.py` (`posting_slots`, `posting_timezone`), `src/clipforge/posting/slots.py`

## Scope
- May edit: `.claude/**` (settings, hooks, agents, skills, commands; not `.claude/skills/neon*`), `scripts/`, `tests/test_docs.py`, `tests/scripts/`, `.github/workflows/`, `docs/ops/`, `docs/templates/`, `docs/cards/README.md`, `docs/studio/11-owner-runbook.md` (commands only), `CLAUDE.md` (the Commands and Sessions sections), `STATUS.md`, `README.md` (the doc map only).
- Must not edit: `src/`, other tests, `web/` (except reading), any spec or plan.

## Actions
1. **`scripts/check.sh`**: one command that runs everything, fails fast, and prints a short summary per step.
   - Python: `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src`, `uv run pytest -q -m "not gpu and not slow"`.
   - Contract: `uv run python scripts/export_openapi.py --check`.
   - Web (if `web/` exists): `npm run check` and `npm run gen:check` in `web/`, with `npm run e2e` behind `--e2e`.
   - Docs: `uv run pytest -q tests/test_docs.py`.
   - Scope: `scripts/check_scope.py` against `origin/main`.
   - Flags `--python`, `--web` and `--docs` run one part. Exit non-zero on any failure.
2. **`scripts/check_scope.py` and `scripts/scopes.toml`.**
   - For the current branch, it lists the files changed against `origin/main` (merge base) and fails if any is outside the globs allowed for the branch prefix.
   - Always allowed on every branch: the branch's own report files (`docs/reports/*-<stream>-*`), and **appended** rows in `docs/studio/10-decision-log.md` whose numbers fall in the branch's range. Check that the diff to that file only adds lines, and only rows in range.
   - `main` itself is exempt.
   - Initial `scopes.toml` (prefix → allowed globs, log range):

     | Prefix | Allowed | Log range |
     |---|---|---|
     | `x0/` | this card's scope (incl. `.claude/**`) | 380–399 |
     | `s1/` | `src/**`, `tests/**`, `alembic/**`, `alembic.ini`, `blueprints/**`, `pyproject.toml`, `uv.lock`, `.github/workflows/ci.yml`, `.env.example`, `docs/ARCHITECTURE.md`, `docs/DECISIONS.md`, `CLAUDE.md`, `docs/superpowers/**/*s1*`, `STATUS.md` | 200–249 |
     | `s3c/` | `docs/superpowers/specs/*s3-workspaces*`, `docs/superpowers/plans/*s3c*`, `docs/studio/04-roadmap.md`, `docs/studio/05-proposed-adrs.md`, `docs/studio/06-session-prompts.md`, `docs/studio/08-dashboard-and-operations.md` | 250–299 |
     | `s3a/` | `web/**`, `scripts/export_openapi.py`, `.github/workflows/web.yml`, `docs/superpowers/**/*s3a*`, `ROADMAP.md`, `docs/studio/04-roadmap.md`, `CLAUDE.md` | 300–319 |
     | `x2/` | `docs/studio/03-tools-and-models.md`, `docs/studio/04-roadmap.md`, `docs/studio/spikes/**` | 320–339 |
     | `s4/` | `src/**`, `tests/**`, `docs/superpowers/**/*s4*`, `docs/ARCHITECTURE.md`, `CLAUDE.md` | 340–379 |
     | `coord/` | `docs/**`, `STATUS.md`, `ROADMAP.md`, `README.md`, `CLAUDE.md`, `.gitignore` | 1–199 |

   - Tests for it in `tests/scripts/test_check_scope.py` (a temp git repo fixture): an in-scope change passes, an out-of-scope file fails with its path, a log row outside the range fails, and an edited (not appended) log row fails.
3. **`tests/test_docs.py`** (fast, no network):
   - decision-log numbers are unique;
   - every `superseded by N` names an existing row;
   - ADR headings in `docs/DECISIONS.md` are unique and increasing, and 05 doesn't repeat the body of an accepted ADR;
   - every relative Markdown link in `docs/`, `README.md`, `CLAUDE.md` and `STATUS.md` resolves;
   - every `docs/cards/*.md` has a Status line and a decision-log range;
   - `.env.example` lists every setting in `config.Settings` that has no default (or document the exceptions in the test).
4. **CI** (`.github/workflows/ci.yml` and `web.yml`):
   - The `check` job runs `scripts/check.sh --python --docs`, and `web.yml` runs `scripts/check.sh --web --e2e`.
   - Add a `scope` job on `pull_request` that runs `scripts/check_scope.py` with `fetch-depth: 0`.
   - **Keep the deploy job exactly as gated** (`vars.DEPLOY_ENABLED == 'true'`), and don't add the Alembic step (that's S1's Task 21b).
5. **`scripts/worktree.sh <branch>`**: `git worktree add ../clipForge-<stream> -b <branch> origin/main` (or an existing branch), copy `.env` and `web/.env.local` if present, run `uv sync` and, if `web/` exists, `npm ci`. Print the next step ("paste: Run card docs/cards/…"). `scripts/worktree.sh --remove <branch>` removes a merged worktree. Refuse if the branch prefix isn't in `scopes.toml`.
6. **`scripts/deploy.sh`**, the only deploy path. It refuses (with the reason) unless all of these hold:
   - on `main`, the tree clean and equal to `origin/main`;
   - the latest CI run for that commit is green (`gh run list --commit <sha> --json conclusion`);
   - now is outside the blackout: from each posting slot to 30 minutes after it, using `POSTING_SLOTS` and `POSTING_TIMEZONE` from `.env` (default slots when unset, the same as `config.py`) (there is no override flag);
   - `STATE_READS` is `dict` unless the operator passes `--rollout-step 4c.7`.

   Then it runs `uv run modal deploy src/clipforge/app.py` with `GIT_SHA` set to the commit, tags `deploy-YYYYMMDD-HHMM` (UTC), pushes the tag, and appends a line to `docs/ops/deploys.md` (time, sha, who, why from `--reason`). A `--dry-run` prints every check without deploying. Unit-test the blackout calculation (a slot at 21:30 New York, a time 21:45 → refused; 22:01 → allowed; across midnight).
7. **Docs**:
   - `CLAUDE.md` gets a short "Sessions" section: work from a card in `docs/cards/`, run `scripts/check.sh` before every checkpoint, write the report, never commit or deploy, stay in scope.
   - Its Commands list adds `scripts/check.sh`, `scripts/worktree.sh` and `scripts/deploy.sh`.
   - The runbook's §1 and §8 point to `scripts/deploy.sh` instead of a bare `modal deploy`.
8. Write the report `docs/reports/001-x0-<date>.md`, and append decision-log rows (#380+) for: `check.sh` as the single gate, the scope rules, and deploys only through `deploy.sh`.

**Checkpoint C: guardrails inside every session (`.claude/`).** Before relying on any format below, check it against the current Claude Code docs (settings, hooks, permissions, sub-agents, skills pages on code.claude.com/docs) and test it. Hook scripts live in `.claude/hooks/`, read the hook JSON on stdin, run in under ~200 ms, and have unit tests in `tests/scripts/test_hooks.py` that feed sample stdin JSON and check the exit code and output. A crashing hook must never block normal work (only an explicit match blocks).

9. **Hooks** in `.claude/settings.json` (committed; per-user overrides go in the gitignored `.claude/settings.local.json`):
   - **PreToolUse `Bash` guard** (`.claude/hooks/bash_guard.py`). It blocks with a clear reason:
     - `git commit`, `push`, `merge`, `tag`, `rebase`, `reset --hard`, `checkout -- .`, `clean -f`;
     - `gh pr merge`, `gh repo …`, `gh secret`, `gh variable`;
     - `modal deploy`, `modal app stop`, `modal secret …`, `modal volume rm`;
     - `vercel deploy --prod`, `vercel env …`;
     - any command that prints `.env`, `web/.env.local` or `.neon` (`cat`, `less`, `grep`, `source` and similar).

     It allows read-only git (`status`, `diff`, `log`, `show`, `ls-files`, `branch --show-current`, `fetch`), plus `scripts/check.sh` and `scripts/check_scope.py`. The message tells the session to give the owner the command instead.
   - **PreToolUse `Edit|Write|MultiEdit|NotebookEdit` scope guard** (`.claude/hooks/scope_guard.py`):
     - It denies an edit to a path the current branch prefix may not touch (`scripts/scopes.toml`, the same logic as `check_scope.py`).
     - It denies any edit to `.env*` (except `.env.example` files), `.neon`, `web/.env.local` and `.claude/settings.local.json`.
     - It denies a `Write` (full overwrite) of `docs/studio/10-decision-log.md`, so only appending edits get through; that's the 2026-09-30 failure.
     - On `main` (the coordinator), only `coord/` paths are allowed.
   - **SessionStart** (matchers `startup`, `resume`, `compact`), in `.claude/hooks/session_context.py`. It injects as additional context:
     - the branch;
     - the card whose `Branch:` line matches (its number, title, scope and log range);
     - the top of `STATUS.md` (the next-cards table);
     - the rules (no commits or deploys, `scripts/check.sh` before every checkpoint, reports in `docs/reports/`, append-only log in range).

     It also warns when a card session runs on `main`. After compaction this restores the card context.
   - **Stop** (`.claude/hooks/stop_check.py`):
     - `scripts/check.sh` writes a marker (`.superpowers/check-ok` with the tree hash from `git stash create` or `git write-tree` of the index plus the working tree) when it's green;
     - if tracked files changed since the last green marker, block the stop once with "run scripts/check.sh and write your report";
     - respect `stop_hook_active` so it never loops, and never block when nothing changed.
10. **Permissions** (same file):
    - deny reading `.env`, `web/.env.local`, `.neon`;
    - allow without prompting `scripts/check.sh*`, `scripts/check_scope.py*`, `uv run pytest*`, `uv run ruff*`, `uv run mypy*`, `npm run check|test|lint|typecheck|gen:check|e2e` in `web/`, and read-only git;
    - ask for `uv run modal run*` (it spends money), `npm install*` and `uv add*`.

    Check whether a Read deny also covers `cat .env` in Bash. The Bash guard covers it either way.
11. **Agents** in `.claude/agents/` (frontmatter: name, description, tools, model):
    - `pr-reviewer` (opus; Read, Grep, Glob, Bash). It reviews a branch against its card, `scripts/scopes.toml`, CLAUDE.md rules 1–9 and the accepted ADRs; runs `scripts/check.sh`; reports findings by severity with file:line; and lists changes the card doesn't mention. It never edits.
    - `security-reviewer` (opus): auth, bearer and proxy auth, webhook secrets, signed links, SSRF, redaction and logs, secrets in code, the AUTH_DISABLED and MOCK_API guards.
    - `migration-reviewer` (opus): Alembic (frozen revisions, expand-only changes, downgrade, autogenerate empty), the Dict→Postgres rules (ADR-24, 26, 41, 46), rollback through `STATE_READS`.
    - `docs-auditor` (sonnet): `STATUS.md`, the decision log's rules, the roadmap ticks versus merged work, links, stale docs. It edits nothing; it lists fixes.
    - Update `pipeline-reviewer`: model opus, plus STAGE_VERSION bumps, ADR-43's derived `producer_version` and cost logging. It runs `scripts/check.sh` instead of bare pytest.
12. **Skills** in `.claude/skills/<name>/SKILL.md`:
    - `run-card`: triggered by "Run card docs/cards/…". Read the card and its read-first list; confirm the branch matches the card; restate the scope, actions, checkpoints and cost cap in five lines; then work, stopping at each checkpoint.
    - `checkpoint`: run `scripts/check.sh` until green; write or update the report from the template; append log rows in range (via `log-append`); stop with the suggested commit message.
    - `write-report`: fill `docs/templates/handoff-report.md`, with the current `git diff --stat` and the changed file list inlined.
    - `log-append`: re-read `docs/studio/10`, take the next free number in the branch's range, append rows only, and mark a superseded row's status.
    - `write-card` (coordinator): build a card from `docs/templates/card.md` and the matching prompt and action card in 06; pick the number and range; add it to `docs/cards/README.md` and `STATUS.md`.
    - `review-pr` (coordinator): `gh pr view` and `gh pr diff` for a PR, plus its report and card, then the `pr-reviewer` agent; a verdict; update `STATUS.md` and the card's status line.
    - Migrate `.claude/commands/new-stage.md` and `run-eval.md` into skills with the same behavior. **Delete `.claude/commands/next-task.md`**: it points at ROADMAP.md and conflicts with the card flow.
    - Keep `.claude/skills/neon*` unchanged.
13. `CLAUDE.md`'s Sessions section names the skills (`run-card`, `checkpoint`) and the agents (`pr-reviewer` before every merge). The runbook's §3.2 says that the coordinator uses `review-pr`. Append decision-log rows for the hooks, the permissions and the agent and skill set.

## Checkpoints
- A: actions 1–3 (check.sh, scope check, docs tests). Suggested commit: `x0: check.sh, scope check and docs tests`.
- B: actions 4–8. Suggested commit: `x0: CI on check.sh, worktree and deploy scripts`.
- C: actions 9–13. Suggested commit: `x0: .claude guardrails (hooks, permissions, agents, skills)`. Land it last: once the hooks exist, they apply to this session too.

## Done when
- `scripts/check.sh` is green on this branch, and the scope check passes for it.
- `scripts/check_scope.py` fails on a deliberately out-of-scope change (show the output, then undo it).
- `scripts/deploy.sh --dry-run` prints every check. Right now it must refuse because the tree isn't `main`; show that.
- The CI run on the PR is green (the owner confirms).
- `tests/scripts/test_hooks.py` is green, and a live demonstration works in this session:
  - `git commit` is blocked;
  - an edit outside the x0 scope is denied;
  - a `Write` over the decision log is denied;
  - after a `/compact`, the SessionStart context names card 001.

## Owner steps
- Before:
  ```
  sudo apt install gh        # or: https://cli.github.com (Debian/Ubuntu instructions)
  gh auth login              # GitHub.com, HTTPS, browser
  cd ~/code/clipForge && git worktree add ../clipForge-x0 -b x0/tooling origin/main
  cp .env ../clipForge-x0/ && (cd ../clipForge-x0 && uv sync)
  ```
  Then open the session in `../clipForge-x0` and paste: `Run card docs/cards/001-x0-tooling.md`.
- At each checkpoint: `docs/templates/checkpoint.md`.
- After checkpoint C: approve the project hooks when Claude Code asks you to trust them (first run of a session in the repo).
- After the merge: turn on branch protection for `main` (runbook §8, "Protect main").

## Hand-off
Write `docs/reports/001-x0-<YYYY-MM-DD>.md` from `docs/templates/handoff-report.md` at each checkpoint and at the end. Don't commit.
