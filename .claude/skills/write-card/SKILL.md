---
name: write-card
description: Coordinator only. Build a new work card in docs/cards/ from docs/templates/card.md and the matching prompt and action card in docs/studio/06-session-prompts.md; pick the number, branch and log range; add it to docs/cards/README.md and STATUS.md. Use when the owner asks for the next card or a card for a workstream.
argument-hint: <stream or workstream, e.g. "S2 publishing">
---

Write the card for: $ARGUMENTS. You are the coordinator, on a `coord/<topic>` branch (the scope guard allows only `coord/` paths on `main`).

1. **Sources:** `STATUS.md` (where the workstream stands, and the next-cards table), the workstream's prompt and action card in `docs/studio/06-session-prompts.md`, `docs/studio/04-roadmap.md` (exit criteria, dependencies), the newest report in `docs/reports/` for that stream, the current plan or spec in `docs/superpowers/`, and any Open rows in `docs/studio/10` it depends on.
2. **Number:** the next unused three-digit number in `docs/cards/` (never reuse one, even for a superseded card).
3. **Branch and range:** branch `<prefix>/<topic>`. The prefix and log range must already exist in `scripts/scopes.toml`. If the stream is new, add its `[prefix."<p>/"]` entry (stream, a free log range, allow globs) in the same `coord/` change, so CI's scope check and the worktree script know it.
4. **Fill `docs/templates/card.md` completely:**
   - Status `proposed`; Model; Depends on; Cost cap (in dollars, with what it's for);
   - Context: the starting state, decisions since the plan, and what other sessions are doing;
   - Read first: numbered, in order;
   - Scope: may edit / must not edit, matching `scopes.toml` exactly;
   - Actions: numbered, concrete, each one verifiable;
   - Checkpoints: which actions each covers, with a suggested commit message;
   - Done when: runnable checks, starting with `scripts/check.sh` green;
   - Owner steps: before, at checkpoints and after, as exact commands;
   - Hand-off.
   Keep the action-card detail from 06: owner steps, done-when and cost cap are required.
5. **Register it:** add a row to the table in `docs/cards/README.md`, and to the next-cards table in `STATUS.md`, with what it can start after and what it runs alongside.
6. Run `scripts/check.sh --docs --scope` (card headers, links and scope are checked), then give the owner the commit and PR commands for the `coord/` branch.
