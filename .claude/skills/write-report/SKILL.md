---
name: write-report
description: Write or update a card's hand-off report in docs/reports/ from docs/templates/handoff-report.md, with the current git diff --stat and changed-file list inlined. Use at every checkpoint, at a stop card, and at the end of a card.
---

Write the report for the card this branch runs.

1. **File:** `docs/reports/NNN-<stream>-<YYYY-MM-DD>.md`, where NNN is the card number, `<stream>` is the branch prefix (as in `scripts/scopes.toml`) and the date is today. Update today's report if it exists; never edit another session's report.
2. **Gather** (read-only):
   - `git diff --stat origin/main` and `git status --short`: every changed, added and untracked file;
   - the latest `scripts/check.sh` summary lines (rerun it if anything changed since);
   - the card's numbered actions and its "done when" list.
3. **Fill** every section of `docs/templates/handoff-report.md`, in order, with no section left out:
   - item 4 lists **every** changed file from step 2, each with one line on what changed (group by code / tests / docs / config);
   - item 6 lists every choice not written down anywhere else, or says "none";
   - item 7 pastes the check summary and the card's own evidence (commands and outputs), and says what was skipped and why;
   - item 10 gives the spend, with the command used to measure it, against the cap;
   - item 11 gives the exact owner commands, including the suggested commit message;
   - item 13 gives the status of every numbered card action.
4. Put the inlined `git diff --stat` block at the end of item 4.
5. Be factual: report failures with their output. Say "not verified" when something wasn't.
6. **Last step:** rerun the full `scripts/check.sh` (no flags) afterwards, until it's green. Links in the report must resolve, and only a full green run after the last file change keeps the Stop hook's marker current.
