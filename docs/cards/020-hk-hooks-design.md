# Card 020: HK — the hook library, spec and plan

Status: proposed
Stream: HK · Branch: `hk/design` · Worktree: `../clipForge-hk` (created with `scripts/worktree.sh hk/design`)
Decision-log range: #550–#579 (append only, in this range; new prefix, log #141)
Model: most capable (design and plan, no code)
Depends on: nothing to start. The build (a later card) waits for S1's rollout (card 010 done) and lands its migration after S2a's 0002 (card 014). Section 6 of the spec (story hooks) reads the X4 report once PR #33 (card 012) merges; until then, write it from 04's S6 list and mark it "to confirm against X4". Runs alongside 010 (rollout, don't touch production), 017, 018, 019, 021
Cost cap: $0 (documents only; no Modal, Neon or API spend)

## Context
Hooks are the lever the owner most wants to improve (ADR-50). The design outline is the S3 dashboard spec §3.6 and §8.5: each account has a hook library (patterns shareable to its blueprint) in its own tables, **outside** ADR-42's versioned setup; patterns are immutable versions; every item stamps `hook_pattern_id@version` and the rotation weights in force; producers write 2–3 variants per item from approved patterns and ship the best-ranked one; while the account runs a setup experiment its rotation weights are frozen; hook rotation is never an S3c experiment. 04 sequences HK after S1's rollout and before S6, so the story producer uses patterns from its first video.

What the spec must settle beyond the outline:
- **Clip hooks today** are the hook title card: highlights' `title`, written into the Timeline's ASS overlay by the captions stage with its key word from `prompts/keywords_v2.md` (ADR-20, #340). Variants therefore go into the captions call (a `keywords_v3` or `hooks_v1` prompt, one Haiku call, about $0.0025 per item, logged as cost, rule 7). That bumps `captions.STAGE_VERSION` and the prompt names in `producer_version` (ADR-43), which opens ADR-49's 5-item review window on every clips account: **bundle it with other stage or prompt bumps** (#439).
- **Story hooks (S6)** are the script's first line plus, per X4's finding, an animated hook frame that works (`docs/studio/spikes/x4-visuals-music.md`, after PR #33). The spec says how clip and story hooks share one library and one interface (pattern kinds or beats, the variants call per producer, about $0.0035 per story item).
- **Fix while there:** the captions code and tests still say `keywords_v1` in comments and docstrings while the code loads `keywords_v2` (STATUS follow-up): `src/clipforge/stages/captions.py` (module docstring, line ~193), `src/clipforge/models.py` (~720), `tests/stages/test_captions.py` (~119). The plan includes that fix in its first code task.
- **Migrations land one at a time, in landing order** (S3 dashboard spec §8.7): S2a's 0002 first, then this card's, then S3c's. The plan's migration number is **assigned at landing** (the next after the head on `main`), and it moves `EXPECTED_HEAD` in `db/doctor.py` in the same change. It doesn't repeat 0002's deferred items.
- The Hooks tab lives in S3c's account workspace; before S3c, a standalone `/hooks?account=` page on S3's `admin` endpoint (S3 dashboard spec §7.3, §8.5 item 7). Card 019 plans S3 and card 018 S3c in parallel: name the routes and the page so both can link them.

This card is design-and-plan only: checkpoint A covers the spec and the owner questions, checkpoint B the plan. **Production is out of bounds today:** card 010 runs the S1 rollout's live steps at 22:00 New York time. Never deploy, touch `clipforge-secrets` or run Alembic.

## Read first
1. `CLAUDE.md`, `STATUS.md`
2. `docs/DECISIONS.md`: ADR-8, 18, 20, 31, 42, 43, 48, 49, 50
3. The S3 dashboard spec: §3.6, §7.3 (the Hooks tab), §8.5 (the outline, cost and release note), §8.7; log rows #426, #436, #439
4. `docs/studio/04-roadmap.md` (HK, S6), `docs/studio/08-dashboard-and-operations.md` §2 and §2c, `docs/studio/05-proposed-adrs.md`
5. The S3c spec §2.5, §2.6, §4.1, §4.4 (experiments, and what "running" means for the freeze), and card 018
6. The S2 plan: Global Constraints, Tasks 2 (0002), 6 (the producer-version window), 15 (review: where 👍/👎 per hook would be recorded); the S2 spec §3
7. The code it changes (read only): `stages/highlights.py`, `stages/captions.py`, `stages/timeline.py`, `prompts/keywords_v2.md`, `prompts/metadata.json`, `models.py` (`ClipCandidate`, `CaptionFiles`, `ContentItem`, `JobMetadata`), `hashing.py`, `db/tables.py`, `posting/enqueue.py`
8. `docs/studio/spikes/x4-visuals-music.md` (after PR #33), `docs/studio/07` (hooks in the first 3–5 s)

## Scope
- May edit, as `scripts/scopes.toml` allows for `hk/`: the spec `docs/superpowers/specs/*studio-hooks*`, the plan `docs/superpowers/plans/*studio-hooks*`, `docs/studio/04-roadmap.md` (the HK section only), `docs/studio/05-proposed-adrs.md`, `docs/studio/08-dashboard-and-operations.md`, its own report, and log rows #550–#579.
- Must not edit: code, tests, prompts, `alembic/`, `docs/DECISIONS.md` (ADR-50 is accepted; propose any new ADR in 05), the S2, S3 and S3c specs and plans (propose their changes in the spec's last section), other cards.

## Actions
1. **Questions first** (superpowers:brainstorming, one at a time, options with a recommendation). At least:
   - the prompt: a new `keywords_v3` that also writes and ranks the title variants, or a separate `hooks_v1` call (one call is cheaper; two keep captions independent);
   - ranking the variants before any results exist: the LLM's own rank, pattern weight × LLM rank, or always the top-weight pattern;
   - the seed library per clips account (from the current title style, how many patterns, who approves them);
   - 👍/👎 per hook: on S2's review cards, only on the dashboard, or both (ADR-44's one-home rule);
   - the freeze: read "experiment running" from S3c's table, or a flag the hooks service owns until S3c exists;
   - the release bundling: ship the captions bump with the next other stage or prompt bump, or alone with its 5-item window per account.
2. **Write the spec** `docs/superpowers/specs/2026-10-0X-studio-hooks-design.md`, approved section by section:
   - contracts first (rule 2): `HookPattern`, `HookPatternVersion`, `HookStamp` (`pattern_id`, `version`, `weights`), the variants reply model with rule 5's single retry and the fallback to the plain title;
   - tables: `hook_patterns`, `hook_pattern_versions` (append-only by trigger), `hook_weights` (with `frozen_by_experiment`), `hook_ratings`, the item stamp columns on `content_items` and in `metadata.json`; the migration "next in landing order, number assigned at landing";
   - clip variants in the captions stage: cache key inputs (ADR-8: the approved pattern versions and weights in force are inputs; the stamp is output), `STAGE_VERSION`, `producer_version`, cost per item;
   - rotation (weighted pick, deterministic per item for resumability), the freeze, ranking before S7 (approval and reject rates with the 90% interval and the 10-item floor) and after S7 (3-second hold, views at 24 h, settled results only);
   - **one library for clip and story hooks:** pattern kinds (title card, first line, animated hook frame per X4), one `HookWriter` protocol per producer, S6's use of it;
   - surfaces: the admin routes (§8.5 item 7), the Hooks tab and the interim `/hooks?account=` page, the digest line for weak patterns (never instant, ADR-45);
   - tests and safety, rollback, cost (about $0.0025 per clip item, $0.0035 per story item, about $3 a month at 03's scenario 2);
   - the last section: proposed changes to 04, 08, 05, the S2, S3 and S3c specs.
   Stop for the owner's review (checkpoint A).
3. **After approval, write the plan** `docs/superpowers/plans/2026-10-0X-studio-hooks.md` in the S2 plan's structure: Global Constraints (the landing order, migration number at landing, `EXPECTED_HEAD`, rule 4 for the new prompt version with `metadata.json`, no Modal outside `app.py`), Review Focus, a File map, tasks with failing tests first and exact signatures (the first code task includes the `keywords_v1` comment fix), deployable checkpoints with owner steps (migrate, `scripts/deploy.sh --dry-run`, deploy, the first stamped clip) and the rollback, and a coverage table against 04's HK list and §8.5's eight items.
4. Apply the HK-only changes to 04's HK section and 08 (the Hooks tab's home), and write a draft ADR in 05 only if the design changes ADR-50.
5. `scripts/check.sh` green (`--docs --scope` at A, the full gate at B), the report, log rows in range for the owner's rulings, and stop at checkpoint B.

## Checkpoints
- A: actions 1–2. Suggested commit: `020: hk: hook library design spec`
- B: actions 3–5. Suggested commit: `020: hk: implementation plan`

## Done when
- The owner approved the spec at A and the plan at B.
- The spec covers every item of 04's HK list and §8.5, says how clip and story hooks share the library, and states the cost per item.
- The plan's first code task fixes the `keywords_v1` comments, and its migration is numbered at landing.
- `scripts/check.sh` is green (paste its summary lines).

## Owner steps
- Before: `scripts/worktree.sh hk/design`, open a session in `../clipForge-hk`, paste `Run card docs/cards/020-hk-hooks-design.md`.
- During: answer the questions in action 1.
- At each checkpoint: commit, push (`git push -u origin hk/design` the first time), keep one PR open until B, squash-merge after B.
- After: the coordinator writes the build card (it widens `hk/` in `scripts/scopes.toml`); it starts after card 010 is done and lands its migration after card 014's.

## Hand-off
Write `docs/reports/020-hk-<YYYY-MM-DD>.md` from `docs/templates/handoff-report.md` at each checkpoint. Don't commit: the owner does.
