# Card 018: S3c — account workspaces, spec revision and implementation plan

Status: done 2026-10-05 (report: docs/reports/018-s3c-2026-10-02.md; PR #44)
Stream: S3c · Branch: `s3c/plan` · Worktree: `../clipForge-s3c` (created with `scripts/worktree.sh s3c/plan`)
Decision-log range: #250–#299 (append only; #250–#253 are taken, so #254–#299 are free: re-read the log)
Model: most capable (spec revision and plan, no code)
Depends on: nothing to start. The build (later cards) waits for S1's rollout (card 010 done) and S3's `admin` endpoint (the first S3 build card, from card 019's plan). Runs alongside 010 (rollout, don't touch production), 017, 019, 020, 021
Cost cap: $0 (documents only; no Modal, Neon or API spend)

## Context
S3c gives every category, blueprint and account a versioned setup, with notes and experiments, edited from the dashboard (ADR-42). Card 003 wrote and the owner accepted the design (`docs/superpowers/specs/2026-09-30-studio-s3-workspaces-design.md`). Since then:
- **ADR-48 (autopilot)** moves the review tier and the budget out of the versioned setup into S2's `autopilot` table (one writer, `accounts/autopilot.py`, built by card 014). **ADR-50 (hooks)** keeps the hook library outside the setup, in its own tables (card 020). The S3 dashboard spec §10.3 lists the amendments to the S3c spec; they are not applied yet.
- **Migrations land one at a time, in landing order** (S3 dashboard spec §8.7, log #438): S2a's 0002 first (card 014; it carries the deferred `jobs.error`, `post_events.actor` with its backfill from `data.actor`, and the pause actor on `posting_state`), then the hooks migration, then S3c's. **The S3c spec's §5.3 still calls its migration "0002" and adds `post_events.actor` itself: the revision renumbers it ("the next in landing order, assigned at landing") and drops the items S2a's migration already carries.**
- S2's plan (`docs/superpowers/plans/2026-10-02-studio-s2.md`) enforces the format-change window from `account_versions.format_changed`, closed until S3c's table exists (card 014, Task 6). S3c must provide exactly what that task reads.
- S3's dashboard v1 (card 019) builds the `admin` endpoint, Accounts → Compare and a minimal `/accounts/<id>` read view; S3c adds the Map, the workspaces and their tabs on top (S3 dashboard spec §7.3, §7.4).

This card is design-and-plan only: checkpoint A is the revised spec (owner review), checkpoint B the plan (owner review). **Production is out of bounds today:** card 010 runs the S1 rollout's live steps at 22:00 New York time. Never deploy, touch `clipforge-secrets` or run Alembic.

## Read first
1. `CLAUDE.md`, `STATUS.md`
2. The S3c spec (all of it), and `docs/studio/04-roadmap.md` S3c (the three build items and the 2026-10-01 amendment line)
3. The S3 dashboard spec `docs/superpowers/specs/2026-10-01-studio-s3-dashboard-design.md`: §2 (autopilot), §3.6, §7.3, §7.4, §8.4, §8.5, §8.7, §10.3
4. `docs/DECISIONS.md`: ADR-14, 26, 29, 41, 42, 43, 44, 45, 48, 49, 50
5. The S2 plan: Global Constraints, File map, Tasks 2, 3, 6 (what 0002 and the autopilot service build, and the format window it reads); the S2 spec §3
6. `docs/studio/06-session-prompts.md` (the S3c card), `docs/studio/08-dashboard-and-operations.md` §2, §2b, §2c
7. The S1 code it builds on (read only): `models.py` (`Account`, `Blueprint`, `ContentItem`), `db/tables.py`, `alembic/versions/0001*`, `accounts/`, `posting/actions.py`, `hashing.py`, `service.py` (`create_job`), `stages/highlights.py`, `stages/captions.py`
8. Log rows #250–#253, #420–#439, #440–#461, #138–#140 in `docs/studio/10-decision-log.md`
9. The S2 plan's structure (`docs/superpowers/plans/2026-10-02-studio-s2.md`), as the model for this plan

## Scope
- May edit, as `scripts/scopes.toml` allows for `s3c/`: the S3c spec (`docs/superpowers/specs/*s3-workspaces*`), the plan (`docs/superpowers/plans/*s3c*`), `docs/studio/04-roadmap.md` (the S3c section), `docs/studio/05-proposed-adrs.md`, `docs/studio/06-session-prompts.md` (the S3c card), `docs/studio/08-dashboard-and-operations.md`, its own report, and log rows #254–#299.
- Must not edit: code, tests, `alembic/`, `docs/DECISIONS.md` (propose ADR text in the spec's last section; the coordinator writes it), the S2 and S3 dashboard specs and plans, other cards.

## Actions
1. **Apply the amendments to the S3c spec** (a dated "Revised 2026-10-0X (card 018)" note at the top, and each change in place):
   - S3 dashboard spec §10.3, item by item: §3.5 (the review tier leaves "rules", the budget leaves "identity", both live in `autopilot`; `format_changed` stays), §5.3 (the actor check allows `system:<component>`), §2.2 (Compare first in S3, the Map in S3c), §2.5 (Overview, Autopilot, Style, Hooks and Activity tabs), §2.7 (autopilot changes as markers on the experiment page), §4.1 (hook metrics on the Hooks tab, not in the metric registry).
   - ADR-42 as refined by ADR-48 and ADR-50: remove the review tier and budget from the field registry and the change classes; the hook stamp sits next to `setup_version` on items, never inside it; the hook rotation weights freeze while an experiment runs (card 020 owns the freeze; S3c says where it reads "an experiment is running").
   - §5.3 and the roadmap: the migration is "the next in landing order (after S2a's 0002 and the hooks migration), number assigned at landing"; drop `post_events.actor` and its backfill (S2a's 0002 carries them); keep the `*_versions` append-only triggers.
   - §7's open items: answer what S1's merged code now settles (card 002's actor lands in `post_events.data.actor`, then S2a's column), and carry the rest to the owner questions.
   - Write the changes this implies for 04, 06 and 08 into the spec's last section, and apply the S3c-only ones (04's S3c section, 06's S3c card) directly.
2. **Ask the open owner questions** (superpowers:brainstorming, one at a time, options with a recommendation). At least:
   - the transcribe key when the language hint is first wired for sources cached under "auto" (§3.1): re-transcribe, or keep "auto" for existing sources;
   - `PATCH /accounts/{id}`: keep S1's request shape and write a version (recommended), or a new versioned route only;
   - the drafted category playbooks: written by the plan from 01, 07 and 09 for the owner to edit, or left empty;
   - the build split: three cards matching S3c-1, S3c-2, S3c-3, or S3c-1 split into data (migration, resolver, import/verify) and pages;
   - whether S3c-1 can start before S3's Compare page lands (its routes need only the `admin` endpoint);
   - who writes the digest's "experiments need a decision" line (S2c's digest reading S3c's derived count) and which card lands it.
3. **Checkpoint A: stop** for the owner's review of the revised spec.
4. **Write the plan** `docs/superpowers/plans/2026-10-0X-studio-s3c.md` in the S2 plan's structure: Global Constraints (the landing-order rule with its migration number assigned at landing, `EXPECTED_HEAD` moved in the same change, `SETUP_SOURCE`, one writer per column group, no Modal outside `app.py`), Review Focus, a File map, then tasks grouped into deployable parts (S3c-1, S3c-2, S3c-3 or the split the owner chose). Each task: the failing tests first (file and test names), exact signatures (`accounts/setup.py` resolver, the versions service, `POST /setup/preview`, `clipforge setup import|verify`), the implementation sketch, the checks. Each part ends with a deployable checkpoint: owner steps (migrate, `scripts/deploy.sh --dry-run`, deploy, verify), the rollback (a revert deploy; the migration is expand-only) and what the owner sees.
5. **Coverage table** at the end of the plan: every item of 04's S3c list and every §10.3 amendment, mapped to its task and test.
6. `scripts/check.sh` green (`--docs --scope` at A, the full gate at B), the report, log rows in range for the owner's rulings, and stop at checkpoint B.

## Checkpoints
- A: actions 1–3. Suggested commit: `018: s3c: spec revised for ADR-48, ADR-50 and the migration order`
- B: actions 4–6. Suggested commit: `018: s3c: implementation plan`

## Done when
- The owner approved the revised spec at A and the plan at B.
- The spec no longer puts the review tier, the budget or hook patterns in the versioned setup, and no longer numbers its migration or adds `post_events.actor`.
- The plan's coverage table maps every item of 04's S3c list to a task with its tests, and names which parts deploy alone.
- `scripts/check.sh` is green (paste its summary lines).

## Owner steps
- Before: `scripts/worktree.sh s3c/plan`, open a session in `../clipForge-s3c`, paste `Run card docs/cards/018-s3c-plan.md`.
- During: answer the questions in action 2.
- At each checkpoint: commit, push (`git push -u origin s3c/plan` the first time), keep one PR open until B (`gh pr create --fill` at A), squash-merge after B.
- After: the coordinator writes the build cards from the plan; they start after card 010 is done and S3's `admin` endpoint is deployed.

## Hand-off
Write `docs/reports/018-s3c-<YYYY-MM-DD>.md` from `docs/templates/handoff-report.md` at each checkpoint. Don't commit: the owner does.
