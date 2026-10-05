# Studio HK: the hook library, implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build ADR-50's hook library in three deployable parts:
- **HK-1:** data and library. Every new clip item records its hook pattern; clip output doesn't change (the `HOOK_VARIANTS` flag is off).
- **HK-2:** variants. Clips ship a title card rewritten in the drawn pattern; patterns are ranked; one item can be re-rendered.
- **HK-3:** the interim `/hooks?account=` page.

**Architecture:**
- `service.create_job` freezes the account's rotation (`HookRotation`) on the job. The clip step draws one pattern from it with a pure, seeded pick and passes it to captions as an explicit cache-key input; the stamp's weights are attached at enqueue, outside the cache.
- One `keywords_v3` Haiku call writes the caption key words, 2–3 lines in the drawn pattern, the best line and its key word. `HOOK_VARIANTS=false` keeps today's stage version, prompt, cache keys and `producer_version` byte for byte.
- The `hooks/` package (Modal-free) is the one writer of the hook tables: `library.py` (patterns, versions, weights, freezes, events; `SqlHookFreezer`), `ratings.py`, `rerender.py`; `rotation.py`, `variants.py` and `stats.py` are pure.

**Tech Stack:** Python 3.12 (`uv`), pydantic v2, SQLAlchemy 2 Core + psycopg 3, Alembic, FastAPI, argparse CLI, Modal (`app.py` only), pytest with the local Postgres fixture (`tests/dbfixture.py`); Next.js, TanStack Query, vitest and Playwright in `web/` for HK-3.

**Spec:** [docs/superpowers/specs/2026-10-02-studio-hooks-design.md](../specs/2026-10-02-studio-hooks-design.md) (approved by the owner, card 020). Read it with this plan: section numbers below (§N) are the spec's.

## Global Constraints

- **Workflow:**
  - Work only from the HK build card. **Sessions never commit, push, deploy or stop the app.**
  - Each task's last step is "check and record" (`scripts/check.sh` green, the task noted in the card's report). The owner commits at the card's checkpoints.
  - **Dependencies are deployed cards, not merges (#144).** Each part starts only when the cards it needs are deployed with their owner steps done; where a card isn't deployed yet, the part uses the named fallback instead of waiting:

    | Part | Needs deployed | Fallback when it isn't |
    |---|---|---|
    | HK-1 | card 010 (S1 rollout), card 014 (S2a: migration 0002, `system:` actors, `ACTOR_CHECK`, `/admin` style) | none: HK-1 waits for both |
    | HK-2 | HK-1 | — |
    | | card 015 (S2b: `posts.state`, `publishing:inflight:<ref>`) | re-render's refusal checks `posted_at` only and says so in the code comment; the in-flight checks are added with a test when 015 is deployed |
    | | card 016 (S2c: the digest's `DigestProvider` tuple) | no digest lines until 016; the providers ship with their tests, unregistered |
    | | card 022 (S3-1: `cli_router`, the `admin` endpoint) | the interim mount: the CLI's routes in `create_app` next to S2's `/admin/*` on `web`, the dashboard-only routes on `web` behind the bearer token; S3-1 moves them |
    | | card 023 (S3-2: the needs registry and `needs_providers`) | `HookWeakProvider` ships with its tests, unregistered, until 023 |
    | | card 024 (S3-3: Review's re-render button) | the route works from the API and CLI tests; the button stays disabled until 024 |
    | HK-3 | HK-2 and card 022 (S3-1's `admin` client in `web/`) | none: HK-3 waits; if S3c's workspace is deployed first, HK-3 is skipped (S3c's Hooks tab) |
- **Python:**
  - `uv` only, never pip. **No new dependencies.**
  - Stage modules stay free of database and Modal code. **Only `src/clipforge/app.py` imports `modal`.**
- **Contracts:** change `models.py` first (CLAUDE.md rule 2). Every new field on an existing contract is **optional with a default**, so cached stage results, stored jobs and `metadata.json` files written before HK still validate.
- **Prompts (rule 4):** `prompts/keywords_v3.md` is a new file; `keywords_v2.md` is never edited. Record `keywords_v3` in `prompts/metadata.json` (`released`, `model_default: claude-haiku-4-5`, `notes`).
- **The flag:** `HOOK_VARIANTS` (`Settings.hook_variants`, default `False`).
  - Off: `captions.stage_version(settings) == "3"`, `captions.keywords_prompt(settings) == "keywords_v2"`, the captions cache key and `producer_version` byte-identical to today's (pinned tests).
  - On: `"4"` and `keywords_v3`.
- **Migrations (#438, #141, coordinator 2026-10-02):**
  - Landing order: S2a's 0002 first, then whichever of the hooks, S3 and S3c migrations lands next, **one at a time**.
  - **The number is assigned at landing:** the next after the head on `main`. The file is written here as `alembic/versions/NNNN_hooks.py`; rename it, set `revision` and `down_revision`, and move `EXPECTED_HEAD` in `src/clipforge/db/doctor.py` in the same change. If another migration lands first, rebase and renumber.
  - Expand-only. `0001` is frozen. It doesn't repeat 0002's deferred items (`jobs.error`, `post_events.actor`, the pause actor); if 0002 has somehow not landed, stop and ask the coordinator.
  - Migrations run only against `DATABASE_URL_UNPOOLED`, by the owner.
- **One writer per table** (ADR-14, ADR-41):

  | Writer | Writes |
  |---|---|
  | `hooks/library.py` | `hook_patterns`, `hook_pattern_versions`, `hook_weights`, `hook_freezes`, `hook_events` (kinds `seeded`, `created`, `version`, `approved`, `retired`, `shared`, `weight`, `frozen`, `released`) |
  | `hooks/ratings.py` | `hook_ratings`, `hook_events` (kind `rated`) |
  | `hooks/rerender.py` | `hook_events` (kind `rerendered`), the `rerender:<item>` Dict claim |
  | `posting/actions.supersede` | the old item's verdict, its `rejected` `post_events` row (reason `superseded:<new id>`) and `content_items.superseded_by` |
  | `posting/enqueue.py` → `db/posting.py` | `content_items.hook_*` at insert (the stamp) |

- **Actors:** S2's format (`telegram:`, `web:`, `session:`, `cli:`, `system:`), checked by `posting.actions` `_checked` and S2's `ACTOR_CHECK`. Seeds use `system:migration`; freezes use `system:experiment`.
- **Routes (spec §7.1; #610, #146):** every path is under `/admin`, with the actor from `X-Clipforge-Actor`.
  - The routes the CLI also uses (`clipforge hooks …`: library, seed, stats) go into S3's `cli_router(ctx, write_actor)` when it is on `main` (S3 plan Task 1); until S3-5b it is mounted on `web` and `admin`. If `cli_router` isn't on `main` yet, add them in `create_app` next to S2's `/admin/*` routes with `Depends(require_token)`, and S3-1 moves them into `cli_router`.
  - The dashboard-only routes (`PUT /admin/items/{id}/hook-rating`, S3's `POST /admin/review/{item}/rerender`, #619) go on `admin` only; before S3-1 they sit on `web` behind the bearer token.
  - Regenerate `web/openapi.json` and `web/lib/api` after route changes (`npm --prefix web run gen`).
- **Extension points, never edits (#142, #147):** the `hook_weak` needs provider registers through `runtime.build_deps(needs_providers=…)` and the digest lines through the digest's `DigestProvider` tuple. The hooks build doesn't edit `needs/` or `dispatch/digest.py`; if either isn't on `main`, leave the provider in `hooks/` and tell the coordinator.
- **One home for `HookFreezer` (coordinator, 2026-10-05):** `src/clipforge/hooks/freezer.py`, holding the `HookFreezer` Protocol (`freeze(self, conn: Connection, account_id: str, experiment_id: int) -> None`, `release(...)` alike) and `NoHookFreezer` (both methods do nothing). Whichever of HK-1 and S3c-3 lands first creates the file with exactly this content; the other imports it. `SqlHookFreezer` lives in `hooks/library.py` and implements it.

  The content, copied verbatim from card 018's S3c plan, Task 17 (create the file only if S3c-3 hasn't already; if it exists, import it and change nothing):

  ```python
  # src/clipforge/hooks/freezer.py
  """The hook-weight freeze (ADR-50; S3c spec §4.4). S3c's experiment start, stop and decide call it
  inside their transaction; the hooks build implements it. One home, shared by S3c-3 and HK-1."""

  from __future__ import annotations

  from typing import Protocol

  from sqlalchemy import Connection


  class HookFreezer(Protocol):
      def freeze(self, conn: Connection, account_id: str, experiment_id: int) -> None: ...
      def release(self, conn: Connection, account_id: str, experiment_id: int) -> None: ...


  class NoHookFreezer:
      """Until the hooks build deploys: nothing to freeze."""

      def freeze(self, conn: Connection, account_id: str, experiment_id: int) -> None:
          return None

      def release(self, conn: Connection, account_id: str, experiment_id: int) -> None:
          return None
  ```
- **Security (rule 8):** every LLM line and every pattern field reaches the ASS file only through `captions.title_words()`. Field lengths are capped in `HookPatternData`. No secrets in stamps or logs.
- **Cost (rule 7):** the captions call records its `StageCost` as today; re-render records its costs on the job.
- **Tests:** DB tests use the `db` fixture and **fail, never skip**, without Postgres. The LLM is mocked (`tests/stages/helpers.py`'s fake client). Fast tests only.
- **Account ids in tests:** `realtalk-clips-en`, `founder-tapes-en`, `hombre-en-construccion-es`.

## Review Focus

The five conditions the spec implies but no task's main tests exercise, most likely first. Each has its pinning test in the owning task.
1. **A pattern edited (v+1) while a job is running:** the job froze v1 at create. The owner expects the item to ship and stamp **v1**, not the newer version. *Pinned in Task 9* (`test_stamp_uses_the_version_frozen_on_the_job`).
2. **A job created before HK, resumed after HK-2 deploys with the flag on** (`JobInput.hooks` is `None`): the owner expects the clip to finish with today's title through `keywords_v3`'s control mode and no stamp, not a crash. *Pinned in Task 9* (`test_resume_of_a_pre_hk_job_runs_control_mode`).
3. **An LLM line that is all ASS braces or punctuation** (`{\\c&H0000FF&}`, `!!!`): cleaning leaves it empty. The owner expects the line rejected and the retry asked, never an empty title card. *Pinned in Task 8* (`test_line_empty_after_cleaning_is_invalid`).
4. **A double tap on re-render** (two requests within a second): the owner expects one new item, not two. *Pinned in Task 11* (`test_second_rerender_request_is_refused_while_the_first_runs`).
5. **Every pattern of an account retired or at weight 0:** the owner expects clips to keep shipping today's title, and the Hooks page to say "nothing rotates", not an error. *Pinned in Task 3* (`test_empty_rotation_picks_none`) and *Task 6* (`test_library_reports_empty_rotation`).

## File map

| Path | New/changed | Responsibility |
|---|---|---|
| `src/clipforge/models.py` | changed | hook contracts (§1); optional fields on `JobInput`, `CaptionFiles`, `RenderedClip`, `PackagedClip`, `ContentItem`, `KeywordsReply`; the `keywords_v1` docstring fix |
| `src/clipforge/config.py` | changed | `hook_variants: bool = False` |
| `alembic/versions/NNNN_hooks.py` | new | the hooks migration (§3) |
| `src/clipforge/db/tables.py` | changed | the six tables and five `content_items` columns |
| `src/clipforge/db/doctor.py` | changed | `EXPECTED_HEAD` |
| `src/clipforge/db/hooks.py` | new | SQL behind `hooks/library.py`, `ratings.py`, `rerender.py` and `stats.py`'s reads |
| `src/clipforge/db/posting.py` | changed | `_item_row` writes the stamp columns; reads `superseded_by` |
| `src/clipforge/hooks/__init__.py`, `rotation.py`, `library.py`, `freezer.py` (created by HK-1 or S3c-3, whichever lands first), `seeds.py`, `variants.py`, `stats.py`, `ratings.py`, `needs.py`, `digest.py`, `rerender.py` | new | the hooks package |
| `src/clipforge/posting/actions.py` | changed | `supersede(posting, ref, new_ref, actor, now)` |
| `src/clipforge/stages/captions.py` | changed | `stage_version()`, `keywords_prompt()`, the pick input, `keywords_v3` parsing, `HookResult`; the `keywords_v1` comment fix |
| `src/clipforge/stages/runner.py` | changed | `producer_version` reads the two functions; `clip()` takes the pick; the keywords prompt by flag |
| `src/clipforge/stages/package.py` | changed | `PackagedClip.hook` and `title` from the result |
| `src/clipforge/pipeline/steps.py` | changed | the pick in `clip_step`; `Deps.hooks`; `rerender_step` |
| `src/clipforge/service.py` | changed | `create_job` freezes the rotation |
| `src/clipforge/posting/enqueue.py` | changed | `ClipFacts.hook`; the stamp and the shipped title on `ContentItem` |
| `src/clipforge/runtime.py` | changed | `build_deps` wires `HookLibrary`, `SqlHookFreezer`, `HookWeakProvider` and the digest providers |
| `src/clipforge/app.py` | changed | `rerender_step` function |
| `src/clipforge/api/main.py` (or S3's `api/admin/` routers) | changed | the `/admin` hooks routes (`cli_router`), the rating and rerender routes (`admin`) |
| `src/clipforge/cli.py` | changed | `clipforge hooks …` |
| `prompts/keywords_v3.md`, `prompts/metadata.json` | new, changed | the prompt (§2.3) |
| `web/app/(app)/hooks/page.tsx`, `web/lib/hooks.ts`, `web/app/api/cf/…` | new | HK-3's page and its proxy handlers |
| `tests/...` | new and changed | mirrors `src/` |
| `.env.example`, `docs/ARCHITECTURE.md`, `ROADMAP.md`, `docs/studio/04-roadmap.md` | changed | settings and docs at each checkpoint (the build card's scope) |

---

# Part HK-1: data and library (flag off; clip output unchanged)

### Task 1: Contracts, the setting, and the `keywords_v1` comment fix

**Files:**
- Modify: `src/clipforge/models.py`, `src/clipforge/config.py`, `src/clipforge/stages/captions.py` (comments only), `tests/stages/test_captions.py` (comment only)
- Test: `tests/test_models.py`, `tests/test_config.py`

**Interfaces:**
- Produces (exactly as spec §1): `HookFit`, `HookStatus`, `HookPatternData` (no `control`), `HookPattern` (with `control: bool = False`, unversioned), `HookPatternVersion`, `RotationEntry` (with `control`), `HookRotation` (with the `id` property; `frozen_by: int | None`), `HookPick` (with `control`), `HookVariants`, `HookResult` (with `drawn: bool = False`), `HookStamp` (`frozen_by: int | None`); and:
  - `JobInput.hooks: HookRotation | None = None`
  - `CaptionFiles.hook: HookResult | None = None`
  - `RenderedClip.hook: HookResult | None = None`
  - `PackagedClip.hook: HookStamp | None = None`
  - `ContentItem.hook_stamp: HookStamp | None = None`, `ContentItem.superseded_by: str | None = None`
  - `KeywordsReply.variants: list[str] | None = None`, `KeywordsReply.best: int | None = None`
  - `Settings.hook_variants: bool = False`
  - `Job.hooks_note: Literal["unavailable"] | None = None` and `Versions.hook_rotation: str | None = None` (Task 5 writes them)

- [ ] **Step 1: Fix the stale `keywords_v1` comments** (the STATUS follow-up; the code loads `keywords_v2`):
  - `src/clipforge/stages/captions.py`: the module docstring's "(prompts/keywords_v1.md, ADR-18)" becomes "(prompts/keywords_v2.md, ADR-18, ADR-20)"; `CaptionsDeps.prompt`'s comment "# prompts/keywords_v1.md" becomes "# prompts/keywords_v2.md (keywords_v3 with HOOK_VARIANTS)".
  - `src/clipforge/models.py`: `KeywordsReply`'s docstring becomes "Output of prompts/keywords_v2 (and v3): indices of the clip words to show in color."
  - `tests/stages/test_captions.py`: the section comment "# ---- key words chosen by the LLM (prompts/keywords_v1.md)" says `keywords_v2.md`.

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_models.py (add)
from clipforge.models import (CaptionFiles, ContentItem, HookPatternData, HookResult, HookRotation,
                              HookStamp, JobInput, RotationEntry)

PATTERN = HookPatternData(name="Open question", structure="A question the clip answers",
                          examples={"en": "WHY DID HE WALK AWAY?"}, fits=["clips"], max_words=8)

def test_rotation_id_is_order_independent_and_weight_sensitive() -> None:
    a = RotationEntry(pattern_id="hp_aaaaaaaa", version=1, weight=1.0, data=PATTERN)
    b = RotationEntry(pattern_id="hp_bbbbbbbb", version=2, weight=1.0, data=PATTERN)
    r1 = HookRotation(account_id="realtalk-clips-en", entries=[a, b])
    r2 = HookRotation(account_id="realtalk-clips-en", entries=[b, a])
    r3 = HookRotation(account_id="realtalk-clips-en", entries=[a, b.model_copy(update={"weight": 2.0})])
    assert r1.id == r2.id and r1.id != r3.id and len(r1.id) == 16

def test_pattern_fields_are_capped() -> None:
    with pytest.raises(ValidationError):
        HookPatternData(name="x" * 41, structure="s", fits=["clips"])
    with pytest.raises(ValidationError):
        HookPatternData(name="n", structure="s", fits=["clips"], max_words=11)

def test_old_records_still_validate() -> None:
    # written before HK: no hooks/hook/hook_stamp keys
    CaptionFiles.model_validate({"clip_id": "clip_01", "ass_path": "a", "srt_path": "s",
                                 "style": "default", "offset_s": 1.0})
    JobInput.model_validate({"source_path": "x.mp4", "permission": "own"})

def test_control_is_not_part_of_the_versioned_body() -> None:
    assert "control" not in HookPatternData.model_fields

def test_stamp_round_trips() -> None:
    result = HookResult(pattern_id="hp_aaaaaaaa", version=1, variants=["A", "B"], chosen=1, text="B")
    stamp = HookStamp(result=result, rotation_id="0123456789abcdef", weights={"hp_aaaaaaaa@1": 1.0})
    assert HookStamp.model_validate_json(stamp.model_dump_json()) == stamp
```

```python
# tests/test_config.py (add)
def test_hook_variants_default_off() -> None:
    assert Settings(_env_file=None).hook_variants is False
```

- [ ] **Step 3: Run and see them fail**

Run: `uv run pytest -q tests/test_models.py tests/test_config.py`
Expected: FAIL (ImportError on the hook contracts).

- [ ] **Step 4: Implement**

Add the contracts from spec §1 to `models.py` (a `# ---- hooks (ADR-50)` section after the posting contracts, before `ContentItem` so it can reference them). `HookRotation.id`:

```python
@property
def id(self) -> str:
    rows = sorted((e.pattern_id, e.version, e.weight) for e in self.entries)
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()[:16]
```

`HookPatternData` validates each `examples` value at most 120 characters (a `field_validator`). Add the optional fields listed under Interfaces. Add `hook_variants: bool = False` to `Settings` with the comment `# HOOK_VARIANTS: clip title variants in captions (ADR-50); off keeps keywords_v2`.

- [ ] **Step 5: Run and see them pass**

Run: `uv run pytest -q tests/test_models.py tests/test_config.py tests/stages/test_captions.py`
Expected: PASS.

- [ ] **Step 6: Check and record**

Run `scripts/check.sh --python`, then note the task.

### Task 2: The migration and the table definitions

**Files:**
- Create: `alembic/versions/NNNN_hooks.py` (the number at landing, Global Constraints)
- Modify: `src/clipforge/db/tables.py`, `src/clipforge/db/doctor.py` (`EXPECTED_HEAD`)
- Test: `tests/db/test_migrations.py`, `tests/db/test_hooks_tables.py`

**Interfaces:**
- Consumes: S2a's `ACTOR_CHECK` string (copy it from `alembic/versions/0002_s2.py` into this migration; migrations never import each other).
- Produces: `tables.hook_patterns`, `hook_pattern_versions`, `hook_weights`, `hook_freezes`, `hook_ratings`, `hook_events`; `content_items` columns `hook_pattern_id`, `hook_version`, `hook_weights`, `hook_result`, `superseded_by`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/db/test_hooks_tables.py
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from tests.dbhelpers import insert_account, insert_item   # add them if S2's helpers don't have them

def _pattern(conn, pid="hp_aaaaaaaa", account="realtalk-clips-en", blueprint=None):
    conn.execute(text("insert into hook_patterns (id, account_id, blueprint_name, status,"
                      " current_version, control, created_at, updated_at) values"
                      " (:id, :a, :b, 'approved', 1, false, now(), now())"),
                 {"id": pid, "a": account, "b": blueprint})
    conn.execute(text("insert into hook_pattern_versions (pattern_id, n, data, author, created_at)"
                      " values (:id, 1, '{}', 'system:migration', now())"), {"id": pid})

def test_versions_and_events_are_append_only(db) -> None:
    insert_account(db, "realtalk-clips-en")
    with db.begin() as conn:
        _pattern(conn)
        conn.execute(text("insert into hook_events (at, actor, kind, data) values"
                          " (now(), 'system:migration', 'seeded', '{}')"))
    for statement in ("update hook_pattern_versions set author='cli:x'",
                      "delete from hook_pattern_versions",
                      "update hook_events set kind='x'", "delete from hook_events"):
        with pytest.raises(DBAPIError):
            with db.begin() as conn:
                conn.execute(text(statement))

def test_pattern_scope_is_exactly_one(db) -> None:
    insert_account(db, "realtalk-clips-en")
    with pytest.raises(IntegrityError):
        with db.begin() as conn:
            _pattern(conn, account="realtalk-clips-en", blueprint="realtalk-clips")

def test_one_open_freeze_per_account(db) -> None:
    insert_account(db, "realtalk-clips-en")
    insert = text("insert into hook_freezes (account_id, experiment_id, rotation, frozen_at,"
                  " frozen_by) values ('realtalk-clips-en', :e, '{}', now(), 'system:experiment')")
    with db.begin() as conn:
        conn.execute(insert, {"e": 1})
    with pytest.raises(IntegrityError):
        with db.begin() as conn:
            conn.execute(insert, {"e": 2})

ITEM = "20261003-aaaaaaaa-0001:clip_01"
RATE = text("insert into hook_ratings (item_id, rating, actor, at) values (:i, :r, :a, now())")

@pytest.mark.parametrize(("rating", "actor"), [(2, "web:mat"), (1, "nobody")])
def test_rating_is_plus_or_minus_one_and_actor_checked(db, rating: int, actor: str) -> None:
    insert_account(db, "realtalk-clips-en")
    insert_item(db, ITEM, account="realtalk-clips-en")
    with pytest.raises(IntegrityError):
        with db.begin() as conn:
            conn.execute(RATE, {"i": ITEM, "r": rating, "a": actor})
    with db.begin() as conn:
        conn.execute(RATE, {"i": ITEM, "r": -1, "a": "web:mat"})          # the valid row goes in

def test_item_stamp_fk_to_the_version(db) -> None:
    insert_account(db, "realtalk-clips-en")
    insert_item(db, ITEM, account="realtalk-clips-en")
    with pytest.raises(IntegrityError):
        with db.begin() as conn:
            conn.execute(text("update content_items set hook_pattern_id = 'hp_missing',"
                              " hook_version = 1 where id = :i"), {"i": ITEM})
```

`tests/dbhelpers.py` gains `insert_account(db, account_id, blueprint="realtalk-clips")` and `insert_item(db, item_id, account)` (minimal rows with the columns S1's `0001` and S2a's `0002` require) if S2's helpers don't already provide them; a check constraint violation raises `IntegrityError` in psycopg 3.

```python
# tests/db/test_migrations.py (add)
def test_head_is_hooks(db) -> None:
    with db.begin() as conn:
        assert conn.execute(text("select version_num from alembic_version")).scalar_one() == EXPECTED_HEAD
```

The existing `test_round_trip` and `test_tables_match_the_migrations` (empty autogenerate) cover the downgrade and `tables.py` matching the migration.

- [ ] **Step 2: Run and see them fail**

Run: `uv run pytest -q tests/db/test_hooks_tables.py tests/db/test_migrations.py`
Expected: FAIL (relation "hook_patterns" does not exist).

- [ ] **Step 3: Implement the migration**

```python
# alembic/versions/NNNN_hooks.py   (revision = "NNNN", down_revision = <main's head at landing>)
# copied from 0002_s2.py (migrations never import each other); compare the two when landing
ACTOR_CHECK = (r"actor ~ '^(telegram:[0-9]{1,20}|web:[A-Za-z0-9-]{1,39}"
               r"|session:[a-z0-9][a-z0-9-]{0,39}|cli:[A-Za-z0-9._-]{1,32}"
               r"|system:[a-z]([a-z-]{0,38}[a-z])?)$' and length(actor) <= 80")

def _append_only(table: str) -> None:
    op.execute(f"""create function {table}_append_only() returns trigger language plpgsql as
                   $$ begin raise exception '{table} is append-only'; end $$""")
    op.execute(f"""create trigger {table}_no_change before update or delete on {table}
                   for each row execute function {table}_append_only()""")

def upgrade() -> None:
    op.create_table("hook_patterns",
        sa.Column("id", sa.String(16), primary_key=True),
        sa.Column("account_id", sa.String(40), sa.ForeignKey("accounts.id")),
        sa.Column("blueprint_name", sa.Text),
        sa.Column("status", sa.Text, nullable=False),
        sa.Column("current_version", sa.Integer, nullable=False),
        sa.Column("control", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", TS, nullable=False), sa.Column("updated_at", TS, nullable=False),
        sa.CheckConstraint("(account_id is null) <> (blueprint_name is null)", name="ck_hook_patterns_scope"),
        sa.CheckConstraint("status in ('draft','approved','retired')", name="ck_hook_patterns_status"))
    op.create_index("ix_hook_patterns_account", "hook_patterns", ["account_id"])
    op.create_index("ix_hook_patterns_blueprint", "hook_patterns", ["blueprint_name"])
    op.create_table("hook_pattern_versions",
        sa.Column("pattern_id", sa.String(16), sa.ForeignKey("hook_patterns.id"), primary_key=True),
        sa.Column("n", sa.Integer, primary_key=True),
        sa.Column("data", JSONB, nullable=False),
        sa.Column("author", sa.Text, nullable=False), sa.Column("note", sa.Text),
        sa.Column("created_at", TS, nullable=False),
        sa.CheckConstraint(ACTOR_CHECK.replace("actor", "author"), name="ck_hook_versions_author"))
    _append_only("hook_pattern_versions")
    op.create_table("hook_weights",
        sa.Column("account_id", sa.String(40), sa.ForeignKey("accounts.id"), primary_key=True),
        sa.Column("pattern_id", sa.String(16), sa.ForeignKey("hook_patterns.id"), primary_key=True),
        sa.Column("weight", sa.Float, nullable=False),
        sa.Column("updated_by", sa.Text, nullable=False), sa.Column("updated_at", TS, nullable=False),
        sa.CheckConstraint("weight >= 0", name="ck_hook_weights_nonneg"),
        sa.CheckConstraint(ACTOR_CHECK.replace("actor", "updated_by"), name="ck_hook_weights_updated_by"))
    op.create_table("hook_freezes",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("account_id", sa.String(40), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column("experiment_id", sa.BigInteger, nullable=False),     # S3c's experiments.id
        sa.Column("rotation", JSONB, nullable=False),
        sa.Column("frozen_at", TS, nullable=False), sa.Column("frozen_by", sa.Text, nullable=False),
        sa.Column("released_at", TS), sa.Column("released_by", sa.Text),
        sa.CheckConstraint(ACTOR_CHECK.replace("actor", "frozen_by"), name="ck_hook_freezes_frozen_by"),
        sa.CheckConstraint("released_by is null or (" + ACTOR_CHECK.replace("actor", "released_by") + ")",
                           name="ck_hook_freezes_released_by"))
    op.create_index("ux_hook_freezes_open", "hook_freezes", ["account_id"], unique=True,
                    postgresql_where=sa.text("released_at is null"))
    op.create_table("hook_ratings",
        sa.Column("item_id", sa.String(64), sa.ForeignKey("content_items.id"), primary_key=True),
        sa.Column("rating", sa.SmallInteger, nullable=False),
        sa.Column("actor", sa.Text, nullable=False), sa.Column("at", TS, nullable=False),
        sa.CheckConstraint("rating in (-1, 1)", name="ck_hook_ratings_value"),
        sa.CheckConstraint(ACTOR_CHECK, name="ck_hook_ratings_actor"))
    op.create_table("hook_events",
        sa.Column("id", sa.BigInteger, sa.Identity(), primary_key=True),
        sa.Column("at", TS, nullable=False), sa.Column("actor", sa.Text, nullable=False),
        sa.Column("account_id", sa.String(40), sa.ForeignKey("accounts.id")),
        sa.Column("pattern_id", sa.String(16), sa.ForeignKey("hook_patterns.id")),
        sa.Column("kind", sa.Text, nullable=False), sa.Column("data", JSONB, nullable=False),
        sa.CheckConstraint(ACTOR_CHECK, name="ck_hook_events_actor"))
    op.create_index("ix_hook_events_pattern", "hook_events", ["pattern_id", "at"])
    _append_only("hook_events")
    op.add_column("content_items", sa.Column("hook_pattern_id", sa.String(16)))
    op.add_column("content_items", sa.Column("hook_version", sa.Integer))
    op.add_column("content_items", sa.Column("hook_weights", JSONB))
    op.add_column("content_items", sa.Column("hook_result", JSONB))
    op.add_column("content_items", sa.Column("superseded_by", sa.String(64),
                                             sa.ForeignKey("content_items.id")))
    op.create_foreign_key("fk_items_hook_version", "content_items", "hook_pattern_versions",
                          ["hook_pattern_id", "hook_version"], ["pattern_id", "n"])
    op.create_index("ix_items_hook_pattern", "content_items", ["hook_pattern_id"])

def downgrade() -> None:
    op.drop_index("ix_items_hook_pattern", "content_items")
    op.drop_constraint("fk_items_hook_version", "content_items", type_="foreignkey")
    for column in ("superseded_by", "hook_result", "hook_weights", "hook_version", "hook_pattern_id"):
        op.drop_column("content_items", column)
    for table in ("hook_events", "hook_pattern_versions"):
        op.execute(f"drop trigger {table}_no_change on {table}")
        op.execute(f"drop function {table}_append_only()")
    op.drop_index("ix_hook_events_pattern", "hook_events")
    op.drop_table("hook_events")
    op.drop_table("hook_ratings")
    op.drop_index("ux_hook_freezes_open", "hook_freezes")
    op.drop_table("hook_freezes")
    op.drop_table("hook_weights")
    op.drop_table("hook_pattern_versions")
    op.drop_index("ix_hook_patterns_blueprint", "hook_patterns")
    op.drop_index("ix_hook_patterns_account", "hook_patterns")
    op.drop_table("hook_patterns")
```

Mirror every table and column in `db/tables.py` (so the empty-autogenerate test passes), and set `EXPECTED_HEAD = "NNNN"`.

- [ ] **Step 4: Run and see them pass**

Run: `uv run pytest -q tests/db`
Expected: PASS.

- [ ] **Step 5: Check and record**

Run `scripts/check.sh --python`, then note the task.

### Task 3: Rotation (pure)

**Files:**
- Create: `src/clipforge/hooks/__init__.py`, `src/clipforge/hooks/rotation.py`
- Test: `tests/hooks/__init__.py`, `tests/hooks/test_rotation.py`

**Interfaces:**
- Consumes: `HookPattern`, `HookPatternVersion`, `HookRotation`, `RotationEntry`, `HookPick` (Task 1).
- Produces:
  - `resolve(account_id: str, producer: HookFit, patterns: list[tuple[HookPattern, HookPatternVersion]], weights: dict[str, float], open_freeze: HookRotation | None) -> HookRotation`
  - `seed_for(*parts: str) -> str` (hex sha256 of the parts joined by `"|"`)
  - `clip_seed(source_hash: str, start: float, end: float, rotation: HookRotation) -> str` = `seed_for(source_hash, f"{start:.3f}", f"{end:.3f}", rotation.id)`
  - `pick(rotation: HookRotation | None, seed: str) -> HookPick | None`
  - `control_entry(rotation: HookRotation | None) -> RotationEntry | None` (the entry whose `data.control` is true)
  - `weights_of(rotation: HookRotation) -> dict[str, float]` (`"<pattern_id>@<version>" -> weight`) and `control_stamp(rotation: HookRotation | None, title: str) -> HookStamp | None` (the flag-off stamp: the control entry's id and version, `text=title`, `drawn=False`, the rotation's weights; `None` without a rotation or a control), used by enqueue and package (Task 5)

- [ ] **Step 1: Write the failing tests**

```python
# tests/hooks/test_rotation.py
from collections import Counter
from clipforge.hooks.rotation import clip_seed, control_entry, pick, resolve, seed_for
from tests.hooks.builders import entry, pattern_pair, rotation   # small builders in this task

def test_pick_is_deterministic() -> None:
    r = rotation(entry("hp_a", 1.0), entry("hp_b", 1.0))
    seed = clip_seed("abc", 1.0, 31.5, r)
    assert pick(r, seed) == pick(r, seed)

def test_pick_follows_weights() -> None:
    r = rotation(entry("hp_a", 1.0), entry("hp_b", 3.0))
    counts = Counter(pick(r, seed_for(str(i))).pattern_id for i in range(6000))
    expected = {"hp_a": 1500, "hp_b": 4500}
    chi2 = sum((counts[k] - v) ** 2 / v for k, v in expected.items())
    assert chi2 < 10.83          # p = 0.001, 1 degree of freedom

def test_empty_rotation_picks_none() -> None:              # Review Focus 5
    assert pick(rotation(), seed_for("x")) is None
    assert pick(None, seed_for("x")) is None

def test_resolve_keeps_approved_fitting_weighted_current_versions() -> None:
    pairs = [pattern_pair("hp_a", status="approved", fits=["clips"]),
             pattern_pair("hp_b", status="draft", fits=["clips"]),
             pattern_pair("hp_c", status="approved", fits=["story"]),
             pattern_pair("hp_d", status="approved", fits=["clips"])]
    r = resolve("realtalk-clips-en", "clips", pairs, {"hp_a": 1.0, "hp_b": 1.0, "hp_c": 1.0, "hp_d": 0.0}, None)
    assert [e.pattern_id for e in r.entries] == ["hp_a"] and r.frozen_by is None

def test_open_freeze_wins() -> None:
    frozen = rotation(entry("hp_old", 1.0)).model_copy(update={"frozen_by": 1})
    r = resolve("realtalk-clips-en", "clips", [pattern_pair("hp_a", status="approved", fits=["clips"])],
                {"hp_a": 1.0}, frozen)
    assert r == frozen

def test_control_entry() -> None:
    r = rotation(entry("hp_a", 1.0), entry("hp_ctl", 1.0, control=True))
    assert control_entry(r).pattern_id == "hp_ctl" and control_entry(None) is None
```

`tests/hooks/builders.py`: `entry(pid, weight, control=False, version=1) -> RotationEntry` (sets `RotationEntry.control`), `rotation(*entries) -> HookRotation` (account `realtalk-clips-en`), `pattern_pair(pid, status, fits, version=1, control=False) -> tuple[HookPattern, HookPatternVersion]`.

- [ ] **Step 2: Run and see them fail**

Run: `uv run pytest -q tests/hooks/test_rotation.py`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement**

```python
# src/clipforge/hooks/rotation.py
"""Hook rotation (ADR-50, spec §4.2): resolve the live library or a freeze into a rotation,
and a seeded weighted pick. Pure: no database, no clock."""

def resolve(account_id, producer, patterns, weights, open_freeze) -> HookRotation:
    if open_freeze is not None:
        return open_freeze
    entries = [
        RotationEntry(pattern_id=p.id, version=v.n, weight=weights[p.id], control=p.control, data=v.data)
        for p, v in patterns
        if p.status == "approved" and producer in v.data.fits
        and v.n == p.current_version and weights.get(p.id, 0.0) > 0
    ]
    return HookRotation(account_id=account_id, entries=sorted(entries, key=lambda e: (e.pattern_id, e.version)))

def seed_for(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()

def clip_seed(source_hash: str, start: float, end: float, rotation: HookRotation) -> str:
    return seed_for(source_hash, f"{start:.3f}", f"{end:.3f}", rotation.id)

def pick(rotation: HookRotation | None, seed: str) -> HookPick | None:
    if rotation is None or not rotation.entries:
        return None
    entries = sorted(rotation.entries, key=lambda e: (e.pattern_id, e.version))
    total = sum(e.weight for e in entries)
    point = int(seed, 16) / 2**256 * total
    for e in entries:
        point -= e.weight
        if point < 0:
            return HookPick(pattern_id=e.pattern_id, version=e.version, control=e.control, data=e.data)
    last = entries[-1]
    return HookPick(pattern_id=last.pattern_id, version=last.version, control=last.control, data=last.data)

def control_entry(rotation: HookRotation | None) -> RotationEntry | None:
    if rotation is None:
        return None
    return next((e for e in rotation.entries if e.control), None)
```

- [ ] **Step 4: Run and see them pass**

Run: `uv run pytest -q tests/hooks/test_rotation.py`
Expected: PASS.

- [ ] **Step 5: Check and record**

Run `scripts/check.sh --python`, then note the task.

### Task 4: The library service, the freezer and the seeds

**Files:**
- Create: `src/clipforge/db/hooks.py`, `src/clipforge/hooks/library.py`, `src/clipforge/hooks/seeds.py`, and `src/clipforge/hooks/freezer.py` with the Global Constraints' exact content, unless S3c-3 already created it (then import it)
- Test: `tests/hooks/test_library.py`, `tests/hooks/test_freezer.py`, `tests/hooks/test_seeds.py`

**Interfaces:**
- Consumes: Task 1's contracts; Task 2's tables; Task 3's `resolve`; `posting.actions._checked` (actor validation; import it as `check_actor` if it's private, or add a public alias in `actions.py`).
- Produces:
  - `HookError(ValueError)`;
  - `HookLibrary(db: Database)` with:
    - `patterns(account_id: str) -> list[tuple[HookPattern, HookPatternVersion, float]]` (own and blueprint-shared, with the account's weight)
    - `create_draft(account_id: str, data: HookPatternData, actor: str, now: datetime, *, control: bool = False) -> HookPattern`
    - `edit(pattern_id: str, data: HookPatternData, note: str | None, actor: str, now: datetime) -> HookPatternVersion`
    - `approve(pattern_id: str, account_id: str, actor: str, now: datetime, weight: float = 1.0) -> HookPattern`
    - `retire(pattern_id: str, account_id: str, actor: str, now: datetime) -> HookPattern`
    - `share(pattern_id: str, actor: str, now: datetime) -> HookPattern`
    - `set_weight(account_id: str, pattern_id: str, weight: float, reason: str, actor: str, now: datetime) -> float`
    - `rotation_for(account_id: str, producer: HookFit) -> HookRotation`
    - `open_freeze(account_id: str) -> HookRotation | None`
  - `SqlHookFreezer(library: HookLibrary)` implementing `freeze(conn, account_id: str, experiment_id: int) -> None` and `release(conn, account_id: str, experiment_id: int) -> None`;
  - `hooks/seeds.py`: `CLIPS_SEEDS: list[tuple[bool, HookPatternData]]` (control flag, body) (spec §4.1's six) and `seed(library: HookLibrary, account_ids: list[str], now: datetime, *, running: Callable[[str], list[int]] = lambda a: [], freezer: SqlHookFreezer | None = None, dry_run: bool = False) -> dict[str, int]` (patterns written per account; `running(account_id)` returns the account's running experiment ids, through S3c's experiments repo when it's on `main`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/hooks/test_library.py
NOW = datetime(2026, 10, 3, 9, tzinfo=UTC)
DATA = HookPatternData(name="Open question", structure="A question the clip answers",
                       examples={"en": "WHY DID HE WALK AWAY?"}, fits=["clips"], max_words=8)

@pytest.fixture
def lib(db) -> HookLibrary:
    insert_account(db, "realtalk-clips-en", blueprint="realtalk-clips")
    return HookLibrary(db)

def test_draft_then_approve_enters_rotation_at_weight_one(lib) -> None:
    p = lib.create_draft("realtalk-clips-en", DATA, "web:mat", NOW)
    assert lib.rotation_for("realtalk-clips-en", "clips").entries == []
    lib.approve(p.id, "realtalk-clips-en", "web:mat", NOW)
    [e] = lib.rotation_for("realtalk-clips-en", "clips").entries
    assert (e.pattern_id, e.version, e.weight) == (p.id, 1, 1.0)

def test_edit_writes_next_version_and_keeps_the_old(lib, db) -> None:
    p = lib.create_draft("realtalk-clips-en", DATA, "web:mat", NOW)
    v2 = lib.edit(p.id, DATA.model_copy(update={"structure": "Sharper"}), "tighter", "web:mat", NOW)
    assert v2.n == 2 and version_count(db, p.id) == 2

def test_weight_change_logs_from_to_reason(lib, db) -> None:
    p = approved(lib)
    lib.set_weight("realtalk-clips-en", p.id, 0.5, "weak on rejects", "web:mat", NOW)
    ev = last_event(db, "weight")
    assert ev.data == {"from": 1.0, "to": 0.5, "reason": "weak on rejects"} and ev.actor == "web:mat"

def test_weight_needs_a_reason_and_a_valid_actor(lib) -> None:
    p = approved(lib)
    with pytest.raises(HookError, match="reason"):
        lib.set_weight("realtalk-clips-en", p.id, 0.5, "  ", "web:mat", NOW)
    with pytest.raises(HookError, match="actor"):
        lib.set_weight("realtalk-clips-en", p.id, 0.5, "x", "nobody", NOW)

def test_retire_sets_weight_zero_and_leaves_rotation(lib) -> None:
    p = approved(lib)
    lib.retire(p.id, "realtalk-clips-en", "web:mat", NOW)
    assert lib.rotation_for("realtalk-clips-en", "clips").entries == []

def test_share_moves_scope_and_pair_sees_it_at_weight_zero(lib, db) -> None:
    insert_account(db, "realtalk-clips-es", blueprint="realtalk-clips")
    p = approved(lib)
    lib.share(p.id, "web:mat", NOW)
    shared = {x.id: w for x, _, w in lib.patterns("realtalk-clips-es")}
    assert shared[p.id] == 0.0
    assert [e.pattern_id for e in lib.rotation_for("realtalk-clips-en", "clips").entries] == [p.id]

def test_unknown_pattern_is_a_hook_error(lib) -> None:
    with pytest.raises(HookError, match="no pattern"):
        lib.approve("hp_zzzzzzzz", "realtalk-clips-en", "web:mat", NOW)
```

```python
# tests/hooks/test_freezer.py
def test_freeze_snapshots_and_edits_apply_at_release(lib, db) -> None:
    p = approved(lib)
    freezer = SqlHookFreezer(lib)
    with db.begin() as conn:
        freezer.freeze(conn, "realtalk-clips-en", 1)
    lib.set_weight("realtalk-clips-en", p.id, 3.0, "try more", "web:mat", NOW)   # saved...
    r = lib.rotation_for("realtalk-clips-en", "clips")
    assert r.frozen_by == 1 and r.entries[0].weight == 1.0                     # ...not applied
    with db.begin() as conn:
        freezer.release(conn, "realtalk-clips-en", 1)
    assert lib.rotation_for("realtalk-clips-en", "clips").entries[0].weight == 3.0

def test_freeze_is_idempotent_and_rolls_back_with_the_caller(lib, db) -> None:
    approved(lib)
    freezer = SqlHookFreezer(lib)
    with db.begin() as conn:
        freezer.freeze(conn, "realtalk-clips-en", 1)
        freezer.freeze(conn, "realtalk-clips-en", 1)
    assert open_freeze_count(db) == 1
    with pytest.raises(RuntimeError):
        with db.begin() as conn:
            freezer.release(conn, "realtalk-clips-en", 1)
            raise RuntimeError("the experiment's own write failed")
    assert open_freeze_count(db) == 1        # the release rolled back with the caller

def test_freeze_is_a_no_op_without_a_library(lib, db) -> None:
    with db.begin() as conn:
        SqlHookFreezer(lib).freeze(conn, "realtalk-clips-en", 1)     # no hook_weights rows yet
    assert open_freeze_count(db) == 0

def test_freeze_events_use_the_system_actor(lib, db) -> None:
    approved(lib)
    with db.begin() as conn:
        SqlHookFreezer(lib).freeze(conn, "realtalk-clips-en", 1)
    ev = last_event(db, "frozen")
    assert ev.actor == "system:experiment" and ev.data["experiment_id"] == 1
```

```python
# tests/hooks/test_seeds.py
def test_seed_writes_six_approved_at_equal_weight_once(lib) -> None:
    assert seed(lib, ["realtalk-clips-en"], NOW) == {"realtalk-clips-en": 6}
    assert seed(lib, ["realtalk-clips-en"], NOW) == {"realtalk-clips-en": 0}      # idempotent
    rows = lib.patterns("realtalk-clips-en")
    assert len(rows) == 6 and {w for _, _, w in rows} == {1.0}
    assert sum(p.control for p, _, _ in rows) == 1

def test_seed_dry_run_writes_nothing(lib) -> None:
    assert seed(lib, ["realtalk-clips-en"], NOW, dry_run=True) == {"realtalk-clips-en": 6}
    assert lib.patterns("realtalk-clips-en") == []

def test_seed_freezes_accounts_with_running_experiments(lib) -> None:
    seed(lib, ["realtalk-clips-en"], NOW, running=lambda a: [7], freezer=SqlHookFreezer(lib))
    assert lib.rotation_for("realtalk-clips-en", "clips").frozen_by == 7

def test_claim_seeds_say_no_promises() -> None:
    by_name = {d.name: d for _, d in CLIPS_SEEDS}
    for name in ("Number + stakes", "Bold claim"):
        assert "no promises" in by_name[name].structure

def test_seed_examples_fit_max_words_after_cleaning() -> None:
    for _, data in CLIPS_SEEDS:
        for line in data.examples.values():
            assert 0 < len(title_words(line)) <= data.max_words
```

Add the small helpers `approved(lib)`, `version_count`, `last_event`, `open_freeze_count` to `tests/hooks/helpers.py`, and `insert_account(db, id, blueprint=...)` to `tests/dbhelpers.py` if S2's helpers don't have it.

- [ ] **Step 2: Run and see them fail**

Run: `uv run pytest -q tests/hooks`
Expected: FAIL (modules missing).

- [ ] **Step 3: Implement**

- `db/hooks.py`: plain SQLAlchemy Core functions taking a `Connection` (`insert_pattern`, `insert_version`, `set_status`, `set_scope`, `upsert_weight`, `insert_event`, `open_freeze_row`, `insert_freeze`, `close_freeze`, `patterns_for(account_id, blueprint)`), so `SqlHookFreezer` can run them on the caller's connection.
- `HookLibrary` opens `self.db.begin()` per call, validates the actor with `check_actor`, and writes the change and its `hook_events` row in one transaction. Pattern ids: `"hp_" + secrets.token_hex(4)`; `share` raises `HookError` for a blueprint pattern or an account without a blueprint; `set_weight` requires `weight >= 0` and a non-blank reason; `approve` upserts the account's weight row (default 1.0); `retire` upserts it to 0.0 and writes `retired` and `weight` events.
- `rotation_for(account_id, producer)` reads `open_freeze(account_id)` and `patterns(account_id)` (current versions), then returns `resolve(...)`.
- `SqlHookFreezer.freeze(conn, account_id, experiment_id)`: if the account has no `hook_weights` rows, return (no library, nothing to freeze); if an open row exists for this experiment, return; if one exists for another experiment, raise `HookError`; otherwise compute the live rotation **on `conn`** (`resolve` over `patterns_for` read through `conn`), insert it with `frozen_by="system:experiment"` and a `frozen` event with `{"experiment_id": …}`. `release` closes the open row for that experiment (no-op if none) and writes `released`.
- `hooks/seeds.py`: the six patterns of spec §4.1 as `(control: bool, HookPatternData)` pairs (all `fits=["clips"]`, `max_words=8`, examples `en` and `es`; the control is created with `hook_patterns.control = true` and `structure="Ship the clip's own title unchanged"`; Number + stakes and Bold claim end with "Only numbers and claims said in the clip; no promises." / "Only claims said in the clip; no promises."). `create_draft` takes `control: bool = False`, set once on the pattern row. `seed()` skips accounts that already have any pattern, writes each pattern (status `approved`, version 1, weight 1.0, author `system:migration`, events `seeded`), then for each id in `running(account_id)` calls `freezer.freeze` on the same transaction.

- [ ] **Step 4: Run and see them pass**

Run: `uv run pytest -q tests/hooks tests/db`
Expected: PASS.

- [ ] **Step 5: Check and record**

Run `scripts/check.sh --python`, then note the task.

### Task 5: The rotation on the job and the control stamp on items

**Files:**
- Modify: `src/clipforge/pipeline/steps.py` (`Deps.hooks: HookLibrary | None = None`, `Deps.hook_variants: bool = False`), `src/clipforge/service.py` (`create_job`), `src/clipforge/stages/package.py` (`Versions.hook_rotation` and the flag-off control stamp on `PackagedClip.hook`), `src/clipforge/posting/enqueue.py` (`ClipFacts.hook`, `items_for`), `src/clipforge/db/posting.py` (`_item_row` and the item reader), `src/clipforge/runtime.py` (`build_deps`)
- Test: `tests/test_service.py`, `tests/posting/test_enqueue.py`, `tests/db/test_posting_repo.py`, `tests/test_runtime.py`

**Interfaces:**
- Consumes: `HookLibrary.rotation_for` (Task 4); `control_entry` (Task 3).
- Produces:
  - `service.create_job` sets `job_input.hooks` from `deps.hooks.rotation_for(account_id, "clips")` when the job has a channel whose source belongs to an account; any exception → `hooks=None`, `Job.hooks_note = "unavailable"` and a log warning;
  - `package` writes `Versions.hook_rotation` = the rotation's id, else `job.hooks_note`, else `"none"`, so `metadata.json` says whether the job had a rotation (spec §2.1), and, with the flag off, `PackagedClip.hook` = the same control stamp enqueue writes (`hooks/rotation.py::control_stamp(rotation, title) -> HookStamp | None`, used by both), so `metadata.json` and the item agree from HK-1;
  - `ClipFacts.hook: HookResult | None` (from `RenderedClip.hook`, or from `PackagedClip.hook.result`);
  - `items_for(..., rotation: HookRotation | None, flag_on: bool)`: with the flag off, the stamp is the control (`HookResult(pattern_id=<control id>, version=<its version>, text=c.title, drawn=False)`, weights from the rotation); with no rotation or no control entry, no stamp;
  - `db/posting._item_row` writes `hook_pattern_id`, `hook_version`, `hook_weights`, `hook_result`; the reader fills `ContentItem.hook_stamp` and `superseded_by`;
  - `runtime.build_deps(..., db)` sets `Deps.hooks = HookLibrary(db)` when `db` is not None, and replaces S3c's no-op `HookFreezer` with `SqlHookFreezer(HookLibrary(db))` wherever S3c wires it.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_service.py (add)
def test_create_job_freezes_the_rotation(deps_with_db, seeded_account) -> None:
    job = create_job(deps_with_db, channel_input("realtalk"))      # source realtalk -> realtalk-clips-en
    assert job.input.hooks is not None and len(job.input.hooks.entries) == 6

def test_create_job_without_a_database_has_no_rotation(deps_dict_only) -> None:
    assert create_job(deps_dict_only, channel_input("realtalk")).input.hooks is None

def test_create_job_survives_a_database_error(deps_with_db, monkeypatch) -> None:
    monkeypatch.setattr(deps_with_db.hooks, "rotation_for", raise_operational_error)
    job = create_job(deps_with_db, channel_input("realtalk"))
    assert job.input.hooks is None and job.hooks_note == "unavailable"
    assert job.status is JobStatus.QUEUED
```

```python
# tests/posting/test_enqueue.py (add)
def test_flag_off_stamps_the_control_with_the_jobs_weights() -> None:
    rot = rotation(entry("hp_ctl", 1.0, control=True), entry("hp_a", 2.0))
    [item] = items_for(job_with(rot), [facts(title="Highlight title")], NOW, ACCOUNT, None, "clips:x",
                       rotation=rot, flag_on=False)
    assert item.hook_stamp.result.pattern_id == "hp_ctl" and item.title == "Highlight title"
    assert item.hook_stamp.result.drawn is False
    assert item.hook_stamp.weights == {"hp_ctl@1": 1.0, "hp_a@1": 2.0}
    assert item.hook_stamp.rotation_id == rot.id

def test_no_rotation_no_stamp() -> None:
    [item] = items_for(job_with(None), [facts()], NOW, ACCOUNT, None, "clips:x", rotation=None, flag_on=False)
    assert item.hook_stamp is None
```

```python
# tests/stages/test_package.py (add)
def test_flag_off_metadata_carries_the_control_stamp(tmp_path) -> None:
    meta = package_case(tmp_path, hook=None, rotation=rotation(entry("hp_ctl", 1.0, control=True)))
    assert meta.clips[0].hook.result.pattern_id == "hp_ctl" and meta.versions.hook_rotation

# tests/db/test_posting_repo.py (add)
def test_stamp_columns_round_trip(db, seeded_account) -> None:
    item = make_item(hook_stamp=control_stamp())
    SqlPostingRepo(db).add(item, [Platform.TIKTOK])
    assert SqlPostingRepo(db).get(item.id).item.hook_stamp == item.hook_stamp
```

```python
# tests/test_runtime.py (add)
def test_build_deps_wires_the_hook_library_only_with_a_database(settings) -> None:
    assert build_deps(settings, **fakes()).hooks is None
    assert isinstance(build_deps(settings, **fakes(), db=fake_db()).hooks, HookLibrary)
```

Use the existing fixtures of each test file (`tests/posting/builders.py`, `tests/pipeline/fakes.py`); add `seeded_account` (an account + source + `seed()`) to `tests/hooks/helpers.py`.

- [ ] **Step 2: Run and see them fail**

Run: `uv run pytest -q tests/test_service.py tests/posting/test_enqueue.py tests/db/test_posting_repo.py tests/test_runtime.py`
Expected: FAIL.

- [ ] **Step 3: Implement**

- `create_job`: set `Job.hooks_note` on failure (it's saved with the job); resolve the account through `deps.posting.source(channel.slug)` → `source.account_id` (in `dict` mode, `deps.posting.default_account_id`), then `job_input.model_copy(update={"hooks": rotation})` before building the `Job`. Wrap the lookup in `try/except Exception` with `log.warning("hook rotation unavailable for %s: %s", account_id, redact(exc))`. The job never fails over it.
- `enqueue_job` gains `rotation` and `flag_on` parameters and passes them to `items_for`; `_enqueue_posts` passes `job.input.hooks` and `deps.hook_variants` (`build_deps` sets it from `settings.hook_variants`).
- `items_for`: build the stamp per clip:
  - flag on and `c.hook` set → `HookStamp(result=c.hook, rotation_id=rot.id, weights=_weights(rot), frozen_by=rot.frozen_by)`, `title=c.hook.text` (the line **as written**; only the title card is upper-cased);
  - flag off, or flag on with `c.hook is None` → the control stamp when `control_entry(rot)` exists, `title=c.title`;
  - `_weights(rot) = {f"{e.pattern_id}@{e.version}": e.weight for e in rot.entries}`.
- `db/posting._item_row` adds the four columns from `item.hook_stamp` (`hook_result` = `stamp.result` plus `rotation_id` and `frozen_by`); the reader rebuilds `HookStamp`.

- [ ] **Step 4: Run and see them pass**

Run: `uv run pytest -q tests`
Expected: PASS.

- [ ] **Step 5: Check and record**

Run `scripts/check.sh --python`, then note the task.

### Task 6: Library routes and the CLI

**Files:**
- Modify: `src/clipforge/api/main.py`, `src/clipforge/cli.py`, `web/openapi.json` and `web/lib/api` (regenerated)
- Test: `tests/api/test_hooks_api.py`, `tests/test_cli.py`

**Interfaces:**
- Consumes: `HookLibrary`, `seed` (Task 4).
- Produces (the CLI's routes, so they belong in `cli_router`; actor from `X-Clipforge-Actor`; `HookError` → 400, unknown account or pattern → 404, database down → 503 through the existing handlers):
  - `GET /admin/accounts/{id}/hooks` → `HookLibraryView{account_id, frozen_by: str | None, rotating: int, patterns: [HookRow{pattern: HookPattern, version: HookPatternVersion, weight: float}]}` (`rotating` = entries in `rotation_for`; stats join in Task 10);
  - `POST /admin/hooks` `{account_id, data: HookPatternData}` → 201 `HookPattern` (draft);
  - `PUT /admin/hooks/{id}` `{data, note}` → `HookPatternVersion`;
  - `POST /admin/hooks/{id}/approve` `{account_id, weight?}`, `/retire` `{account_id}`, `/share` → `HookPattern`;
  - `PUT /admin/hooks/{id}/weight` `{account_id, weight, reason}` → `{weight}`;
  - `POST /admin/hooks/seed?dry_run=` `{account_ids?}` (default: every `clips` account) → `{written: {account: n}}`;
  - CLI: `clipforge hooks list <account>`, `show <pattern>`, `add <account> --name --structure --example LANG=TEXT … [--max-words]`, `edit <pattern> [--structure …] --note`, `approve <pattern> --account [--weight]`, `retire <pattern> --account`, `share <pattern>`, `weight <pattern> <w> --account --reason`, `seed [--account] [--dry-run]`, `stats <pattern>` (Task 10 fills it).

- [ ] **Step 1: Write the failing tests**

```python
# tests/api/test_hooks_api.py
def test_library_lists_seeded_patterns(client, seeded) -> None:
    body = client.get("/admin/accounts/realtalk-clips-en/hooks", headers=AUTH).json()
    assert body["rotating"] == 6 and body["frozen_by"] is None

def test_library_reports_empty_rotation(client, seeded) -> None:           # Review Focus 5
    for row in client.get("/admin/accounts/realtalk-clips-en/hooks", headers=AUTH).json()["patterns"]:
        client.post(f"/admin/hooks/{row['pattern']['id']}/retire", headers=AUTH | ACTOR,
                    json={"account_id": "realtalk-clips-en"})
    assert client.get("/admin/accounts/realtalk-clips-en/hooks", headers=AUTH).json()["rotating"] == 0

def test_weight_without_reason_is_400(client, seeded) -> None:
    pid = first_pattern(client)
    r = client.put(f"/admin/hooks/{pid}/weight", headers=AUTH | ACTOR,
                   json={"account_id": "realtalk-clips-en", "weight": 2, "reason": ""})
    assert r.status_code == 400

def test_routes_need_the_token(client) -> None:
    assert client.get("/admin/accounts/realtalk-clips-en/hooks").status_code == 401

def test_unknown_pattern_404(client, seeded) -> None:
    assert client.post("/admin/hooks/hp_zzzzzzzz/approve", headers=AUTH | ACTOR,
                       json={"account_id": "realtalk-clips-en"}).status_code == 404
```

```python
# tests/test_cli.py (add)
def test_hooks_list_prints_weights(fake_api, capsys) -> None:
    fake_api.hooks = library_view(rotating=6)
    assert main(["hooks", "list", "realtalk-clips-en"], client=fake_api) == 0
    out = capsys.readouterr().out
    assert "Highlight title" in out and "1.0" in out and "6 rotating" in out

def test_hooks_seed_dry_run(fake_api, capsys) -> None:
    fake_api.seeded = {"realtalk-clips-en": 6}
    main(["hooks", "seed", "--dry-run"], client=fake_api)
    assert "realtalk-clips-en: 6 patterns (dry run)" in capsys.readouterr().out
```

- [ ] **Step 2: Run and see them fail**

Run: `uv run pytest -q tests/api/test_hooks_api.py tests/test_cli.py -k hooks`
Expected: FAIL.

- [ ] **Step 3: Implement**

Add the routes to S3's `cli_router` when it's on `main` (S3 plan Task 1), else in `create_app` next to S2's `/admin/*` routes (Global Constraints), in the `/accounts` routes' style (`database()`, `slug()` for account ids, a `pattern_id()` check with `re.fullmatch(r"hp_[0-9a-f]{8}", …)` → 404). Add the `hooks` subparser in `build_parser` and its dispatch in `main`, as `_add_source_parser` does; `ApiClient` gains `hooks_*` methods. Regenerate `web/openapi.json` with the existing export script and `npm --prefix web run gen`.

- [ ] **Step 4: Run and see them pass**

Run: `uv run pytest -q tests/api tests/test_cli.py`
Expected: PASS.

- [ ] **Step 5: Check and record — checkpoint HK-1**

1. Run the full `scripts/check.sh`.
2. Ask `pr-reviewer` and `migration-reviewer` to review (and `pipeline-reviewer` for Task 5's enqueue change).
3. Update `docs/ARCHITECTURE.md` (the hooks tables and the stamp, under "Durable state in Postgres"), `.env.example` (`# HOOK_VARIANTS=false`) and `docs/studio/04-roadmap.md`'s HK list.
4. Write the report.
5. Suggested commit: `NNN: hk-1: hook library tables, seeds, rotation on jobs, control stamps`.

**Owner deploy steps (HK-1).**

Preconditions: card 010 done; card 014 deployed (`db_doctor` head = 0002, or the head of whichever of S3's and S3c's migrations deployed since); `clipforge posting verify` at 0.

0. **The #144 check:** no other code card is on `main` undeployed (`docs/ops/deploys.md` against `git log`).
1. `uv run alembic upgrade head` (`DATABASE_URL_UNPOOLED` only), then `scripts/deploy.sh --dry-run` (shows the new head), then `scripts/deploy.sh --reason "HK-1: hook library, control stamps"`, outside the blackout (runbook §1).
2. `uv run modal run src/clipforge/app.py::db_doctor`. Expected: the hooks head.
3. `uv run clipforge hooks seed --dry-run`, then `uv run clipforge hooks seed`. Expected: "realtalk-clips-en: 6 patterns" (and each other clips account).
4. `uv run clipforge hooks list realtalk-clips-en`: six patterns, weight 1.0, "6 rotating".
5. Clip one episode (`uv run clipforge clip videos/<source>/<file>`). When it's done, its items carry `hook_pattern_id` = the control's id (Neon console: `select id, hook_pattern_id, hook_version from content_items order by queued_at desc limit 5`), and the clips look exactly as before.

**Rollback (HK-1):** a revert deploy (`git revert` of the HK-1 merge on `main`, `scripts/deploy.sh --dry-run`, `scripts/deploy.sh --reason "revert HK-1"`). The migration is expand-only; S2a's code ignores the new tables and columns.

---

# Part HK-2: variants, ranking and re-render

### Task 7: The shared variants interface (`hooks/variants.py`)

**Files:**
- Create: `src/clipforge/hooks/variants.py`
- Test: `tests/hooks/test_variants.py`

**Interfaces:**
- Consumes: `HookPick`, `HookVariants`, `HookResult` (Task 1); `captions.title_words` (existing).
- Produces:
  - `render_task(pick: HookPick | None, language: str, source_line: str, n: int = 3) -> str` (the `{hook_task}` prompt block);
  - `valid_lines(variants: list[str], max_words: int) -> list[tuple[str, ...]]` (cleaned; raises `ValueError` naming the first invalid line);
  - `settle(reply: HookVariants | None, pick: HookPick | None, fallback_text: str, *, drawn: bool) -> HookResult`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/hooks/test_variants.py
OPEN_Q = pick_of("hp_q", "Open question", "A question the clip answers", {"en": "WHY DID HE WALK AWAY?"})
CONTROL = pick_of("hp_c", "Highlight title", "Ship the clip's own title unchanged", {}, control=True)

def test_task_for_a_pattern_names_structure_example_and_limits() -> None:
    task = render_task(OPEN_Q, "en", "He quit at 40")
    assert "A question the clip answers" in task and "WHY DID HE WALK AWAY?" in task
    assert "2–3 lines" in task and "at most 8 words" in task and "He quit at 40" in task

def test_task_for_control_or_none_says_use_the_title() -> None:
    for p in (CONTROL, None):
        assert "use the title as given" in render_task(p, "en", "He quit at 40").lower()

def test_example_falls_back_to_the_first_language() -> None:
    assert "WHY DID HE WALK AWAY?" in render_task(OPEN_Q, "es", "x")

def test_line_too_long_is_invalid() -> None:
    with pytest.raises(ValueError, match="more than 8 words"):
        valid_lines(["ONE TWO THREE FOUR FIVE SIX SEVEN EIGHT NINE"], 8)

def test_settle_picks_best_and_records_the_pattern() -> None:
    r = settle(HookVariants(variants=["Why did he quit?", "What made him walk?"], best=1), OPEN_Q, "fallback", drawn=True)
    assert (r.pattern_id, r.version, r.chosen, r.text, r.fallback, r.drawn) == ("hp_q", 1, 1, "What made him walk?", False, True)

def test_settle_none_is_the_fallback() -> None:
    r = settle(None, OPEN_Q, "He quit at 40", drawn=True)
    assert r.fallback and r.text == "He quit at 40" and r.pattern_id == "hp_q"

def test_settle_control_ships_the_source_line() -> None:
    r = settle(None, CONTROL, "He quit at 40", drawn=True)
    assert not r.fallback and r.text == "He quit at 40" and r.pattern_id == "hp_c" and r.drawn
```

- [ ] **Step 2: Run and see them fail**

Run: `uv run pytest -q tests/hooks/test_variants.py`
Expected: FAIL.

- [ ] **Step 3: Implement**

```python
# src/clipforge/hooks/variants.py
"""The hook-variants interface every producer shares (spec §8): the prompt block, the reply
sub-model's validation, and settling a reply into a HookResult with rule 5's fallback."""

def render_task(pick, language, source_line, n=3) -> str:
    if pick is None or pick.control:
        return f"Hook: use the title as given: {source_line}"
    example = pick.data.examples.get(language) or next(iter(pick.data.examples.values()), "")
    return (f"Hook: write 2–{n} lines for the on-screen title in this pattern, in {language}, "
            f"each at most {pick.data.max_words} words, built only from what is said in the clip.\n"
            f"Pattern: {pick.data.name}. {pick.data.structure}\n"
            + (f"Example of the pattern: {example}\n" if example else "")
            + f"The clip's own title, for reference: {source_line}\n"
            "Rank them and give the index of the best one.")

def valid_lines(variants, max_words) -> list[tuple[str, ...]]:
    cleaned = []
    for i, line in enumerate(variants):
        words = title_words(line)
        if not words:
            raise ValueError(f"line {i} is empty after cleaning")
        if len(line.split()) > max_words:
            raise ValueError(f"line {i} has more than {max_words} words")
        cleaned.append(words)
    return cleaned

def settle(reply, pick, fallback_text, *, drawn) -> HookResult:
    pid, ver = (pick.pattern_id, pick.version) if pick else (None, None)
    drawn = drawn and pick is not None
    if pick is None or pick.control:
        return HookResult(pattern_id=pid, version=ver, text=fallback_text, drawn=drawn)
    if reply is None:
        return HookResult(pattern_id=pid, version=ver, text=fallback_text, fallback=True, drawn=drawn)
    return HookResult(pattern_id=pid, version=ver, variants=list(reply.variants),
                      chosen=reply.best, text=reply.variants[reply.best], drawn=drawn)   # as written
```

Move `title_words` (and its regexes) unchanged to a small `src/clipforge/stages/asstext.py` only if importing `captions` from `hooks` creates a cycle; otherwise import it from `captions`.

- [ ] **Step 4: Run and see them pass**

Run: `uv run pytest -q tests/hooks/test_variants.py`
Expected: PASS.

- [ ] **Step 5: Check and record**

Run `scripts/check.sh --python`, then note the task.

### Task 8: `keywords_v3` and variants in the captions stage

**Files:**
- Create: `prompts/keywords_v3.md`
- Modify: `prompts/metadata.json`, `src/clipforge/stages/captions.py`, `src/clipforge/stages/runner.py` (`producer_version`, the keywords prompt by flag)
- Test: `tests/stages/test_captions.py`, `tests/stages/test_runner.py`, `tests/test_prompts.py`

**Interfaces:**
- Consumes: `render_task`, `valid_lines`, `settle` (Task 7); `HookPick`, `HookResult`, `KeywordsReply` (Task 1).
- Produces:
  - `captions.stage_version(settings: Settings) -> str` ("4" when `settings.hook_variants`, else "3"); `captions.keywords_prompt(settings) -> str`;
  - `captions.run(ctx, spec, transcript, deps=None, pick: HookPick | None = None, manual_title: str | None = None) -> Stored[CaptionFiles]` (the existing signature plus `pick`, and `manual_title` for a re-render's given title, Task 11);
  - `CaptionFiles.hook` set when the flag is on;
  - `runner.producer_version(settings)` uses `captions.stage_version(settings)` and `captions.keywords_prompt(settings)`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/stages/test_captions.py (add)
OFF = Settings(_env_file=None)
ON = Settings(_env_file=None, hook_variants=True)

def test_flag_off_key_is_pinned(tmp_path) -> None:
    ctx, spec, t = clip_case(tmp_path)
    stored = captions.run(ctx, spec, t, deps_for(OFF, reply=V2_REPLY))
    assert stored.ref.split("/")[2] == PINNED_V2_KEY      # today's key, copied from a run on main

def test_same_pattern_hits_the_cache_other_pattern_reruns(tmp_path) -> None:
    ctx, spec, t = clip_case(tmp_path)
    llm = FakeLLM([V3_REPLY, V3_REPLY])
    first = captions.run(ctx, spec, t, deps_for(ON, llm=llm), pick=OPEN_Q)
    again = captions.run(ctx, spec, t, deps_for(ON, llm=llm), pick=OPEN_Q)
    other = captions.run(ctx, spec, t, deps_for(ON, llm=llm), pick=BOLD)
    assert first.ref == again.ref != other.ref and llm.calls == 2

def test_variant_ships_on_the_title_card(tmp_path) -> None:
    ctx, spec, t = clip_case(tmp_path)
    files = captions.run(ctx, spec, t, deps_for(ON, reply=V3_REPLY), pick=OPEN_Q).value
    assert files.hook.text == "WHAT MADE HIM WALK?" and files.hook.chosen == 1
    assert "WHAT MADE HIM" in title_event(ctx.path(files.ass_path).read_text())

def test_line_empty_after_cleaning_is_invalid(tmp_path) -> None:          # Review Focus 3
    ctx, spec, t = clip_case(tmp_path)
    llm = FakeLLM([v3_reply(["{\\c&H0000FF&}", "!!!"], best=0), V3_REPLY])
    files = captions.run(ctx, spec, t, deps_for(ON, llm=llm), pick=OPEN_Q).value
    assert llm.calls == 2 and "not valid" in llm.messages[1][-1]["content"]
    assert files.hook.text == "WHAT MADE HIM WALK?"

def test_two_bad_replies_fall_back_to_the_highlights_title(tmp_path) -> None:
    ctx, spec, t = clip_case(tmp_path)
    files = captions.run(ctx, spec, t, deps_for(ON, llm=FakeLLM(["nope", "still nope"])), pick=OPEN_Q).value
    assert files.hook.fallback and files.hook.text == spec.candidate.title

def test_title_keyword_indexes_the_cleaned_best_line(tmp_path) -> None:
    ctx, spec, t = clip_case(tmp_path)
    llm = FakeLLM([v3_reply(["WHY?", "WHAT MADE HIM WALK?"], best=0, title_keyword=3), V3_REPLY])
    captions.run(ctx, spec, t, deps_for(ON, llm=llm), pick=OPEN_Q)
    assert llm.calls == 2                                  # 3 is out of range for "WHY?"

def test_control_pick_keeps_the_source_title(tmp_path) -> None:
    ctx, spec, t = clip_case(tmp_path)
    files = captions.run(ctx, spec, t, deps_for(ON, reply=V2_REPLY), pick=CONTROL).value
    assert files.hook.text == spec.candidate.title and not files.hook.fallback

def test_manual_title_has_its_own_cache_key(tmp_path) -> None:
    ctx, spec, t = clip_case(tmp_path)
    a = captions.run(ctx, spec, t, deps_for(ON, reply=V2_REPLY), manual_title="He quit at 40")
    b = captions.run(ctx, spec, t, deps_for(ON, reply=V2_REPLY), manual_title="He walked away")
    assert a.ref != b.ref and a.value.hook.manual and a.value.hook.text == "He quit at 40"

def test_title_stays_as_written_card_is_upper(tmp_path) -> None:
    ctx, spec, t = clip_case(tmp_path)
    files = captions.run(ctx, spec, t, deps_for(ON, reply=v3_reply(["What made him walk?"], best=0)), pick=OPEN_Q).value
    assert files.hook.text == "What made him walk?"
    assert "WHAT MADE HIM WALK?" in title_event(ctx.path(files.ass_path).read_text())

def test_cost_recorded_per_call(tmp_path) -> None:
    ctx, spec, t = clip_case(tmp_path)
    llm = FakeLLM(["nope", V3_REPLY])
    captions.run(ctx, spec, t, deps_for(ON, llm=llm), pick=OPEN_Q)
    costs = [c for c in recorded_costs(ctx) if c.stage is StageName.CAPTIONS]
    assert [c.llm_calls for c in costs] == [1, 1] and all(c.usd_estimate > 0 for c in costs)
```

```python
# tests/stages/test_runner.py (add)
def test_producer_version_flag_off_is_pinned() -> None:
    assert producer_version(Settings(_env_file=None)) == PINNED_PRODUCER_VERSION   # copy from main

def test_producer_version_flag_on_differs() -> None:
    assert producer_version(Settings(_env_file=None, hook_variants=True)) != PINNED_PRODUCER_VERSION
```

```python
# tests/test_prompts.py (add)
def test_keywords_v3_is_released_and_renders() -> None:
    p = load_prompt("keywords_v3", PROMPTS_DIR)
    text = p.render(language="en", words="0 HELLO", max_keywords="1", source_title="T0 HI", hook_task="Hook: x")
    assert "Hook: x" in text and "variants" in text
```

Before writing the pinned tests, run `uv run python -c` on `main`'s code to print today's captions key for the fixture clip and today's `producer_version`, and paste the values in as `PINNED_V2_KEY` and `PINNED_PRODUCER_VERSION`. **Re-pin from `main` at landing:** if another card changed a stage version, prompt or model on `main` meanwhile, print both again from `main` after rebasing and update the literals (they must equal `main`'s values, not the values at the time of writing).

- [ ] **Step 2: Run and see them fail**

Run: `uv run pytest -q tests/stages/test_captions.py tests/stages/test_runner.py tests/test_prompts.py`
Expected: FAIL.

- [ ] **Step 3: Write the prompt**

`prompts/keywords_v3.md`: `keywords_v2.md`'s text with these changes:
- front matter `version: keywords_v3`;
- the title input section reads `{source_title}` (the `T<index> <WORD>` listing, as v2's `{title}`) and is followed by `{hook_task}`;
- "What to pick" adds: "Hook lines (only when the Hook section asks for them): write them as asked; `best` is the index of the best line; `title_keyword` is an index into the words of that best line (uppercase, split on spaces). When the Hook section says to use the title as given, leave out `variants` and `best`, and `title_keyword` indexes the title above.";
- the output becomes `{"keywords": [<index>, ...], "variants": ["...", "..."], "best": <index>, "title_keyword": <index or null>}` with the note that `variants` and `best` are left out when not asked.

Add `"keywords_v3": {"released": "<build date>", "model_default": "claude-haiku-4-5", "notes": "keywords_v2 plus 2–3 hook lines in the drawn pattern and the best one's key word (ADR-50)."}` to `prompts/metadata.json`.

- [ ] **Step 4: Implement the stage**

In `captions.py`:
- `STAGE_VERSION = "3"` stays (today's); add `STAGE_VERSION_HOOKS = "4"` and `KEYWORDS_PROMPT_HOOKS = "keywords_v3"`, with `stage_version(settings)` and `keywords_prompt(settings)` choosing by `settings.hook_variants`.
- `run(..., pick=None)`: when `deps is not None and deps.settings.hook_variants`, the key uses `stage_version(...)` and adds `"hook": _hook_key(pick, manual_title)` = `f"manual:{sha256(manual_title)[:16]}"` when a title is given, else `f"{pick.pattern_id}@{pick.version}:{sha256(pick.data.model_dump_json())[:16]}"`, else `"none"`. With the flag off, the `extra` dict and the version are exactly today's.
- `pick_keywords` gains `pick` and `source_line` parameters. With the flag on it renders `keywords_v3` with `source_title` (today's `T<i>` listing) and `hook_task=render_task(pick, language, source_line)`, and parses with `_parse_v3`:
  - `KeywordsReply` as today, then for a non-control pick: `variants` and `best` required, `valid_lines(variants, pick.data.max_words)`, `0 <= best < len(variants)`, and `title_keyword` checked against `len(cleaned[best])`;
  - for a control or no pick: today's `_parse_keywords` against the source title.
- It returns `(Emphasis, HookResult)`: on success `settle(HookVariants(variants, best), pick, source_line, drawn=True)` (or `settle(None, pick, source_line, drawn=True)` for a control), and after two failures `Emphasis()` with `settle(None, pick, source_line, drawn=True)` (`fallback=True` for a non-control pick). With `manual_title`, the source line is that title, the pick is `None`, and the result is `HookResult(pattern_id=None, version=None, text=manual_title, manual=True)`.
- `compute()` builds the title card from `title_words(result.text)` (cleaned and upper-cased; `result.text` itself stays as written for `ContentItem.title`) and sets `CaptionFiles.hook = result` (flag on only).
- In `runner.py`, `PipelineStages.from_settings` loads `captions.keywords_prompt(settings)`; `producer_version` uses `captions.stage_version(settings)` and `captions.keywords_prompt(settings)`; `STAGE_VERSIONS["captions"]` stays "3" for the record, and `Versions.stages` in the metadata writes `captions.stage_version(settings)`.

- [ ] **Step 5: Run and see them pass**

Run: `uv run pytest -q tests/stages tests/test_prompts.py`
Expected: PASS.

- [ ] **Step 6: Check and record**

Run `scripts/check.sh --python`, then note the task. Ask `pipeline-reviewer` to review this task (STAGE_VERSION, cache key, `producer_version`, prompt version).

### Task 9: The pick in the clip step, and the result through render, package and enqueue

**Files:**
- Modify: `src/clipforge/stages/runner.py` (`clip(ctx, spec, transcript, pick=None)`), `src/clipforge/pipeline/steps.py` (`clip_step`), `src/clipforge/stages/package.py`, `src/clipforge/posting/enqueue.py` (`ClipFacts.from_rendered`, `from_packaged`)
- Test: `tests/pipeline/test_chain.py`, `tests/pipeline/test_recovery.py`, `tests/stages/test_package.py`, `tests/posting/test_enqueue.py`

**Interfaces:**
- Consumes: `clip_seed`, `pick` (Task 3); `captions.run(..., pick)` (Task 8); `items_for(..., rotation, flag_on)` (Task 5).
- Produces:
  - `clip_step` computes `pick(job.input.hooks, clip_seed(spec.source.source_hash, spec.start, spec.end, job.input.hooks))` when `deps.hook_variants` and `job.input.hooks` are set, else `None`, and passes it to `deps.stages.clip(..., pick=…)`;
  - `RenderedClip.hook = caps.hook`;
  - `PackagedClip.hook = HookStamp(...)` built by package from `RenderedClip.hook` and the job's rotation, and `PackagedClip.title = hook.text` when there is a non-fallback result;
  - `ClipFacts.hook: HookResult | None` from `RenderedClip.hook` and `PackagedClip.hook.result`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/pipeline/test_chain.py (add)
def test_every_item_is_stamped_and_matches_the_title_card(harness_on) -> None:
    job = harness_on.run_job(channel_input("realtalk"), rotation=two_pattern_rotation())
    for item in harness_on.items(job.job_id):
        assert item.hook_stamp is not None and item.title == item.hook_stamp.result.text   # as written
        assert item.hook_stamp.result.drawn
        assert item.hook_stamp.weights == weights_of(job.input.hooks)
        assert item.title.upper() in harness_on.title_card(item)

def test_stamp_uses_the_version_frozen_on_the_job(harness_on, db_lib) -> None:     # Review Focus 1
    job = harness_on.create(channel_input("realtalk"))          # freezes hp_q@1
    db_lib.edit("hp_q", sharper(), "v2", "web:mat", NOW)        # edited before the clip step runs
    harness_on.drain(job.job_id)
    assert {i.hook_stamp.result.version for i in harness_on.items(job.job_id) if i.hook_stamp.result.pattern_id == "hp_q"} == {1}

def test_pick_is_the_same_on_retry(harness_on) -> None:
    job = harness_on.run_job(channel_input("realtalk"), rotation=two_pattern_rotation(), fail_once="render")
    assert harness_on.llm_calls("captions") == len(job.clip_ids)        # retry hit the captions cache
```

```python
# tests/pipeline/test_recovery.py (add)
def test_resume_of_a_pre_hk_job_runs_control_mode(harness_on) -> None:    # Review Focus 2
    job = harness_on.failed_job_from_before_hk()      # JobInput without `hooks`, failed at clip
    harness_on.resume(job.job_id)
    items = harness_on.items(job.job_id)
    assert items and all(i.hook_stamp is None for i in items)
    assert all(i.title == c.title for i, c in zip(items, harness_on.candidates(job.job_id)))
```

```python
# tests/stages/test_package.py (add)
def test_metadata_carries_the_stamp(tmp_path) -> None:
    meta = package_case(tmp_path, hook=HookResult(pattern_id="hp_q", version=1, variants=["A", "B"],
                                                  chosen=1, text="B"), rotation=two_pattern_rotation())
    clip = meta.clips[0]
    assert clip.hook.result.text == "B" and clip.title == "B" and clip.hook.weights
```

`harness_on` is `tests/pipeline/harness.py`'s harness with `hook_variants=True`, a seeded `HookLibrary` on the test database and the fake LLM returning `V3_REPLY`; add `rotation=`, `fail_once=`, `items()`, `title_card()`, `llm_calls()` and `failed_job_from_before_hk()` helpers there.

- [ ] **Step 2: Run and see them fail**

Run: `uv run pytest -q tests/pipeline tests/stages/test_package.py tests/posting/test_enqueue.py`
Expected: FAIL.

- [ ] **Step 3: Implement**

- `clip_step`: compute the pick after loading `spec` (pure, so a retry computes the same one) and pass it on. `PipelineStages.clip` forwards it to `captions.run` and copies `caps.hook` onto the `RenderedClip`.
- `package`: build each `PackagedClip.hook` from `rendered.hook` and `job.input.hooks` (the same `_weights` helper as enqueue; move it to `hooks/rotation.py` as `weights_of(rotation) -> dict[str, float]` and use it in both places). Flag off: unchanged from Task 5 (`control_stamp`).
- `ClipFacts.from_rendered` reads `r.hook`; `from_packaged` reads `c.hook.result if c.hook else None`; `items_for` already does the rest (Task 5).

- [ ] **Step 4: Run and see them pass**

Run: `uv run pytest -q tests`
Expected: PASS.

- [ ] **Step 5: Check and record**

Run `scripts/check.sh --python`, then note the task.

### Task 10: Ranking, ratings and the weak-pattern rows

**Files:**
- Create: `src/clipforge/hooks/stats.py`, `src/clipforge/hooks/ratings.py`, `src/clipforge/hooks/needs.py`, `src/clipforge/hooks/digest.py`
- Modify: `src/clipforge/runtime.py` (register the needs provider and the digest providers)
- Modify: `src/clipforge/db/hooks.py` (the stats read), `src/clipforge/api/main.py` (`GET /admin/hooks/{id}/stats`, `PUT /admin/items/{id}/hook-rating`; `HookRow` gains `stats`), `src/clipforge/cli.py` (`hooks stats`)
- Test: `tests/hooks/test_stats.py`, `tests/hooks/test_ratings.py`, `tests/hooks/test_needs.py`, `tests/hooks/test_digest.py`, `tests/api/test_hooks_api.py`

**Interfaces:**
- Consumes: `content_items` stamps and verdicts; S2's `post_events` kinds `approved` and `reviewed` with person actors (S2 plan Task 6); `hook_ratings`.
- Produces:
  - `ItemOutcome(item_id, pattern_id, version, drawn: bool, fallback: bool, superseded: bool, decided: bool, posted: bool, rejected: bool, reviewed: bool, approved: bool, rating: int | None)` (one row per stamped item, read by `db/hooks.outcomes(account_id)`; `superseded` is true for an item with `superseded_by` or a `rejected` event whose reason starts with `superseded:`);
  - `Rate(k: int, n: int, low: float, high: float)` with `wilson(k, n, z=1.645) -> Rate`;
  - `PatternStats(pattern_id, items, fallback_rate, posted: Rate, rejected: Rate, approved: Rate, liked: Rate, verdict: Literal["likely_better","no_clear_difference","likely_worse","too_few"], by_version: dict[int, int])`;
  - `stats(outcomes: list[ItemOutcome], control_id: str | None) -> dict[str, PatternStats]`;
  - `WeakPattern(account_id, pattern_id, name, measure, k, n, suggested_weight)` and `weak(account_id, outcomes, weights, names, control_id) -> list[WeakPattern]`;
  - `rate(db, item_id: str, rating: Literal[1, -1], actor: str, now) -> None` (upsert + `rated` event);
  - `hooks/needs.py::HookWeakProvider(library: HookLibrary)`, S3's `Provider` protocol (S3 plan Task 6) with `kind = NeedsKind.hook_weak`: `rows(ctx, now)`, `get(ctx, subject, now)`, `evidence(ctx, subject)`, `act(ctx, subject, action, actor, now)` (actions `apply`, `open`), `done(ctx, subject)`; subject `<account_id>:<pattern_id>`;
  - `hooks/digest.py`: `weak_line(db, now) -> DigestLine | None` and `make_stale_freeze_line(running: Callable[[int], bool]) -> DigestProvider` (S2's `DigestProvider = Callable[[Database, datetime], DigestLine | None]`, #142);
  - `runtime.build_deps` passes `needs_providers=(HookWeakProvider(lib),)` and adds `weak_line` (and, once S3c's experiments repo is on `main`, the stale-freeze line) to the digest providers.

- [ ] **Step 1: Write the failing tests**

```python
# tests/hooks/test_stats.py
def test_wilson_90() -> None:
    r = wilson(3, 12)
    assert (r.k, r.n) == (3, 12) and r.low == pytest.approx(0.0996, abs=1e-3) and r.high == pytest.approx(0.5035, abs=1e-3)

def test_too_few_below_ten_decided() -> None:
    s = stats(outcomes("hp_a", decided=9, rejected=6) + outcomes("hp_c", decided=30, rejected=3), "hp_c")
    assert s["hp_a"].verdict == "too_few"

def test_likely_worse_on_rejects() -> None:
    s = stats(outcomes("hp_a", decided=20, rejected=12) + outcomes("hp_c", decided=40, rejected=4), "hp_c")
    assert s["hp_a"].verdict == "likely_worse"

def test_superseded_and_fallback_are_excluded_from_rates() -> None:
    rows = outcomes("hp_a", decided=10, rejected=0) + outcomes("hp_a", decided=5, rejected=5, superseded=True) \
         + outcomes("hp_a", decided=3, rejected=3, fallback=True)
    s = stats(rows, None)["hp_a"]
    assert s.rejected.n == 10 and s.rejected.k == 0 and s.fallback_rate == pytest.approx(3 / 13)

def test_pending_items_are_not_failures() -> None:
    s = stats(outcomes("hp_a", decided=10, rejected=1) + outcomes("hp_a", decided=0, pending=5), None)
    assert s["hp_a"].rejected.n == 10

def test_weak_suggests_half_the_weight() -> None:
    w = weak("realtalk-clips-en", outcomes("hp_a", decided=20, rejected=12) + outcomes("hp_c", decided=40, rejected=4),
             {"hp_a": 1.0, "hp_c": 1.0}, {"hp_a": "Contrarian", "hp_c": "Highlight title"}, "hp_c")
    assert [(x.pattern_id, x.measure, x.suggested_weight) for x in w] == [("hp_a", "rejected", 0.5)]

def test_only_drawn_items_count() -> None:
    rows = outcomes("hp_c", decided=12, rejected=0) + outcomes("hp_c", decided=30, rejected=30, drawn=False)
    assert stats(rows, "hp_c")["hp_c"].rejected.n == 12      # flag-off control stamps stay out

def test_control_is_never_weak() -> None:
    assert weak("realtalk-clips-en", outcomes("hp_c", decided=40, rejected=30), {"hp_c": 1.0}, {"hp_c": "x"}, "hp_c") == []
```

```python
# tests/hooks/test_ratings.py
def test_latest_rating_wins_and_each_is_logged(db, stamped_item) -> None:
    rate(db, stamped_item, 1, "web:mat", NOW)
    rate(db, stamped_item, -1, "web:mat", NOW)
    assert rating_of(db, stamped_item) == -1 and event_count(db, "rated") == 2

def test_rating_an_unstamped_item_is_a_hook_error(db, unstamped_item) -> None:
    with pytest.raises(HookError, match="no hook"):
        rate(db, unstamped_item, 1, "web:mat", NOW)
```

```python
# tests/api/test_hooks_api.py (add)
def test_stats_route_and_rating_route(client, seeded, stamped_item) -> None:
    assert client.put(f"/admin/items/{stamped_item}/hook-rating", headers=AUTH | ACTOR,
                      json={"rating": 1}).status_code == 200
    pid = pattern_of(stamped_item)
    assert client.get(f"/admin/hooks/{pid}/stats", headers=AUTH).json()["liked"]["k"] == 1
```

- [ ] **Step 2: Run and see them fail**

Run: `uv run pytest -q tests/hooks/test_stats.py tests/hooks/test_ratings.py tests/api/test_hooks_api.py`
Expected: FAIL.

- [ ] **Step 3: Implement**

- `wilson(k, n, z=1.645)`: the standard score interval; `n == 0` gives `Rate(0, 0, 0.0, 1.0)`.
- Measures over **drawn, settled, non-superseded, non-fallback** items (spec §5; superseded = `superseded_by` set or a reject with reason `superseded:<id>`): `posted` = posted ÷ decided; `rejected` = rejected ÷ decided; `approved` = approved ÷ reviewed (S2's counted decisions); `liked` = 👍 ÷ rated.
- `verdict` compares with the control on `rejected` (lower is better), then `approved` and `liked` (higher is better), each only when both sides have ≥ 10: likely worse when this pattern's interval is entirely on the bad side of the control's; likely better when entirely on the good side; otherwise no clear difference; `too_few` when no measure qualifies. The control's own verdict is `None`-equivalent (`no_clear_difference`) and it is never weak.
- `weak` returns one row per pattern whose verdict is `likely_worse`, naming the first failing measure, with `suggested_weight = round(weight / 2, 2)` (0 when the halved weight is under 0.1).
- `db/hooks.outcomes(account_id)` joins `content_items` (stamp columns, verdicts, `superseded_by`), `posts.posted_at`, `post_events` (`approved`, `reviewed` with non-`system:` actors, `superseded`) and `hook_ratings`.
- The `GET /admin/accounts/{id}/hooks` rows gain `stats: PatternStats`; `hooks stats <pattern>` prints the rates with intervals and the verdict.
- After S7 (not in this card): S7 adds `hold_3s` and `views_24h` medians with p25–p75 to `PatternStats`, over items past 48 h (spec §5).

- [ ] **Step 4: Run and see them pass**

Run: `uv run pytest -q tests/hooks tests/api`
Expected: PASS.

- [ ] **Step 5: The needs provider and the digest lines (extension points, #142, #147)**

```python
# tests/hooks/test_needs.py
def test_weak_pattern_is_a_digest_row(needs_ctx, weak_history) -> None:
    [row] = HookWeakProvider(needs_ctx.lib).rows(needs_ctx, NOW)
    assert (row.kind, row.subject, row.level) == ("hook_weak", "realtalk-clips-en:hp_a", "digest")
    assert row.href == "/act/hook_weak/realtalk-clips-en:hp_a"

def test_apply_sets_the_suggested_weight_with_the_tapping_actor(needs_ctx, weak_history) -> None:
    msg = HookWeakProvider(needs_ctx.lib).act(needs_ctx, "realtalk-clips-en:hp_a", "apply", "web:mat", NOW)
    assert "0.5" in msg and last_event(needs_ctx.db, "weight").actor == "web:mat"
    assert HookWeakProvider(needs_ctx.lib).done(needs_ctx, "realtalk-clips-en:hp_a").by == "web:mat"

def test_registered_through_build_deps(settings, fake_db) -> None:
    deps = build_deps(settings, **fakes(), db=fake_db)
    assert any(isinstance(p, HookWeakProvider) for p in deps.needs_providers)
```

```python
# tests/hooks/test_digest.py
def test_weak_line_names_the_pattern_and_suggestion(db, weak_history) -> None:
    line = weak_line(db, NOW)
    assert "Contrarian" in line.text and "0.5" in line.text and line.href == "/hooks?account=realtalk-clips-en"

def test_stale_freeze_line(db, open_freeze_for_experiment_12) -> None:
    line = make_stale_freeze_line(running=lambda experiment_id: False)(db, NOW)
    assert "experiment 12" in line.text
    assert make_stale_freeze_line(running=lambda experiment_id: True)(db, NOW) is None
```

Run: `uv run pytest -q tests/hooks/test_needs.py tests/hooks/test_digest.py` (FAIL first). Implement `HookWeakProvider` over `hooks.stats.weak` (one row per weak pattern, about 1 minute; `apply` calls `HookLibrary.set_weight(account, pattern, suggested, "suggested: likely worse than control on <measure>", actor, now)`; `open` returns the page link; `done` reads the pattern's last `weight` or `retired` event) and the two digest providers. Register them in `runtime.build_deps` through `needs_providers` and the digest's provider tuple. **Don't edit `needs/` or `dispatch/digest.py`.** If S3's needs registry or S2c's digest providers aren't on `main` yet, keep the providers in `hooks/` with their tests, skip the registration, and tell the coordinator which card registers them. Then rerun: PASS.

- [ ] **Step 6: Check and record**

Run `scripts/check.sh --python`, then note the task.

### Task 11: Re-render one item (G21)

**Files:**
- Create: `src/clipforge/hooks/rerender.py`
- Modify: `src/clipforge/pipeline/steps.py` (`Step.RERENDER`, `rerender_step`), `src/clipforge/app.py` (the Modal function), `src/clipforge/posting/actions.py` (`supersede`), `src/clipforge/posting/repo.py` and `src/clipforge/db/posting.py` (`set_verdict` takes an optional event `reason`; `superseded_by`; superseded items leave the eligible pick), the `admin` review router or `api/main.py` (S3's `POST /admin/review/{item}/rerender`, #619), `src/clipforge/db/hooks.py`
- Test: `tests/hooks/test_rerender.py`, `tests/pipeline/test_rerender_step.py`, `tests/posting/test_actions.py`, `tests/api/test_hooks_api.py`

**Interfaces:**
- Consumes: `PostingRepo`, `posting/actions.reject` (Dual-written); S2's `publishing:inflight:<ref>` key and `posts.state`; `captions.run(..., pick)` (Task 8); `render.run`; `HookLibrary` (pattern lookup).
- Produces:
  - `Step.RERENDER` with `STEP_TIMEOUT_S[Step.RERENDER]` = the clip step's;
  - `RerenderChoice = PatternChoice(pattern: str  # "<id>@<v>") | TitleChoice(title: str = Field(max_length=120))`;
  - `RerenderRefused(Exception)` with a user-safe message;
  - `request(deps: Deps, item_id: str, choice: RerenderChoice, actor: str, now: datetime, *, preview: bool = False) -> RerenderTicket{new_item_id: str, estimate_usd: float}`;
  - `rerender_step(deps: Deps, job_id: str, clip_id: str, ticket_key: str) -> None`;
  - S3's `POST /admin/review/{item}/rerender?preview=` (#619; `admin` only, `web` behind the bearer token until S3-1) → 202 `RerenderTicket` (409 with the reason when refused);
  - `posting/actions.supersede(posting: Posting, ref: str, new_ref: str, actor: str, now: datetime) -> None`: `posting.repo.set_verdict(ref, PostVerdict(kind="rejected", at=now), actor, reason=f"superseded:{new_ref}", superseded_by=new_ref)`, Dual-written; the Dict side records the verdict without a `RejectReason`, Postgres writes `superseded_by` and the `rejected` event with `data.reason`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/hooks/test_rerender.py
def test_refused_once_posted(deps, posted_item) -> None:
    with pytest.raises(RerenderRefused, match="already posted"):
        request(deps, posted_item, PatternChoice(pattern="hp_q@1"), "web:mat", NOW)

def test_refused_while_in_flight(deps, inflight_item) -> None:
    with pytest.raises(RerenderRefused, match="publishing"):
        request(deps, inflight_item, PatternChoice(pattern="hp_q@1"), "web:mat", NOW)

def test_second_rerender_request_is_refused_while_the_first_runs(deps, queued_item) -> None:   # Review Focus 4
    first = request(deps, queued_item, PatternChoice(pattern="hp_q@1"), "web:mat", NOW)
    with pytest.raises(RerenderRefused, match="already being re-rendered"):
        request(deps, queued_item, PatternChoice(pattern="hp_b@1"), "web:mat", NOW)
    assert first.new_item_id.endswith(":clip_01r1")

def test_stale_claim_is_freed_after_the_step_timeout(deps, queued_item) -> None:
    request(deps, queued_item, PatternChoice(pattern="hp_q@1"), "web:mat", NOW)
    later = NOW + timedelta(seconds=STEP_TIMEOUT_S[Step.RERENDER] + 5 * 60 + 1)
    t = request(deps, queued_item, PatternChoice(pattern="hp_b@1"), "web:mat", later)   # not refused
    assert t.new_item_id.endswith(":clip_01r1")

def test_preview_spawns_nothing_and_gives_the_estimate(deps, queued_item) -> None:
    t = request(deps, queued_item, TitleChoice(title="He quit at 40"), "web:mat", NOW, preview=True)
    assert deps.spawner.spawned == [] and 0.005 <= t.estimate_usd <= 0.02

def test_unknown_pattern_version_is_refused(deps, queued_item) -> None:
    with pytest.raises(RerenderRefused, match="no pattern"):
        request(deps, queued_item, PatternChoice(pattern="hp_q@9"), "web:mat", NOW)
```

```python
# tests/pipeline/test_rerender_step.py
def test_new_item_replaces_the_old_one_and_verify_stays_zero(harness_on, queued_item) -> None:
    t = request(harness_on.deps, queued_item, PatternChoice(pattern="hp_q@1"), "web:mat", NOW)
    harness_on.drain_rerender()
    old, new = harness_on.item(queued_item), harness_on.item(t.new_item_id)
    assert old.superseded_by == new.id and harness_on.status(old.id) == "rejected"
    assert new.hook_stamp.result.pattern_id == "hp_q" and new.score == old.score
    assert harness_on.verify_differences() == 0
    assert harness_on.llm_calls("transcribe") == 0 and harness_on.llm_calls("highlights") == 0

def test_title_choice_is_manual(harness_on, queued_item) -> None:
    t = request(harness_on.deps, queued_item, TitleChoice(title="He quit at 40"), "web:mat", NOW)
    harness_on.drain_rerender()
    r = harness_on.item(t.new_item_id).hook_stamp.result
    assert r.manual and r.pattern_id is None and r.text == "He quit at 40"

def test_supersede_writes_reason_and_column_through_actions(posting_dual, queued_item) -> None:
    supersede(posting_dual, queued_item, queued_item + "r1", "web:mat", NOW)
    ev = last_post_event(posting_dual, queued_item)
    assert (ev.kind, ev.data["reason"], ev.actor) == ("rejected", f"superseded:{queued_item}r1", "web:mat")
    assert sql_item(posting_dual, queued_item).superseded_by == queued_item + "r1"
    assert dict_verdict(posting_dual, queued_item).reason is None        # verify stays at 0

def test_crash_between_insert_and_supersede_is_finished_by_the_retry(harness_on, queued_item) -> None:
    t = request(harness_on.deps, queued_item, PatternChoice(pattern="hp_q@1"), "web:mat", NOW)
    harness_on.fail_once("supersede")                   # raises after repo.add, before supersede
    harness_on.drain_rerender()                         # the first attempt fails, the retry finishes
    assert harness_on.item(queued_item).superseded_by == t.new_item_id
    assert harness_on.item_count_with_prefix(queued_item) == 2     # old + one new, no duplicate
    assert harness_on.verify_differences() == 0

def test_rerender_of_a_rerender_is_r2(harness_on, queued_item) -> None:
    first = request(harness_on.deps, queued_item, PatternChoice(pattern="hp_q@1"), "web:mat", NOW)
    harness_on.drain_rerender()
    second = request(harness_on.deps, first.new_item_id, TitleChoice(title="He quit at 40"), "web:mat", NOW)
    assert second.new_item_id.endswith(":clip_01r2")

def test_superseded_items_leave_counts_and_the_pick(harness_on, queued_item) -> None:
    request(harness_on.deps, queued_item, PatternChoice(pattern="hp_q@1"), "web:mat", NOW)
    harness_on.drain_rerender()
    assert queued_item not in harness_on.eligible_refs()
```

- [ ] **Step 2: Run and see them fail**

Run: `uv run pytest -q tests/hooks/test_rerender.py tests/pipeline/test_rerender_step.py`
Expected: FAIL.

- [ ] **Step 3: Implement**

- `request()`:
  1. load the item (404 if missing) and its record; refuse if it is superseded, any platform has `posted_at`, any `posts.state` is past `pending`, or `publishing:inflight:<ref>` exists;
  2. resolve the choice (`HookLibrary` lookup of `<id>@<v>` that fits `clips`, or the title); the **base** is the item's clip id without any `r<n>` suffix, and `N` = 1 + the highest `r<n>` among the base's items, so a re-render of `clip_01r1` is `clip_01r2`, never `clip_01r1r1`;
  3. estimate = the captions call (`settings.prices.llm_usd` over 1.5K in and 200 out) + one render (the job's mean render cost per clip from its `costs`, else $0.01);
  4. with `preview`, return the ticket;
  5. otherwise claim `rerender:<item_id>` in the Dict with `skip_if_exists=True`, store the ticket under the claim key (choice, actor, `N`, **`at`**), write a `rerendered` event, and spawn `Step.RERENDER` with `(job_id, clip_id, ticket_key)`. When the claim is taken, read its ticket: if `at` is older than `STEP_TIMEOUT_S[Step.RERENDER]` + 5 minutes (the attempt died after its retries ran out), the claim is stale, so overwrite it and go on; otherwise refuse "already being re-rendered".
- `rerender_step` (Modal-free in `steps.py`; `app.py` adds the function with the clip step's image, timeout and `Retries(max_retries=2)`):
  1. load the ticket, the job, the clip's `ClipSpec` and the cached transcript;
  2. build the `HookPick`, or pass the given title as `manual_title` (Task 8: its own cache key, `manual=True`, `pattern_id=None`);
  3. run the clip pipeline (`deps.stages.clip(ctx, spec, transcript, pick=…)`) under clip id `<clip_id>r<N>` for its output paths;
  4. insert the new `ContentItem` with **`posting.repo.add(item, platforms)` directly**, not `enqueue.enqueue`: `enqueue` skips it because `queue.overlaps` still sees the old item, which isn't rejected yet. `add` is idempotent by id, so a retry re-adds nothing. The item keeps the old item's platforms, score, episode and `queued_at` (its place in the queue), carries the stamp from the job's rotation, and takes `title` = the given title or the best line as written. Then call `posting/actions.supersede(posting, old_ref, new_ref, actor, now)`, which rejects the old item with reason `superseded:<new id>` and sets `superseded_by` (no other `post_events` writer). Both writes are idempotent, so a crash between them is finished by the step's retry;
  5. release the `rerender:<item_id>` claim. On a `PermanentError` ("the source is gone"), release the claim and raise an ops alert.
- `db/posting`'s eligible pick excludes items with `superseded_by` set (`posting/queue.py` derives "rejected" for them through the verdict, as today). S2's ladder and demotion counts and S3c's reject-rate metric exclude rejects with reason `superseded:<id>` (spec §10.4, §10.6): if those modules are on `main`, add the exclusion with a test there; otherwise tell the coordinator.
- **`metadata.json` is not rewritten** (spec §3.2): the new files go under `<job_id>/rerender/<clip_id>r<N>/`, and the record is the new item, `superseded_by` and the `rerendered` hook event.

- [ ] **Step 4: Run and see them pass**

Run: `uv run pytest -q tests`
Expected: PASS.

- [ ] **Step 5: Check and record — checkpoint HK-2**

1. Run the full `scripts/check.sh`.
2. Ask `pr-reviewer`, `pipeline-reviewer` (captions, render inputs, `producer_version`), `migration-reviewer` (Task 11 changes `posting/repo.py` and `db/posting.py`: the Dual write of `supersede`, `posting verify`) and `security-reviewer` (the new routes, LLM text into ASS) to review.
3. Update `docs/ARCHITECTURE.md` (captions: hook variants; the flag; re-render), `.env.example` (`HOOK_VARIANTS`), `docs/ops/secrets.md` (the `HOOK_VARIANTS` row: not a secret, a setting in `clipforge-secrets`; missing = off), `docs/studio/04-roadmap.md` and `ROADMAP.md`.
4. Write the report.
5. Suggested commit: `NNN: hk-2: keywords_v3 hook variants behind HOOK_VARIANTS, ranking, ratings, re-render`.

**Owner deploy steps (HK-2).**

0. **The #144 check:** no other code card is on `main` undeployed (`docs/ops/deploys.md` against `git log`). Note which of cards 015, 016, 022, 023 and 024 are deployed: they decide which fallbacks of the Global Constraints' table are in force.
1. `uv run modal run src/clipforge/app.py::db_doctor` (the hooks head, unchanged: HK-2 has no migration), then `scripts/deploy.sh --dry-run`, then `scripts/deploy.sh --reason "HK-2: hook variants (flag off)"`, outside the blackout. Clip output is still unchanged (flag off).
2. Check that no other clips stage or prompt bump is due this week (#439); if one is, ship them together instead.
3. Add `HOOK_VARIANTS=true` to `clipforge-secrets` with `docs/ops/secrets.md`'s add-only procedure, then `scripts/deploy.sh --reason "HOOK_VARIANTS on"`. Every clips account's `producer_version` changes once: expect ADR-49's 5-item window per account (about 15 reviews).
4. Clip one episode. Its items' title cards show rewritten lines; `metadata.json` has `hook.result.variants`; `uv run clipforge hooks list realtalk-clips-en` shows items per pattern.
5. Try `uv run clipforge hooks stats <pattern>` and one re-render from the API (`POST /admin/review/<item>/rerender?preview=true`, then without `preview`).

**Rollback (HK-2):**
- The variants only: set `HOOK_VARIANTS=false` (or remove it) and redeploy. Captions use their old cache keys again and stamps go back to the control. **`producer_version` returns to its previous value, and that is a change too:** S2 counts the producer window per version (`WindowCounts.producer`, ADR-49), so an account opens a new 5-item window only if it has fewer than 5 counted review decisions under the old version. Accounts reviewed under the old version for at least 5 items see no window; an account created after the flip, or one with no counted decisions yet (before S2b), gets one. Turning the flag on again later returns to the variants' version, whose decisions are already counted.
- The whole part: a revert deploy (dry run first). No migration in HK-2.

---

# Part HK-3: the interim page

Starts when HK-2 and card 022 (S3-1: the `admin` client and its route-handler pattern) are deployed (#144). If S3c's account workspace lands first, skip this part: S3c's Hooks tab is built on the same routes, and `/hooks?account=` redirects there.

### Task 12: `/hooks?account=<id>` in `web/`

**Files:**
- Create: `web/app/(app)/hooks/page.tsx`, `web/lib/hooks.ts`, the proxy handlers under `web/app/api/cf/` that S3 uses for admin calls (follow its pattern exactly)
- Modify: `web/lib/upstream.ts` only through the helpers S3 adds; the link-contract test (S3 §7.10)
- Test: `web/tests/unit/hooks.test.ts`, `web/e2e/hooks.spec.ts`

**Interfaces:**
- Consumes: `GET /admin/accounts/{id}/hooks`, `POST /admin/hooks`, `PUT /admin/hooks/{id}`, `POST /admin/hooks/{id}/approve|retire|share`, `PUT /admin/hooks/{id}/weight`, `PUT /admin/items/{id}/hook-rating` (Tasks 6, 10), through the generated client in `web/lib/api`.
- Produces: the page at `/hooks?account=<id>`; `hookRows(view) -> Row[]` and `suggestion(row) -> {weight, label} | null` in `web/lib/hooks.ts`.

- [ ] **Step 1: Write the failing tests**

```ts
// web/tests/unit/hooks.test.ts
import { hookRows, suggestion } from "@/lib/hooks";
import { libraryView } from "./fixtures/hooks";

test("rows sort approved first, then by weight", () => {
  expect(hookRows(libraryView()).map((r) => r.name)).toEqual(["Open question", "Highlight title", "Contrarian"]);
});
test("a weak pattern suggests half its weight", () => {
  expect(suggestion(hookRows(libraryView())[2])).toEqual({ weight: 0.5, label: "likely worse than control on rejects" });
});
test("frozen view marks every row", () => {
  expect(hookRows(libraryView({ frozen_by: 1 })).every((r) => r.frozen)).toBe(true);
});
```

```ts
// web/e2e/hooks.spec.ts (MOCK_API, phone and desktop projects)
test("the hooks page shows the library and the freeze notice", async ({ page }) => {
  await page.goto("/hooks?account=realtalk-clips-en");
  await expect(page.getByRole("table")).toContainText("Highlight title");
  await expect(page.getByText(/changes apply when experiment/)).toBeHidden();
});
test("an unknown account shows not found", async ({ page }) => {
  await page.goto("/hooks?account=nope");
  await expect(page.getByText("not found")).toBeVisible();
});
```

- [ ] **Step 2: Run and see them fail**

Run: `npm --prefix web run test -- hooks` and `npm --prefix web run e2e -- hooks`
Expected: FAIL.

- [ ] **Step 3: Implement**

The page (server component for the first load, TanStack Query for refresh, no polling while hidden):
- a table: pattern, version, status, scope, weight (❄ when frozen), items, posted and reject rates, 👍 share, verdict;
- per pattern, the approval rate as a dot with its 90% interval and a direct label (the `dataviz` method), plus a "table view" toggle;
- actions: Edit (a form writing v+1), Approve, Retire, Share to blueprint, Weight (pre-filled with `suggestion()`; reason required);
- recent items with 👍/👎;
- the freeze notice when `frozen_by` is set;
- states: not found, empty library ("nothing rotates: approve a pattern"), API unavailable.

Add `/hooks?account=<id>` to the link-contract test.

- [ ] **Step 4: Run and see them pass**

Run: `npm --prefix web run check` and `npm --prefix web run e2e -- hooks`
Expected: PASS.

- [ ] **Step 5: Check and record — checkpoint HK-3**

1. Run the full `scripts/check.sh --e2e`.
2. Ask `pr-reviewer` and `security-reviewer` (auth on the new handlers) to review.
3. Write the report.
4. Suggested commit: `NNN: hk-3: interim hooks page`.

**Owner steps (HK-3):**
0. **The #144 check:** no other code card is on `main` undeployed (`docs/ops/deploys.md` against `git log`), and card 022 is deployed.
1. `uv run modal run src/clipforge/app.py::db_doctor` (the head is unchanged; HK-3 has no migration).
2. The Vercel deploy as runbook §5b (no Modal deploy). Open `/hooks?account=realtalk-clips-en` on the phone and the laptop.

**Rollback (HK-3):** revert the merge; Vercel redeploys the previous build.

---

## Deployable steps and coverage

| Step | Tasks | Deployable alone | What the owner sees |
|---|---|---|---|
| HK-1 | 1–6 | yes (after cards 010 and 014) | `hooks list`, control stamps; clips unchanged |
| HK-2 | 7–11 | yes (after HK-1); the flag flip is a separate redeploy | rewritten title cards, stats, ratings, re-render |
| HK-3 | 12 | yes (after S3's admin client) | the Hooks page |

| 04's HK item | Tasks |
|---|---|
| Pattern versions, append-only | 2, 4 |
| Item stamping (`hook_pattern_id@version` and the weights in force) | 5, 9 |
| 2–3 variants per item in the clips producer, one Haiku call (about $0.0025) | 7, 8 |
| The captions prompt bump opens ADR-49's window (released behind the flag) | 8, HK-2 owner steps |
| Weighted rotation, frozen during experiments | 3, 4 |
| Ranking before S7 (👍/👎, approval and reject rates) | 10 |
| Ranking after S7 (3-second hold, views at 24 h) | 10 (S7 fills the measures; spec §5) |
| Admin routes and the Hooks tab | 6, 10, 11, 12 (S3c's tab reuses them) |

| S3 dashboard spec §8.5 item | Tasks |
|---|---|
| 1. Pattern versions, drafts from + Hook idea, share, seeds | 2, 4, 6 |
| 2. Item stamping and `metadata.json` | 5, 9 |
| 3. Variants in producers (clips now; story's interface) | 7, 8, 9 |
| 4. Rotation and the freeze | 3, 4 |
| 5. Ranking before S7, `hook_weak` digest line | 10 |
| 6. Ranking after S7 | 10 (S7) |
| 7. Surfaces (routes, the interim page) | 6, 10, 11, 12 |
| 8. Tests (append-only, every item stamped, frozen weights, rule 5, cost) | 2, 4, 8, 9 |
| G21 re-render (coordinator) | 11 |

| Coordinator review of checkpoint A (2026-10-03) | Where |
|---|---|
| 1. One re-render path: S3's `POST /admin/review/{item}/rerender` (#619) | Task 11; Global Constraints |
| 2. Every path under `/admin` | Tasks 6, 10, 11; Global Constraints |
| 3. `HookWeakProvider` through `build_deps(needs_providers=…)`, digest lines through `DigestProvider`s, the stale-freeze line | Task 10 Step 5 |
| 4. Integer experiment ids; freeze a no-op without a library | Tasks 1, 2, 4 |
| 5. CLI routes in `cli_router` (move at S3-5b), dashboard-only routes on `admin` | Global Constraints; Task 6; spec §10.5 |
| 6. A manual title in the cache key (`manual:<sha16>`) | Task 8 |
| 7. Superseded = a reject with reason `superseded:<new id>` through `posting/actions.supersede`; excluded from S2's counts and S3c's reject rate | Task 11; Task 10 (`ItemOutcome.superseded`) |
| 8. `ContentItem.title` as written; only the title card upper-cased | Tasks 5, 8, 9 |
| 9. `HookResult.drawn`; stats over drawn items only | Tasks 1, 5, 7, 8, 10 |
| 10. `hook_stamp` is the title card, not `ContentItem.hook` | spec §1 |
| 11. `control` stored once, unversioned | Tasks 1, 3, 4 |
| 12. Re-renders not in `metadata.json` | Task 11; spec §3.2 |
| 13. "No promises" in Number + stakes and Bold claim | Task 4 |
| 14. The report accounts for every coordinator note | `docs/reports/020-hk-2026-10-02.md` |
