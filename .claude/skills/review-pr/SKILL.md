---
name: review-pr
description: Coordinator only. Review a pull request before the owner merges it — gh pr view and gh pr diff, the card and its report, then the pr-reviewer agent — and give a verdict; afterwards update STATUS.md and the card's status line. Use when the owner says a PR or checkpoint is ready for review.
argument-hint: <PR number>
---

Review PR #$ARGUMENTS for the owner. You don't merge, push or comment on GitHub: the owner does.

1. **Read the PR:** `gh pr view $ARGUMENTS` (title, branch, checks) and `gh pr diff $ARGUMENTS --name-only`, then the full diff. `gh pr checks $ARGUMENTS` must show `check` and `scope` green (and `web` when it ran).
2. **Find the card and report:** the card whose `Branch:` line matches the PR's head branch, and that stream's newest report in `docs/reports/`. Read both in full.
3. **Delegate the line-by-line review** to the `pr-reviewer` agent with the PR number, the card path and the report path. Add `security-reviewer` when the diff touches auth, webhooks, links, ingest, `sanitize.py`, `config.py`, secrets or `web/` auth; `migration-reviewer` for `alembic/`, `db/` or rollout steps; `pipeline-reviewer` for `stages/`, `pipeline/` or `models.py`. Run them in parallel.
4. **Verdict** for the owner, short:
   - merge / merge after fixes / don't merge;
   - the blocking findings, each with `file:line`;
   - changes the card doesn't mention;
   - anything the owner must decide.
   If fixes are needed, write them as a short numbered list the owner can paste into the card's session.
5. **After the owner merges** (on a `coord/` branch):
   - update `STATUS.md`: the workstream row, the next-cards table, the addendum tracker and "Last updated";
   - update the card's Status line (`done YYYY-MM-DD (report: docs/reports/…)` at the last checkpoint);
   - update its row in `docs/cards/README.md`;
   - record the review's lasting rulings with `log-append`, in `coord/`'s range.
   Then run `scripts/check.sh --docs --scope`, and give the owner the commit commands.
