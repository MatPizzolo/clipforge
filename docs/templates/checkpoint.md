# Checkpoint protocol

At every checkpoint a session:
1. Runs `scripts/check.sh` until it's green, and pastes its summary lines into the report.
2. Writes or updates its report in `docs/reports/` (template: `handoff-report.md`).
3. Appends any lasting decision to `docs/studio/10-decision-log.md`, in its number range.
4. Stops and tells the owner the checkpoint is ready, with a suggested commit message.

Then the owner, in the session's worktree:
```
git add -A && git status --short
git commit -m "<card NNN>: <suggested message>"
git push -u origin <branch>
gh pr create --fill            # first checkpoint only; later pushes update the PR
```
CI runs `scripts/check.sh` and the scope check on the PR. The owner merges on GitHub when it's green (squash merge; the title keeps the card number). The coordinator reads the PR diff and the report, updates `STATUS.md`, and writes the next card.
