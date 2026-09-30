# Card 003: S3c — revise the workspaces design (design only)

Status: proposed (after card 001 is merged; can run alongside 002 and 005)
Stream: S3c · Branch: `s3c/design` · Worktree: `../clipForge-s3c`
Decision-log range: #250–#299
Model: most capable
Depends on: card 001 merged
Cost cap: $0 (no code, no Modal or Vercel spend, no deploys)

## Context
The spec `docs/superpowers/specs/2026-09-30-studio-s3-workspaces-design.md` (sections 1–6 approved in chat) and the ADR-42 draft in `docs/studio/05` are waiting for the owner's review. Since they were written:
- ADR-43 (derived `producer_version`), ADR-44 (one home per task), ADR-45 (notification budget) and ADR-46 (daily reconcile) were accepted;
- `docs/studio/08` §2 gained a "Telegram's role" column and §2b (surfaces, sync, notifications, deep links, identity).

The D-items come from the coordinator's addendum. Their status is in `STATUS.md`.

## Read first
1. `CLAUDE.md`, `STATUS.md`
2. The spec and ADR-42 draft named above, `docs/studio/08` §2 and §2b, `docs/DECISIONS.md` ADR-42–46
3. The S1 spec (for the tables S3c builds on): `docs/superpowers/specs/2026-09-29-studio-s1-design.md`

## Scope
- May edit: as `scripts/scopes.toml` allows for `s3c/`.
- Must not edit: code, `web/`, `docs/studio/08` §2b (only the S3c rows of the §2 table).

## Actions
1. **D1:** record in the spec that the setup is identified by `(account_id, account_version)` with pinned parents (#88). There is no separate setup id.
2. **D3:** add `post_events.actor` (text: `telegram:<id>`, `web:<login>` or `session:<name>`) to migration 0002. It is written by `posting/actions.py` (card 002, A4).
3. **D4:** one dry run is used by both "save version" and "start experiment". Either a standalone `POST /setup/preview`, or show that `GET …/diff` plus the estimate already is that single path. It returns the diff, which stages re-run, the affected items and the estimated cost.
4. **D7:** state that keep and revert are decided only on the experiment page.
5. **D10:** use the deep-link formats in 08 §2b, and add any page the spec needs.
6. **D8 and D9 belong to S3.** Add them to 06's S3 card:
   - the pre-S2 Review page is a queue manager (skip, reject, reorder, posted correction through `posting/actions.py`);
   - `admin` is a second `@modal.asgi_app(requires_proxy_auth=True)` that reuses `create_app` with an admin router and its own `ADMIN_API_TOKEN`.
7. Update the spec's status line and the ADR-42 draft. Reference ADR-43–46; don't redefine them.
8. **STOP** for the owner's review. No plan until card 002's final review is done.

## Done when
- The spec's status line lists each section and D-item. No placeholders.
- `scripts/check.sh --docs` is green, and the scope check passes.

## Owner steps
- Before: `scripts/worktree.sh s3c/design`, then paste `Run card docs/cards/003-s3c-revision.md`.
- After: review the spec, then accept ADR-42 into `docs/DECISIONS.md` in a `coord/` PR, or ask the coordinator to write that PR's card.

## Hand-off
The report goes in `docs/reports/003-s3c-<date>.md`. Don't commit.
