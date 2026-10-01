---
name: checkpoint
description: Close a card checkpoint. Use when a card's checkpoint is reached (or the owner says "checkpoint"). Runs scripts/check.sh until green, writes or updates the report, appends decision-log rows in range, then stops with the suggested commit message.
---

Close the current checkpoint of the card this branch runs (its `Branch:` line matches `git branch --show-current`).

1. **Gate:** run `scripts/check.sh` (the full run, no flags; add `--e2e` only if the card asks). Fix failures and rerun until every line says `ok`. Don't skip or weaken a check to get green; if a check is wrong, say so and ask. Only a green full run writes the marker the Stop hook looks for.
2. **Scope:** the summary's `scope` line must pass. If a file is out of scope, undo it or ask the owner.
3. **Report:** use the `write-report` skill to write or update `docs/reports/NNN-<stream>-<YYYY-MM-DD>.md`, with the checkpoint letter, the `check.sh` summary lines, and the card's own "done when" evidence for this checkpoint.
4. **Decisions:** for every lasting decision made since the last checkpoint (a rule, a default, a ruling from the owner), use the `log-append` skill to append a row in the branch's range. Choices that aren't lasting decisions go in the report's item 6 instead.
5. **Rerun** the full `scripts/check.sh` (no flags) after the report and the log rows, until it's green. The docs tests check both, and the report and log changed files after step 1, so only this last full run leaves the Stop hook's marker current. Update the report's check summary if the lines changed.
6. **Stop.** Tell the owner, briefly: what's done, anything that needs their decision, and the commands:
   ```
   git add -A && git status --short
   git commit -m "<NNN>: <the card's suggested message for this checkpoint>"
   git push -u origin <branch>     # first push; later: git push
   gh pr create --fill             # first checkpoint only
   ```
   Then wait. Don't start the next checkpoint until the owner says so.
