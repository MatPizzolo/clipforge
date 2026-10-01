---
name: log-append
description: Append decision rows to docs/studio/10-decision-log.md safely — re-read it, take the next free number in the branch's range, add rows only, and mark a superseded row's status. Use whenever a lasting decision or owner ruling needs recording.
---

Record decisions in `docs/studio/10-decision-log.md` without ever rewriting it (the 2026-09-29 failure).

1. **Range:** find the branch's log range in `scripts/scopes.toml` (`log = [low, high]` for the prefix of `git branch --show-current`; the card's "Decision-log range" line says the same).
2. **Re-read the file now**, right before editing: other sessions append to it too.
3. **Number:** the next free number is one more than the highest row number already in your range (or `low` if none). Never reuse a number, and never take one outside your range. If the range is full, stop and ask the owner.
4. **Append with Edit, never Write.** Insert the new rows after the last row of the table the decision belongs to (Platform and architecture / Distribution and posting / Accounts and content / Money / Process); when unsure, use Process. The scope guard denies a Write over this file.
5. **Row format:** `| N | YYYY-MM-DD | <the decision, one self-contained sentence or two> | current | <where it's recorded: ADR, card, file> |`. Name the files and settings. A reader must understand the row without the chat.
6. **Superseding:** when a new row replaces an old one, change **only** the old row's Status cell to `superseded by N`, where N is your new row, and change nothing else in it. `scripts/check_scope.py` allows exactly that edit, and only for a row N added on the same branch.
7. **Don't** reformat, reorder, fix typos in, or delete existing rows, and don't touch the Open table unless you are the coordinator (`coord/`).
8. Run `scripts/check.sh --docs --scope`: unique numbers, supersede targets and the append-only rule are all checked.
