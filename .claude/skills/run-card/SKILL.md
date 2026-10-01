---
name: run-card
description: Start and run a work card. Use when the owner says "Run card docs/cards/NNN-….md" (or names a card to run). Reads the card and its read-first list, confirms the branch, restates scope, actions, checkpoints and cost cap in five lines, then works, stopping at each checkpoint.
argument-hint: docs/cards/NNN-<stream>-<topic>.md
---

Run the card at `$ARGUMENTS` (a path under `docs/cards/`; if it's only a number, find `docs/cards/<number>-*.md`).

1. **Read** the card in full, then every file in its "Read first" list, in order. Also read the newest report for this card in `docs/reports/` if one exists: that's where a previous session stopped.
2. **Confirm the branch.** `git branch --show-current` must equal the card's `Branch:` line, and the worktree must be the card's (`../clipForge-<stream>`). If not, stop and tell the owner the exact command: `scripts/worktree.sh <branch>`, then open a session there. Don't work on `main`.
3. **Restate in five lines**, before any edit:
   1. the goal (one sentence);
   2. the scope (may edit / must not edit; it matches `scripts/scopes.toml`);
   3. the actions, by number;
   4. the checkpoints and what each one covers;
   5. the cost cap, and the decision-log range.
4. **Work** through the actions in order. Before a non-trivial change, say which files you'll touch. Stay in scope: the scope guard denies out-of-scope edits, and `scripts/check_scope.py` fails them in CI. If the card needs a file outside its scope, stop and ask the owner.
5. **At each checkpoint**, use the `checkpoint` skill: `scripts/check.sh` green, the report written, log rows appended in range, then **stop** with the suggested commit message. Wait for the owner before starting the next checkpoint.
6. **Never** commit, push, tag, merge, deploy, stop the Modal app, or change secrets: give the owner the exact command instead. Spend nothing beyond the cost cap: stop and ask first.
7. If the card is wrong or out of date (a file moved, a decision changed), say so, propose the smallest fix, and wait. Don't silently deviate: every deviation goes in the report's item 8.
