# Card 007: docs — audit and refresh every Markdown file, and find unused files

Status: proposed (after card 002 is merged)
Stream: cleanup · Branch: `cleanup/docs-refresh` · Worktree: `../clipForge-cleanup` (created with `scripts/worktree.sh cleanup/docs-refresh`)
Decision-log range: #400–#419 (append only, in this range)
Model: most capable (judging what is current needs the whole picture)
Depends on: card 002 merged, so the docs are checked against S1's final code
Cost cap: $0 (no Modal or API calls; `gh` reads only)

## Context
The repo grew fast on 2026-09-29/30: the studio docs (01–11), specs and plans, cards, reports, templates, `STATUS.md`, S1's and S3a's code, and card 001's `.claude/` agents and skills. Several Markdown files repeat another one (`ROADMAP.md` mirrors `docs/studio/04`; 05 points to `docs/DECISIONS.md`; `STATUS.md` summarizes the cards; `CLAUDE.md` and `docs/ARCHITECTURE.md` describe the code). Some still say "planned", "not built" or "awaiting" for work that has since merged, and some were written by tools rather than by us (`web/AGENTS.md` from Next.js, the Neon skills installed from `skills-lock.json`).

The owner wants every Markdown file to have a clear use and to describe the project **as it is on main**, and to know what can be deleted or merged. This card does both for Markdown. For anything else (code, scripts, assets, fixtures, folders) it only proposes changes, because those belong to other streams (`scripts/scopes.toml`).

## Read first
1. `CLAUDE.md`, `STATUS.md`, `README.md` (the doc map)
2. `docs/superpowers/README.md` (when specs and plans become historical), `docs/cards/README.md`, `docs/templates/`
3. `docs/studio/11-owner-runbook.md` §3.4 (rules for shared docs), `scripts/scopes.toml` (the `cleanup/` prefix and who owns everything else)
4. `docs/DECISIONS.md` and `docs/studio/10-decision-log.md`: what is decided, so a doc that contradicts them is the one to fix

## Scope
- May edit: Markdown only, as `scripts/scopes.toml` allows for `cleanup/`:
  - `docs/**/*.md` and the root `*.md` files;
  - `web/*.md`, `tests/fixtures/README.md`, `videos/README.md`;
  - our `.claude/agents/*.md` and `.claude/skills/*/SKILL.md`.
- Must not edit:
  - the installed Neon skills (`.claude/skills/neon*`, pinned by `skills-lock.json`);
  - the released prompts in `prompts/` (`CLAUDE.md` rule 4);
  - other cards' reports;
  - any code, config, script or test.
- Within the allowed files, these keep their history:
  - **The decision log:** append only. A wrong row gets a new row in this card's range, and the old row's status becomes `superseded by N`.
  - **Accepted ADRs in `docs/DECISIONS.md`:** don't rewrite the text. Only a status line may point to a newer ADR. If an accepted ADR is wrong, propose a new ADR in the report.
  - **Historical specs and plans:** add or fix the historical banner (per `docs/superpowers/README.md`), never rewrite the body.
  - **`web/AGENTS.md`:** the block between `BEGIN:nextjs-agent-rules` and `END:nextjs-agent-rules` is Next.js's. Leave it, and add project notes only outside it.
- Open PRs: before editing a file, check `gh pr list` and `gh pr diff <n> --name-only`. Leave any file an open PR changes, and list it as a follow-up instead, so this card doesn't create merge conflicts.

## Actions
1. **Audit every tracked `.md` file** (`git ls-files '*.md'`). For each, record:
   - **Purpose and reader:** one line (owner, coordinator, sessions, CI tests, Claude tooling).
   - **Origin:** written by us, or generated or installed by a tool (Next.js, the Neon skills).
   - **Copy of:** if it repeats another file, say which one is the source of truth.
   - **Linked from:** which docs link to it. A file nothing links to needs a reason to stay.
   - **Stale statements:** each with a line reference and the evidence from main, checked against the code (grep the names, commands, paths, settings and routes), `git log`, `gh pr list`, `docs/DECISIONS.md` and the decision log. Never against another doc. Typical problems:
     - "planned", "not built" or "awaiting" for built, merged or accepted work;
     - commands or flags that no longer exist;
     - wrong paths, card or PR states, ADR numbers or test counts;
     - copies that disagree with their source.
   - **Verdict:** keep; update (list the exact fixes); mark historical; merge into `<file>`; or delete, with the evidence.
2. **Audit the rest, proposals only:**
   - unused code, scripts and prompts (a `prompts/*_v<N>.md` that neither `metadata.json` nor the code references), assets, test fixtures, blueprints;
   - stray root folders and files (`scratch/`, `.superpowers/`, generated output, old lockfiles);
   - `.gitignore` patterns that hide files that should be tracked, or let through files that shouldn't be (`git ls-files --others --ignored --exclude-standard`).

   Before calling anything unused, check that no code or test imports or references it.
3. Run the `docs-auditor` agent, merge its findings into the same tables, then **stop at checkpoint A** with the report.
4. **After the owner and the coordinator approve** (they may strike items), apply the approved Markdown changes:
   - Each fix states the fact as it is on main, in the surrounding doc's style: plain words, short sentences, no new jargon.
   - `ROADMAP.md` and `docs/studio/04` stay in step (runbook §3.4).
   - A merged or deleted file leaves no broken links: the docs tests check links and anchors.
   - Log a row only for a lasting decision, such as a file deleted or merged and why. Routine corrections need no row.
5. Update the report with what changed, file by file, then **stop at checkpoint B**.

## Checkpoints
- A: the audit report (actions 1–3), with no other file changed. Suggested commit: `007: cleanup: docs audit report`
- B: the approved Markdown updates (actions 4–5). Suggested commit: `007: cleanup: refresh the docs to match main`

## Done when
- The report has one table per area: Markdown (by folder), code, assets, root. The columns are path | purpose | origin | problem | verdict | evidence | owner (branch prefix).
- The report lists the proposals for other streams, grouped by owning branch, each small enough for one PR.
- After B, a re-run of action 1 on the changed files finds no stale statement left. Anything still stale is listed with the reason, such as a file an open PR touches.
- `scripts/check.sh --docs --scope` is green at A, and the full `scripts/check.sh` is green at B.

## Owner steps
- Before: card 002 merged. Then run `scripts/worktree.sh cleanup/docs-refresh`, open a session in `../clipForge-cleanup`, and paste `Run card docs/cards/007-cleanup-docs.md`.
- At A: commit, push (`git push -u origin cleanup/docs-refresh`), open the PR (`gh pr create --fill`), and send the report to the coordinator. Tell the session which items are approved.
- At B: commit, push, squash-merge when CI is green. The coordinator writes the follow-up PRs for the other streams' proposals.

## Hand-off
Write `docs/reports/007-cleanup-<YYYY-MM-DD>.md` from `docs/templates/handoff-report.md`, with the audit tables in its summary section. Update it at B. Don't commit: the owner does.
