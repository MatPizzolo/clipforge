# Studio S3: dashboard v1, implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the dashboard v1 in six deployable checkpoints, one card each:
- **S3-1:** the `admin` endpoint, S3's migration and Settings.
- **S3-2:** "needs me", Home and `/act`.
- **S3-3:** Review and Calendar.
- **S3-4:** Produce, Jobs and Sources.
- **S3-5:** Results → Costs, Compare and the account read view.
- **S3-5b:** the bridges' retirement and the CLI cut-over, each after its 7-day wait (#623).

**Architecture:**
- **One route table, two mounts.** `create_app(ctx, surface)` is mounted twice:
  - `web` (public, `API_TOKEN`) keeps today's routes, the webhooks and the CLI's `/admin/*`;
  - `admin` (`@modal.asgi_app(requires_proxy_auth=True)`, `ADMIN_API_TOKEN`) adds S3's routers.
- **Vercel's route handlers are the only callers of `admin`.** They send the proxy pair, the bearer and `X-Clipforge-Actor: web:<login>`. `web/` never touches the database.
- **"Needs me" is derived on read** by a provider registry. Actions dispatch to the services that already own each write (`posting/actions.py`, S2's review and autopilot services, `service.resume_job`, the new `produce/batches.py`).
- **The router owns no state** except `needs_log`.

**Tech Stack:**
- Python 3.12 (`uv`), pydantic v2, SQLAlchemy 2 Core + psycopg 3, Alembic, FastAPI, Modal (`app.py` only), pytest with the local Postgres fixture (`tests/dbfixture.py`).
- Next.js 16 App Router, TypeScript, Auth.js (one owner), TanStack Query, the hey-api client and zod schemas generated from `web/openapi.json`, Vitest, Playwright on the mock API (phone and desktop projects).

**Spec:** [docs/superpowers/specs/2026-10-01-studio-s3-dashboard-design.md](../specs/2026-10-01-studio-s3-dashboard-design.md). §1–§10 are card 009's design; **§11 is the delta after S2's plan, and it wins where they differ.** Read §11 with this plan; section numbers below (§N) are the spec's. The S2 plan ([2026-10-02-studio-s2.md](2026-10-02-studio-s2.md)) defines every S2 module this plan calls.

## Global Constraints

- **Workflow:**
  - Each checkpoint is its own card (prefix and log range assigned by the coordinator). **Sessions never commit, push, deploy, stop the app or change secrets.**
  - Each task's last step is "check and record": `scripts/check.sh` green, and the task noted in the card's report. The owner commits at the card's checkpoint.
- **Landing order:**
  - **Gates are on deploys, not merges (#623).** Every deploy ships all of `main`. If card 014 were merged but not deployed, S3-1's `alembic upgrade head` would also apply 0002, and its deploy would swap `posting_tick` for the dispatcher without S2a's owner checks.
  - **S3-1 starts after card 010 is done and card 014 (S2a) is deployed with its owner steps done**, so `autopilot` exists and S3's migration numbers after 0002. The same rule holds for any S3 task that needs S2b or S2c: that card is deployed and its owner steps are done.
  - S3-2 to S3-5b follow in order, each after the previous one is deployed.
  - **Every S3 owner deploy starts with the pre-deploy check:** no other code card is on `main` undeployed (compare `docs/ops/deploys.md` with `git log`), and `uv run modal run src/clipforge/app.py::db_doctor` shows the expected head before any `alembic upgrade head`.
  - A task that calls an S2b or S2c module (the review service, `open_problems`, the ladder) checks that the module is on `main`. If it isn't, the task does the part that doesn't need it and the report names the follow-up (§11.1 "Providers and landing order").
  - **Never import a module that isn't on `main`.**
- **Python:**
  - `uv` only. New dependencies: none.
  - **Only `src/clipforge/app.py` imports `modal`.** Stage modules are untouched.
- **Contracts:** change in `models.py` first (CLAUDE.md rule 2). Every new route's request and response is a pydantic model, so OpenAPI and the generated client carry it.
- **OpenAPI:**
  - every route change regenerates `web/openapi.json` (the export now uses the `admin` surface, Task 1) and the client (`npm --prefix web run gen`) in the same task;
  - `scripts/check.sh`'s `openapi contract` and `web gen:check` lines enforce it.
- **One writer per table, column group or key** (ADR-14, ADR-41):

  | Writer | Writes |
  |---|---|
  | `needs/router.py` | `needs_log` |
  | `settings_service.py` | `settings` |
  | `produce/batches.py` | `batches` |
  | `posting/actions.pin` | `content_items.queue_pin`, its `pinned`/`unpinned` events |
  | `ops.py` | `alert:msg:<row id>` |
  | S2's writers | everything S2's plan lists; S3 only calls them |

- **Actors:**
  - every write on `admin` requires `X-Clipforge-Actor`, validated by `posting/actions.web_actor` (400 otherwise);
  - S3 adds no new actor forms; `system:<component>` stays S2's.
- **Migrations:**
  - S3's one migration takes **the next number after `main`'s head when S3-1 lands** (#620: S2a's 0002 first, then whichever of the hooks build, S3 and S3c lands next, one at a time);
  - it moves `EXPECTED_HEAD` in `src/clipforge/db/doctor.py` in the same change;
  - expand-only; `0001` is frozen;
  - the plan writes it as `alembic/versions/NNNN_s3.py`; the card replaces `NNNN` at landing.
- **The Dict stays current until S1 Task 23.** Every posting write goes through `posting/actions.py` and `PostingRepo` (Dual). The one exception is `queue_pin`, which is Postgres-only and excluded from `posting verify` on purpose (#621).
- **Spend values:**
  - batch lines and monthly caps come only from S2's `autopilot` row (`batch_line_usd`, `monthly_cap_usd`);
  - `settings` holds the attention budget, the fleet cap, the payout-program thresholds and the fixed subscriptions list (#621);
  - **caps are shown, never enforced** (ADR-48, #435).
- **`web/`:**
  - Server route handlers under `web/app/api/cf/**` call `admin` through `web/lib/upstream.ts`, the only module that reads `ADMIN_API_URL`, `ADMIN_API_TOKEN`, `MODAL_PROXY_KEY` and `MODAL_PROXY_SECRET`.
  - Upstream bodies, URLs and tokens never reach a response or a log line (S3a spec §5).
  - Client components fetch only `/api/cf/**`.
  - `MOCK_API=1` serves fixtures (`web/lib/mocks.ts`) and is refused on Vercel production (`mockGuard.ts`).
- **Polling** (#616): Home and Review every 15 s; `/act` on focus and after each action; nothing while the tab is hidden (`web/lib/polling.ts`).
- **Shared states:** every page has loading (skeletons in the final layout), error (names what failed and what still works), stale (`StaleNote`) and empty (says what fills it and what unlocks it), §7.
- **Security** (rule 8):
  - a missing `ADMIN_API_TOKEN` answers 503 on `admin`, never runs open;
  - tokens are compared with `hmac.compare_digest`;
  - `admin` never mounts the public routes, and `web` never mounts S3's routers;
  - `security-reviewer` reviews S3-1, S3-4 and S3-5b (#618).
- **Secrets:**
  - added with the `docs/ops/secrets.md` dashboard procedure, never `modal secret create --force`;
  - Vercel variables are set by the owner in the Vercel dashboard (runbook §5b).
- **Every owner deploy:** `scripts/deploy.sh --dry-run` first, then the deploy outside the blackout (runbook §1).
- **Tests:**
  - DB tests use the `db` fixture and **fail, never skip**, without Postgres;
  - routes are tested on both surfaces where mounted;
  - Vitest for `web/lib` units, Playwright (`web/e2e/`) on the mock API at phone and desktop sizes;
  - network calls are mocked (`tests/bot/fakes.py`, FastAPI `TestClient`).
- **Account ids in tests:** `realtalk-clips-en`, `founder-tapes-en`, `hombre-en-construccion-es`.

## Review Focus

The five conditions the spec implies but no task's main tests exercise, most likely first. Each has its pinning test in the owning task.
1. **The same row acted on twice at once** (an Approve tapped in Telegram while the dashboard's Approve is in flight, or two dashboard tabs). The owner expects one effect and the second surface showing "already done by … at …", not an error or a second write. *Pinned in Task 8* (`test_second_action_returns_already_done`) and *Task 16* (`test_double_approve_creates_jobs_once`).
2. **A Telegram Open link to a row that no longer exists** (the job was resumed and finished, the source was edited, the item was deleted). The owner expects `/act` to say "isn't in the list any more; nothing was changed", never a blank page or a 500. *Pinned in Task 8* (`test_detail_of_vanished_row_is_gone_not_500`) and *Task 11* (Playwright `act shows not found for an unknown id`).
3. **`admin` is cold or Neon is asleep when the owner opens Home on the phone** (first request after hours idle; Modal cold start plus Neon wake can pass 10 s). The owner expects skeletons, then the data, with no "API unavailable" before `UPSTREAM_TIMEOUT_MS`. *Pinned in Task 5* (`upstream waits through a slow first response`).
4. **A dashboard action while the brake is on, or during the outage flag** (e.g. move to the front, or approve a batch while `posting:outage` is set). The owner expects the action recorded and the page saying the brake is on, with nothing sent. *Pinned in Task 12* (`test_pin_while_braked_records_and_sends_nothing`) and *Task 8* (`test_outage_row_first_when_flag_set`).
5. **A subject id with `:` or other characters in the URL** (`publish_failed` subjects are `<item>:<platform>`; job ids have `-`). The owner expects the Open link to land on the right row. *Pinned in Task 8* (`test_subject_with_colon_round_trips`) and *Task 11* (the link-contract test).

## File map

| Path | New/changed | Responsibility |
|---|---|---|
| `src/clipforge/models.py` | changed | S3 contracts (Tasks 1, 6, 9, 12, 16, 19, 20) |
| `src/clipforge/config.py` | changed | `admin_api_token` |
| `src/clipforge/api/main.py` | changed | `create_app(ctx, surface)`; surface-aware token; public routes only on `web`; includes the admin routers on `admin` |
| `src/clipforge/api/admin/__init__.py` | new | `admin_routers(ctx) -> list[APIRouter]` |
| `src/clipforge/api/admin/settings.py`, `needs.py`, `fleet.py`, `posting.py`, `review.py`, `produce.py`, `results.py`, `accounts.py` | new | one router per area (S3c and the hooks build add theirs) |
| `src/clipforge/api/admin/deps.py` | new | `require_web_actor`, `database()` |
| `src/clipforge/app.py` | changed | the `admin` asgi function |
| `alembic/versions/NNNN_s3.py` | new | S3's migration (§11.8) |
| `src/clipforge/db/tables.py`, `db/doctor.py` | changed | tables; `EXPECTED_HEAD` |
| `src/clipforge/db/needs.py`, `db/settings.py`, `db/batches.py` | new | SQL behind the three writers |
| `src/clipforge/db/posting.py` | changed | `queue_pin` read into `PostRecord.pinned_at`; `set_pin` |
| `src/clipforge/settings_service.py` | new | studio settings with defaults |
| `src/clipforge/needs/__init__.py`, `registry.py`, `providers.py`, `router.py`, `attention.py` | new | rows, providers, actions, the meter |
| `src/clipforge/accounts/runway.py` | new | §3.3's runway |
| `src/clipforge/fleet.py` | new | scoreboard, slots, compare, overview, activity (read models) |
| `src/clipforge/produce/__init__.py`, `produce/batches.py`, `produce/estimate.py` | new | the batch planner |
| `src/clipforge/results.py` | new | the costs report |
| `src/clipforge/posting/actions.py` | changed | `pin` |
| `src/clipforge/posting/repo.py`, `posting/queue.py`, `posting/migrate.py` | changed | `set_pin` on the protocol; `pick_next` pins; verify excludes pins |
| `src/clipforge/ops.py` | changed | `row_id`, `alert:msg:<row id>`, `mark_done` |
| `src/clipforge/review/cards.py`, `dispatch/digest.py` | changed | Open ↗ to `/act`; `EXISTING_PAGES` grows |
| `src/clipforge/bot/commands.py` | changed | `/clip`, `/status <id>`, `/resume` retire (S3-5b) |
| `src/clipforge/cli.py` | changed | the CLI cut-over to `admin` (S3-5b) |
| `scripts/export_openapi.py` | changed | export the `admin` surface |
| `web/lib/upstream.ts`, `web/lib/types.ts`, `web/lib/mocks.ts`, `web/lib/polling.ts` | changed | the four env vars, actor header, generic `call`, mocks per route |
| `web/lib/actor.ts` | new | the session's GitHub login as `web:<login>` |
| `web/app/api/cf/**` | new and changed | one handler per route the pages call |
| `web/app/(app)/page.tsx`, `act/[kind]/[subject]/page.tsx`, `review/page.tsx`, `calendar/page.tsx`, `produce/page.tsx`, `sources/**`, `results/page.tsx`, `accounts/page.tsx`, `accounts/[id]/page.tsx`, `settings/page.tsx` | new and changed | pages |
| `web/components/home/**`, `act/**`, `review/**`, `produce/**`, `results/**`, `accounts/**` | new | page components |
| `web/components/nav.ts` | changed | §6's sidebar and phone tabs |
| `web/e2e/links.spec.ts`, `home.spec.ts`, `act.spec.ts`, `review.spec.ts`, `produce.spec.ts`, `results.spec.ts`, `accounts.spec.ts` | new | Playwright, phone and desktop |
| `web/tests/unit/*.test.ts` | new and changed | Vitest |
| `tests/api/admin/test_*.py`, `tests/needs/`, `tests/produce/`, `tests/test_fleet.py`, `tests/test_results.py`, `tests/test_settings_service.py` | new | pytest |
| `.env.example`, `web/README.md`, `docs/ops/secrets.md`, `docs/studio/11-owner-runbook.md` §5b, `docs/ARCHITECTURE.md`, `ROADMAP.md`, `docs/studio/04-roadmap.md`, `CLAUDE.md` | changed | docs at each checkpoint (each card's scope) |

---

# Part S3-1: the `admin` endpoint, the migration, Settings

### Task 1: `create_app(ctx, surface)` and the admin token

**Files:**
- Modify: `src/clipforge/config.py`, `src/clipforge/api/main.py`, `scripts/export_openapi.py` (export `surface="admin"`)
- Create: `src/clipforge/api/admin/__init__.py`, `src/clipforge/api/admin/deps.py`
- Test: `tests/api/admin/test_surfaces.py`

**Interfaces:**
- Produces:
  - `Settings.admin_api_token: SecretStr | None = None` (env `ADMIN_API_TOKEN`);
  - `Surface = Literal["web", "admin"]`;
  - `create_app(ctx: ApiContext, surface: Surface = "web") -> FastAPI`;
  - `admin_routers(ctx: ApiContext) -> list[APIRouter]` (empty in this task; each later task appends its router);
  - `require_web_actor(x_clipforge_actor: str | None = Header(None)) -> str`, which returns `web:<login>` or raises 400.
- Mounting rules:
  - **the CLI's routes go into their own router**, `cli_router(ctx, write_actor: Callable[..., str]) -> APIRouter`, so S3-5b's cut-over is a mount change. They are `/jobs` (POST, GET, resume), `/jobs/backfill`, `/accounts` (GET, POST, PATCH), `/sources` (GET, POST, PUT, events, submissions), `/posting`, `/posting/rebuild|import|verify|restore`, and S2's `/admin/*` (autopilot, policy dry-run, publisher check, links). Until S3-5b it is mounted on both surfaces;
  - **on `admin`, every write in that router requires `require_web_actor`** (S1's `POST /accounts`, `PATCH /accounts/{id}`, `POST /sources`, `PUT /sources/{id}`, and S2's writes); on `web` they keep today's optional `actor` header for the CLI;
  - `/telegram/webhook`, `/jobs/{id}/download`, `/webhooks/upload-post`, `/media/{item}.mp4`, `/go/{slug}`: `web` only;
  - `admin_routers(ctx)`: `admin` only.
- Token: `web` checks `API_TOKEN`; `admin` checks `ADMIN_API_TOKEN`. Missing → 503 "<NAME> is not configured"; wrong → 401.

- [ ] **Step 1: Write the failing tests**

```python
# tests/api/admin/test_surfaces.py
import pytest
from fastapi.testclient import TestClient
from clipforge.api.main import ApiContext, create_app
from tests.bot.fakes import make_settings

WEB = {"Authorization": "Bearer t0ken"}
ADMIN = {"Authorization": "Bearer adm1n"}

def client(tmp_path, surface, **kw) -> TestClient:
    settings = make_settings(tmp_path, api_token="t0ken", admin_api_token="adm1n", **kw)
    return TestClient(create_app(ApiContext(settings=settings, deps=lambda: None, sender=lambda: None), surface))

def test_admin_rejects_the_web_token(tmp_path) -> None:
    assert client(tmp_path, "admin").get("/accounts", headers=WEB).status_code == 401

def test_web_rejects_the_admin_token(tmp_path) -> None:
    assert client(tmp_path, "web").get("/accounts", headers=ADMIN).status_code == 401

def test_admin_without_its_token_is_503(tmp_path) -> None:
    c = client(tmp_path, "admin", admin_api_token=None)
    r = c.get("/accounts", headers=ADMIN)
    assert r.status_code == 503 and "ADMIN_API_TOKEN" in r.json()["detail"]

@pytest.mark.parametrize("path", ["/telegram/webhook", "/go/abcd1234", "/jobs/20260923-aaaaaaaa-0001/download"])
def test_public_routes_are_not_on_admin(tmp_path, path) -> None:
    assert client(tmp_path, "admin").get(path, headers=ADMIN).status_code in (404, 405)

def test_admin_routers_are_not_on_web(tmp_path) -> None:
    web = create_app(ApiContext(settings=make_settings(tmp_path, api_token="t0ken"), deps=lambda: None, sender=lambda: None), "web")
    paths = {r.path for r in web.routes}
    assert "/admin/settings" not in paths          # added by Task 4 on admin only

def test_source_write_on_admin_needs_actor(admin_client_db) -> None:
    r = admin_client_db.post("/sources", headers=ADMIN, json=SOURCE)
    assert r.status_code == 400 and "X-Clipforge-Actor" in r.json()["detail"]

def test_source_write_on_web_keeps_optional_actor(web_client_db) -> None:
    assert web_client_db.post("/sources", headers=WEB, json=SOURCE).status_code == 201

def test_actor_header_required_for_writes(tmp_path) -> None:
    from clipforge.api.admin.deps import require_web_actor
    assert require_web_actor("web:octo") == "web:octo"
    with pytest.raises(Exception):
        require_web_actor(None)
```

- [ ] **Step 2: Run and see them fail**

Run: `uv run pytest -q tests/api/admin/test_surfaces.py`
Expected: FAIL (`create_app() takes 1 positional argument`).

- [ ] **Step 3: Implement**

In `create_app`:
- pick `expected = settings.api_token if surface == "web" else settings.admin_api_token` and its name for the 503;
- move the CLI's routes (list above) into `cli_router(ctx, write_actor)`, where `write_actor` is `actor` on `web` and `require_web_actor` on `admin`; include it on both surfaces;
- wrap the public routes in `if surface == "web":`;
- at the end, `if surface == "admin": for r in admin_routers(ctx): app.include_router(r, dependencies=authorized)`.

`require_web_actor` calls `actions.web_actor` and maps `ValueError` to `HTTPException(400, str(e))`. Change the export script to call `create_app(ctx, "admin")`, the superset the dashboard uses. Regenerate `web/openapi.json` and the client.

- [ ] **Step 4: Run and see them pass**

Run: `uv run pytest -q tests/api`
Expected: PASS. The existing API tests still use the default `surface="web"`.

- [ ] **Step 5: Check and record**

Run `scripts/check.sh --python`, then `npm --prefix web run gen` and `scripts/check.sh --web`.

### Task 2: The `admin` Modal function

**Files:**
- Modify: the module that defines `web` (today `src/clipforge/app.py`; S5 may split it, and then the test reads that module)
- Test: `tests/test_app.py` (add)

**Interfaces:**
- Consumes: `create_app(ctx, "admin")` (Task 1).
- Produces: an `admin` function, `@app.function(image=base_image, cpu=0.5, timeout=60, volumes={JOBS_ROOT: jobs_volume}, secrets=[secrets])` with `@modal.asgi_app(requires_proxy_auth=True)`. It returns `create_app(ApiContext(settings=..., deps=_service_deps, sender=lambda: sender, db=_database), "admin")`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_app.py (add)
def _decorators(src: str, name: str) -> str:
    """The decorator lines above `def <name>(`, back to the previous blank line."""
    head = src[: src.index(f"def {name}(")]
    return head[head.rindex("\n\n"):]

def _body(src: str, name: str) -> str:
    rest = src[src.index(f"def {name}("):]
    return rest[: rest.find("\n\n\n") if "\n\n\n" in rest else len(rest)]

def test_admin_endpoint_requires_proxy_auth() -> None:
    src = Path("src/clipforge/app.py").read_text()
    assert "@modal.asgi_app(requires_proxy_auth=True)" in _decorators(src, "admin")
    assert '"admin")' in _body(src, "admin")

def test_web_endpoint_stays_public() -> None:
    src = Path("src/clipforge/app.py").read_text()
    assert "requires_proxy_auth" not in _decorators(src, "web")
```

- [ ] **Step 2: Run and see it fail**

Run: `uv run pytest -q tests/test_app.py -k "admin or web_endpoint"`
Expected: FAIL (`substring not found`).

- [ ] **Step 3: Implement**

Add the function next to `web`, with the same `ApiContext` construction and `surface="admin"`. `timeout=60`: no downloads go through `admin`.

- [ ] **Step 4: Run and see it pass**

Run: `uv run pytest -q tests/test_app.py`
Expected: PASS.

- [ ] **Step 5: Check and record**

Run `scripts/check.sh --python`.

### Task 3: S3's migration, tables and repositories

**Files:**
- Create: `alembic/versions/NNNN_s3.py`, `src/clipforge/db/needs.py`, `src/clipforge/db/settings.py`, `src/clipforge/db/batches.py`
- Modify: `src/clipforge/db/tables.py`, `src/clipforge/db/doctor.py` (`EXPECTED_HEAD = "NNNN"`)
- Test: `tests/db/test_migrations.py` (add), `tests/db/test_s3_repos.py`

**Interfaces:**
- Produces (§11.8):
  - **Table** `needs_log(row_id text, appeared_at timestamptz, acted_at timestamptz NULL, action text NULL, surface text NULL, actor text NULL, snoozed_until timestamptz NULL, snoozed_by text NULL, PRIMARY KEY (row_id, appeared_at))`.
  - **Table** `settings(key text PRIMARY KEY, value jsonb NOT NULL, updated_by text NOT NULL, updated_at timestamptz NOT NULL)`.
  - **Table** `batches(id bigint identity PK, account_id text NOT NULL REFERENCES accounts(id), request jsonb NOT NULL, estimate_usd numeric(10,4) NOT NULL, status text NOT NULL CHECK (status IN ('pending','approved','declined','created')), created_by text NOT NULL, created_at timestamptz NOT NULL, decided_by text NULL, decided_at timestamptz NULL, job_ids jsonb NULL)`.
  - **Column** `content_items.queue_pin timestamptz NULL`.
  - **Repo** `NeedsLogRepo(db)`:
    - `claim(row_id, appeared_at, action, actor, surface, at) -> NeedsLogEntry | None`: an insert-if-absent of the row, then `UPDATE … SET acted_at, action, actor, surface WHERE acted_at IS NULL RETURNING`. Returns `None` when this caller now holds the claim, else the entry that already holds it (#623: the claim is taken **before** the owning service runs);
    - `release(row_id, appeared_at, actor)`: `UPDATE … SET acted_at=NULL, action=NULL, actor=NULL, surface=NULL WHERE actor=:actor`, used when the owning service refuses;
    - `snooze(row_id, appeared_at, until, actor)`;
    - `get(row_id, appeared_at) -> NeedsLogEntry | None`;
    - `snoozed(now) -> set[str]`;
    - `acted_since(since) -> list[NeedsLogEntry]`.
  - **Repo** `SettingsRepo(db)`: `all() -> dict[str, Any]`, `put(key, value, actor, now)`.
  - **Repo** `BatchesRepo(db)`:
    - `add(account_id, request, estimate_usd, actor, now) -> int`;
    - `get(id) -> BatchRow | None`;
    - `decide(id, to: Literal["approved","declined"], actor, now) -> bool`: conditional `WHERE status='pending'`;
    - `created(id, job_ids)`;
    - `pending(account_id: str | None = None) -> list[BatchRow]`.
  - **Contracts** `NeedsLogEntry` and `BatchRow`, in `models.py`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/db/test_migrations.py (add)
def test_s3_tables_and_column(db) -> None:
    cols = columns(db, "content_items")
    assert "queue_pin" in cols
    for t in ("needs_log", "settings", "batches"):
        assert table_exists(db, t)

def test_expected_head_matches_latest_revision() -> None:
    assert doctor.EXPECTED_HEAD == latest_revision()
```

```python
# tests/db/test_s3_repos.py
NOW = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)

def test_claim_once_then_returns_holder(db) -> None:
    repo = NeedsLogRepo(db)
    assert repo.claim("job_failed:J1", NOW, "resume", "web:octo", "web", NOW) is None
    again = repo.claim("job_failed:J1", NOW, "resume", "telegram:42", "telegram", NOW)
    assert again is not None and again.actor == "web:octo"

def test_release_reopens_the_row(db) -> None:
    repo = NeedsLogRepo(db)
    repo.claim("job_failed:J1", NOW, "resume", "web:octo", "web", NOW)
    repo.release("job_failed:J1", NOW, "web:octo")
    assert repo.claim("job_failed:J1", NOW, "resume", "telegram:42", "telegram", NOW) is None

def test_snooze_hides_until(db) -> None:
    repo = NeedsLogRepo(db)
    repo.snooze("runway_low:realtalk-clips-en", NOW, NOW + timedelta(days=3), "web:octo")
    assert "runway_low:realtalk-clips-en" in repo.snoozed(NOW + timedelta(days=1))
    assert "runway_low:realtalk-clips-en" not in repo.snoozed(NOW + timedelta(days=4))

def test_decide_is_conditional(db, account) -> None:
    repo = BatchesRepo(db)
    bid = repo.add("realtalk-clips-en", {"inputs": []}, 3.1, "web:octo", NOW)
    assert repo.decide(bid, "approved", "web:octo", NOW) is True
    assert repo.decide(bid, "approved", "telegram:42", NOW) is False

def test_settings_put_and_all(db) -> None:
    SettingsRepo(db).put("attention_budget_min", 25, "web:octo", NOW)
    assert SettingsRepo(db).all()["attention_budget_min"] == 25
```

- [ ] **Step 2: Run and see them fail**

Run: `uv run pytest -q tests/db/test_migrations.py tests/db/test_s3_repos.py`
Expected: FAIL.

- [ ] **Step 3: Implement**

Write the migration with `down_revision` = `main`'s head, and the reverse `downgrade()`. Add the `Table` objects to `tables.py` and move `EXPECTED_HEAD`. Write the repos in SQLAlchemy Core, as `db/jobs.py` does. `claim` uses `INSERT … ON CONFLICT DO NOTHING`, then `UPDATE … WHERE acted_at IS NULL RETURNING`; when nothing is returned, it `SELECT`s the holder and returns it.

- [ ] **Step 4: Run and see them pass**

Run: `uv run pytest -q tests/db`
Expected: PASS.

- [ ] **Step 5: Check and record**

Run `scripts/check.sh --python`.

### Task 4: Settings service, routes and page

**Files:**
- Create: `src/clipforge/settings_service.py`, `src/clipforge/api/admin/settings.py`, `web/app/(app)/settings/page.tsx`, `web/components/settings/SettingsForm.tsx`, `web/app/api/cf/settings/route.ts`
- Modify: `src/clipforge/models.py`, `src/clipforge/api/admin/__init__.py`, `web/lib/mocks.ts`, `web/components/nav.ts` (Settings under More)
- Test: `tests/test_settings_service.py`, `tests/api/admin/test_settings_api.py`, `web/tests/unit/settings.test.ts`, `web/e2e/settings.spec.ts`

**Interfaces:**
- Produces:
  - `StudioSettings(attention_budget_min: int = 20, fleet_cap_usd: float = 50.0, payout_thresholds: dict[str, dict[str, float]] = DEFAULT_THRESHOLDS, fixed_subscriptions: list[FixedSubscription] = DEFAULT_SUBSCRIPTIONS, quiet_hours: str = "23:00–08:00")`;
  - `quiet_hours` is read-only: it is computed from `ops.QUIET_FROM` and `QUIET_UNTIL` and ignored on PUT;
  - `FixedSubscription(name: str, usd_month: float)`;
  - `StudioSettingsPatch`: the same fields, all optional (`None` = unchanged), with `attention_budget_min: int | None = Field(None, ge=5, le=240)` and `fleet_cap_usd: float | None = Field(None, ge=0)`; `quiet_hours` is accepted and ignored;
  - `DEFAULT_SUBSCRIPTIONS` = Modal Starter $0, Upload-Post Basic $24, Vercel Pro $20, Neon Free $0;
  - `DEFAULT_THRESHOLDS = {"ypp": {"subscribers": 1000, "watch_hours": 4000}, "tiktok_rewards": {"followers": 10000, "views_30d": 100000}, "fb_cmp": {"followers": 5000}}` (01's figures);
  - `load(db) -> StudioSettings`;
  - `save(db, patch: StudioSettingsPatch, actor, now) -> StudioSettings`;
  - `GET /admin/settings -> StudioSettings`;
  - `PUT /admin/settings` (body `StudioSettingsPatch`, actor required) `-> StudioSettings`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_settings_service.py
def test_defaults_without_rows(db) -> None:
    s = load(db)
    assert s.attention_budget_min == 20 and s.fleet_cap_usd == 50.0

def test_save_patch_and_ignore_quiet_hours(db) -> None:
    s = save(db, StudioSettingsPatch(attention_budget_min=25, quiet_hours="00:00–01:00"), "web:octo", NOW)
    assert s.attention_budget_min == 25 and s.quiet_hours == "23:00–08:00"

def test_negative_budget_rejected() -> None:
    with pytest.raises(ValidationError):
        StudioSettingsPatch(attention_budget_min=-1)
```

```python
# tests/api/admin/test_settings_api.py
def test_put_requires_actor(admin_client) -> None:
    assert admin_client.put("/admin/settings", headers=ADMIN, json={"fleet_cap_usd": 60}).status_code == 400

def test_put_then_get(admin_client) -> None:
    admin_client.put("/admin/settings", headers=ADMIN | ACTOR, json={"fleet_cap_usd": 60})
    assert admin_client.get("/admin/settings", headers=ADMIN).json()["fleet_cap_usd"] == 60
```

```ts
// web/e2e/settings.spec.ts
test("settings shows the budget and quiet hours read-only", async ({ page, context }) => {
  await context.addCookies([await sessionCookie()]);
  await page.goto("/settings");
  await expect(page.getByLabel("Daily attention budget (minutes)")).toHaveValue("20");
  await expect(page.getByText("23:00–08:00")).toBeVisible();
  await expect(page.getByLabel("Quiet hours")).toHaveCount(0); // shown as text, not an input
});
```

`admin_client`, `ADMIN` and `ACTOR` live in `tests/api/admin/conftest.py` (created in this task): a `TestClient` over `create_app(ctx, "admin")` with the `db` fixture wired into `ApiContext.db`, `ADMIN = {"Authorization": "Bearer adm1n"}`, and `ACTOR = {"X-Clipforge-Actor": "web:octo"}`.

- [ ] **Step 2: Run and see them fail**

Run: `uv run pytest -q tests/test_settings_service.py tests/api/admin/test_settings_api.py`
Expected: FAIL.

- [ ] **Step 3: Implement**

`load` merges `SettingsRepo.all()` over the defaults. `save` writes one row per changed key. The route file builds an `APIRouter(prefix="/admin")`, and `admin_routers` returns it. The page is a form with the fixed subscriptions as an editable list. Regenerate OpenAPI and the client; add the mock to `mocks.ts`.

- [ ] **Step 4: Run and see them pass**

Run: `uv run pytest -q tests/test_settings_service.py tests/api/admin` and `npm --prefix web run test`, then `npm --prefix web run e2e -- settings`
Expected: PASS.

- [ ] **Step 5: Check and record**

Run `scripts/check.sh --python --web`.

### Task 5: `upstream.ts` on `admin`, with the actor

**Files:**
- Modify: `web/lib/upstream.ts`, `web/app/api/cf/posting/route.ts`, `web/app/api/cf/jobs/[id]/route.ts`, `web/playwright.config.ts` (env names), `web/README.md`, `.env.example`, `docs/ops/secrets.md`, `docs/studio/11-owner-runbook.md` §5b
- Create: `web/lib/actor.ts`
- Test: `web/tests/unit/upstream.test.ts` (extend), `web/tests/unit/actor.test.ts`

**Interfaces:**
- Produces:
  - `UpstreamEnv = { apiUrl?: string; apiToken?: string; proxyKey?: string; proxySecret?: string; mock: boolean }`, read from `ADMIN_API_URL`, `ADMIN_API_TOKEN`, `MODAL_PROXY_KEY` and `MODAL_PROXY_SECRET`. A missing variable → `NOT_CONFIGURED`.
  - `call<S>(route, path, schema, env, fetchImpl, opts?: { method?: "GET"|"POST"|"PUT"|"DELETE"; body?: unknown; actor?: string; onNotFound?: UpstreamResult })`, extended from today's (method, body and actor added).
  - Headers: `Modal-Key`, `Modal-Secret`, `Authorization: Bearer`, `Accept`, plus `X-Clipforge-Actor` when `actor` is set and `Content-Type: application/json` when `body` is set.
  - `upstreamGet<S>(route, path, schema, env?, fetchImpl?)` and `upstreamWrite<S>(route, path, schema, method, body, actor, env?, fetchImpl?)`, the helpers every later handler uses.
  - A 409 maps to `{ ok: false, status: 409, error: <the API's detail> }`, shown by the page ("changed meanwhile: …"). A 400 maps to `{ ok: false, status: 400, error: detail }`.
  - `actorFor(session): string` returns `web:<github login>` (the login is in the session through Auth.js's `profile.login`, added to the JWT callback in `auth.ts`).

- [ ] **Step 1: Write the failing tests**

```ts
// web/tests/unit/upstream.test.ts (add)
it("sends the proxy pair, the bearer and the actor", async () => {
  const seen: Request[] = [];
  const fetchImpl = async (u: URL, init: RequestInit) => { seen.push(new Request(u, init)); return Response.json({ ok: 1 }); };
  await upstreamWrite("/admin/settings", "admin/settings", z.object({ ok: z.number() }), "PUT", { a: 1 }, "web:octo",
    { apiUrl: "https://admin.example", apiToken: "t", proxyKey: "wk-1", proxySecret: "ws-1", mock: false }, fetchImpl as typeof fetch);
  const h = seen[0].headers;
  expect(h.get("Modal-Key")).toBe("wk-1");
  expect(h.get("Modal-Secret")).toBe("ws-1");
  expect(h.get("Authorization")).toBe("Bearer t");
  expect(h.get("X-Clipforge-Actor")).toBe("web:octo");
});

it("missing proxy pair is not configured", async () => {
  const r = await upstreamGet("/posting", "posting", zPostingOverview, { apiUrl: "https://a", apiToken: "t", mock: false });
  expect(r).toEqual({ ok: false, status: 503, error: "API not configured" });
});

it("upstream waits through a slow first response", async () => {   // Review Focus 3
  vi.useFakeTimers();
  const slow = () => new Promise<Response>((res) => setTimeout(() => res(Response.json(MOCK_POSTING)), 12_000));
  const p = upstreamGet("/posting", "posting", zPostingOverview, FULL_ENV, slow as unknown as typeof fetch);
  await vi.advanceTimersByTimeAsync(12_000);
  expect((await p).ok).toBe(true);
  vi.useRealTimers();
});

it("409 carries the detail", async () => {
  const f = async () => Response.json({ detail: "already approved by telegram:42 at 09:04" }, { status: 409 });
  const r = await upstreamWrite("/x", "x", z.object({}), "POST", {}, "web:octo", FULL_ENV, f as unknown as typeof fetch);
  expect(r).toEqual({ ok: false, status: 409, error: "already approved by telegram:42 at 09:04" });
});
```

- [ ] **Step 2: Run and see them fail**

Run: `npm --prefix web run test -- upstream actor`
Expected: FAIL.

- [ ] **Step 3: Implement**

Generalize `call` and keep `getPosting` and `getJob` on top of `upstreamGet`. Log lines keep naming only the route and the status. Update the Playwright env (`ADMIN_API_URL: ""`, etc.). Docs:
- **`docs/ops/secrets.md`:** `ADMIN_API_TOKEN` in `clipforge-secrets`; the four Vercel variables, each with where it lives, who reads it and the rotation steps from spec §11.2.
- **Runbook §5b:** create the Modal proxy token (Modal → Settings → Proxy Auth Tokens) and set the four variables; remove `CLIPFORGE_API_URL` and `API_TOKEN` from Vercel after the deploy.
- **`.env.example`:** `ADMIN_API_TOKEN=` commented.
- **`web/README.md`:** the variables and local use (`ADMIN_API_URL` pointed at the deployed `admin`, with `AUTH_DISABLED=1`).

- [ ] **Step 4: Run and see them pass**

Run: `npm --prefix web run check`
Expected: PASS.

- [ ] **Step 5: Check and record — checkpoint S3-1**

1. Run the full `scripts/check.sh` and `scripts/check.sh --e2e`.
2. Ask `pr-reviewer`, `security-reviewer` (endpoint split, proxy auth, token checks, the actor header; #618) and `migration-reviewer` to review.
3. Update `docs/ARCHITECTURE.md` (the `admin` endpoint, S3's tables).
4. Write the report.
5. Suggested commit: `NNN: s3-1: admin endpoint, proxy auth, S3 migration, settings`.

**Owner steps (S3-1):**
0. **Pre-deploy check (#623):** no other code card is on `main` undeployed (`docs/ops/deploys.md` against `git log`), and `uv run modal run src/clipforge/app.py::db_doctor` shows the expected head (card 014's `0002`, or the hooks build's if it deployed first) before `alembic upgrade head`.
1. **Secret:** add `ADMIN_API_TOKEN` to `clipforge-secrets` with the `docs/ops/secrets.md` procedure (a random value: `python -c "import secrets; print(secrets.token_urlsafe(32))"`).
2. **Migrate and deploy:**
   - `uv run alembic upgrade head` (Neon now at `NNNN`);
   - `scripts/deploy.sh --dry-run`;
   - `scripts/deploy.sh --reason "S3-1: admin endpoint"`, outside the blackout.
3. `uv run modal run src/clipforge/app.py::db_doctor`: the head is `NNNN`.
4. **Proxy token:** create a Modal proxy token (Settings → Proxy Auth Tokens). Then check, from the laptop:
   - `curl -s -o /dev/null -w "%{http_code}" <admin url>/accounts` → `401` (no proxy headers, refused by Modal);
   - `curl -s -H "Modal-Key: …" -H "Modal-Secret: …" -H "Authorization: Bearer <ADMIN_API_TOKEN>" <admin url>/admin/settings` → the defaults.
5. **Vercel (only if card 004 is done):** set `ADMIN_API_URL`, `ADMIN_API_TOKEN`, `MODAL_PROXY_KEY` and `MODAL_PROXY_SECRET`, redeploy, check Home and Settings (`/settings`, under More) on the phone, then remove `CLIPFORGE_API_URL` and `API_TOKEN`. Without card 004, check locally: `ADMIN_API_URL=… npm --prefix web run dev` with `AUTH_DISABLED=1`.

**What the owner sees:** Settings (`/settings`, listed under More); Home and the job page unchanged, now over `admin`.

**Rollback (S3-1):**
- A revert deploy (`git revert` of the merge, `scripts/deploy.sh --dry-run`, then the deploy).
- The migration is expand-only, so the old code runs on it.
- On Vercel, put `CLIPFORGE_API_URL` and `API_TOKEN` back (the reverted `upstream.ts` reads them).
- `web`'s routes and token are unchanged by S3-1 (the CLI's routes only moved into a router mounted on both), so the CLI and Telegram are unaffected throughout.

---

# Part S3-2: "needs me", Home and `/act`

### Task 6: Needs contracts and the provider registry

**Files:**
- Create: `src/clipforge/needs/__init__.py`, `src/clipforge/needs/registry.py`, `src/clipforge/needs/providers.py`, `src/clipforge/needs/attention.py`
- Modify: `src/clipforge/models.py`
- Test: `tests/needs/test_providers.py`, `tests/needs/test_attention.py`

**Interfaces:**
- Produces:
  - `NeedsKind` (str enum): `review_due, review_batch, publish_failed, publisher_disconnected, strike, spend_line, cap_reached, permission_expired, runway_low, promotion_ready, demotion_done, experiment_decision, held_clips, job_failed, hook_weak, series_approval, view_collapse, outage` (§7.11).
  - `NeedsAction(key: str, label: str, primary: bool = False)`.
  - `NeedsRow(id: str, kind: NeedsKind, subject: str, level: Literal["instant","digest"], account_id: str | None, title: str, context: str, appeared_at: datetime, due_at: datetime | None, est_minutes: float, actions: list[NeedsAction], href: str)`; `id = f"{kind}:{subject}"`; `href = f"/act/{kind}/{subject}"`.
  - `Attention(budget_min: int, done_min: float, listed_min: float)`.
  - `NeedsList(rows: list[NeedsRow], attention: Attention)`.
  - `NeedsDetail(row: NeedsRow | None, state: Literal["open","done","gone"], done: NeedsLogEntry | None, evidence: dict[str, Any])`.
  - `Provider` protocol, `kind: NeedsKind`:
    - `rows(ctx: NeedsContext, now: datetime) -> list[NeedsRow]`;
    - `get(ctx, subject, now) -> NeedsRow | None`;
    - `evidence(ctx, subject) -> dict[str, Any]`;
    - `act(ctx, subject, action, actor, now) -> str`, which returns a one-line result and raises `ActionFailed` or `AlreadyDone(by, at, surface)`;
    - `done(ctx, subject) -> NeedsLogEntry | None` (#623): who decided a row that left the list **outside the needs router**, read from the owning service's record. Held clips and posting rows read the last `post_events` row with its `actor` (a ✅, ⏭ or 🗑 tapped in Telegram); review rows read `content_items.approved_by`/`approved_at` or the verdict event; the outage row reads `posting_state.changed_by` (S2a). `job_failed` has no service record of its own, so every resume path goes through the router (Task 10), and its `done` reads `needs_log` only.
  - `NeedsContext(db: Database, kv: KV, deps: Deps, settings: Settings, posting: Posting, ops: OpsAlerts | None)`.
  - In `needs/registry.py`: `AlreadyDone(Exception)` with `by: str`, `at: datetime` and `surface: str | None` (the router and `produce/batches.py` raise it; routes map it to 409 "already done by <by> at <time>"). `ActionFailed` is `posting/actions.ActionFailed`, reused.
  - `REGISTRY: dict[NeedsKind, Provider]`, filled by `register(provider)`.
  - Providers in this task (their sources are on `main` after S1 and S2a):
    - `JobFailedProvider`: `jobs.status='failed'`; instant when the account has under 1 day of queue, else digest; action `resume` → `service.resume_job`;
    - `HeldClipsProvider`: `bot/posting.held(record, source, now)` per queued record, grouped by account; actions `skip`, `reject` through `posting/actions`; `done` from the item's last `post_events` row;
    - `PermissionExpiredProvider`: `sources.source_problem` holding clips; action `open`;
    - `OutageProvider`: the `posting:outage` flag; actions `go` → `posting/actions.pause(on=False)`, `restore` → `service.restore_posting`.
  - `estimate_minutes(kind, account_kind, publish_path) -> float`, using §2.7's table (assisted clip 7, a review decision 1, others 1).
  - `attention(rows, done: list[NeedsLogEntry], budget) -> Attention`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/needs/test_providers.py
def test_failed_job_is_a_row_with_resume(needs_ctx, failed_job) -> None:
    rows = REGISTRY[NeedsKind.JOB_FAILED].rows(needs_ctx, NOW)
    assert rows[0].id == f"job_failed:{failed_job}" and rows[0].actions[0].key == "resume"
    assert rows[0].href == f"/act/job_failed/{failed_job}"

def test_failed_job_is_instant_under_a_day_of_queue(needs_ctx, failed_job_queue_short) -> None:
    assert REGISTRY[NeedsKind.JOB_FAILED].rows(needs_ctx, NOW)[0].level == "instant"

def test_outage_row_when_flag_set(needs_ctx) -> None:
    needs_ctx.kv.put("posting:outage", "2026-10-19")
    rows = REGISTRY[NeedsKind.OUTAGE].rows(needs_ctx, NOW)
    assert [r.kind for r in rows] == [NeedsKind.OUTAGE] and {a.key for a in rows[0].actions} == {"go", "restore"}

def test_appeared_at_is_the_source_time(needs_ctx, failed_job) -> None:
    row = REGISTRY[NeedsKind.JOB_FAILED].rows(needs_ctx, NOW)[0]
    assert row.appeared_at == FAILED_AT                      # not NOW

def test_registry_has_no_module_from_unmerged_cards() -> None:
    import clipforge.needs.providers as p
    assert "publishing" not in p.__dict__ or importlib.util.find_spec("clipforge.publishing") is not None
```

```python
# tests/needs/test_attention.py
def test_meter_counts_assisted_clips_at_seven() -> None:
    rows = [row(est=7.0), row(est=1.0)]
    assert attention(rows, done=[], budget=20) == Attention(budget_min=20, done_min=0, listed_min=8.0)
```

- [ ] **Step 2: Run and see them fail**

Run: `uv run pytest -q tests/needs`
Expected: FAIL.

- [ ] **Step 3: Implement**

Each provider is a small class in `providers.py`, registered at import. `rows` reads only what it needs (one query per provider). `get` returns the row if it is still open, else `None`. **S2-owned kinds** are registered in this task only if their module is on `main` when the card runs; each is a class here with its source and action named:
- `ReviewDueProvider` and `ReviewBatchProvider`: `ReviewService.queue`, approve and reject;
- `PublishFailedProvider`, `PublisherDisconnectedProvider` and `StrikeProvider`: `publishing.problems.open_problems`;
- `PromotionReadyProvider`: `ladder()` and `AutopilotService.promote`;
- `DemotionDoneProvider`: `autopilot_events` with actor `system:demotion`, in the last 7 days.

Otherwise, the card's report names them for the S2 card's follow-up (§11.1).

- [ ] **Step 4: Run and see them pass**

Run: `uv run pytest -q tests/needs`
Expected: PASS.

- [ ] **Step 5: Check and record**

Run `scripts/check.sh --python`.

### Task 7: Runway (`accounts/runway.py`) and the `runway_low` row

**Files:**
- Create: `src/clipforge/accounts/runway.py`
- Modify: `src/clipforge/needs/providers.py` (`RunwayLowProvider`); `src/clipforge/accounts/ladder.py`'s stats builder, only if card 016 is merged (its `runway_days` input reads `runway()`)
- Test: `tests/accounts/test_runway.py`

**Interfaces:**
- Produces:
  - `Runway(account_id: str, days: float, queued: int, in_production: int, unused_material: int, per_day: float, limited_by: str | None)`;
  - `runway(db, deps, account: Account, now) -> Runway`;
  - **clips:** `(eligible queued + clips expected from running jobs + clips per source hour × unclipped imported hours) ÷ len(slots)`. Clips per source hour is the median over the account's done jobs, or 6 with no history. `limited_by="fetch more episodes"` when there are no unclipped hours;
  - **other kinds:** queued ÷ cadence, `limited_by="approve a series"` (S6 replaces this);
  - `RunwayLowProvider`: a digest row under 14 days; actions `open_produce`, `open_sources`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/accounts/test_runway.py
def test_clips_runway_counts_unclipped_hours(db, deps, realtalk_with_3_slots) -> None:
    seed_queue(db, eligible=6); seed_unclipped(deps, hours=2.0); seed_done_jobs(db, clips_per_hour=6)
    r = runway(db, deps, realtalk_with_3_slots, NOW)
    assert r.days == pytest.approx((6 + 12) / 3)

def test_empty_pool_says_fetch_more(db, deps, realtalk_with_3_slots) -> None:
    seed_queue(db, eligible=3)
    assert runway(db, deps, realtalk_with_3_slots, NOW).limited_by == "fetch more episodes"

def test_runway_low_row_under_14_days(needs_ctx, realtalk_short_runway) -> None:
    rows = REGISTRY[NeedsKind.RUNWAY_LOW].rows(needs_ctx, NOW)
    assert rows and rows[0].level == "digest"

def test_no_slots_is_not_a_division_error(db, deps, account_without_slots) -> None:
    assert runway(db, deps, account_without_slots, NOW).days == float("inf")
```

- [ ] **Step 2: Run, implement, pass**

Run: `uv run pytest -q tests/accounts/test_runway.py` (FAIL first). Implement. "Unclipped imported" episodes come from `episodes(db, deps, account) -> list[Episode]`, defined in `accounts/runway.py` in this task (with the `Episode` contract in `models.py`), so Task 17's route reuses it. Rerun: PASS.

- [ ] **Step 3: Check and record**

Run `scripts/check.sh --python`.

### Task 8: The needs routes and the router

**Files:**
- Create: `src/clipforge/needs/router.py`, `src/clipforge/api/admin/needs.py`
- Modify: `src/clipforge/api/admin/__init__.py`
- Test: `tests/needs/test_router.py`, `tests/api/admin/test_needs_api.py`

**Interfaces:**
- Consumes: `REGISTRY` (Task 6), `NeedsLogRepo` (Task 3), `settings_service.load` (Task 4).
- Produces:
  - `list_rows(ctx, now, account_id=None, level=None, after: str | None = None) -> NeedsList`. It removes snoozed rows; sorts instant first, then by `due_at`, then `appeared_at`; `after=<row id>` returns the rows after that one (Next).
  - `detail(ctx, kind, subject, now) -> NeedsDetail`:
    - `open` when the provider's `get` returns a row;
    - `done` when `needs_log` has an acted entry, or the provider raises `AlreadyDone`;
    - `gone` otherwise.
  - `act(ctx, kind, subject, action, actor, surface, now) -> ActResult(row_id, result, next: str | None)`:
    1. `row = provider.get(...)`; if `None`: `provider.done(...)` or the `needs_log` entry → 409 `already done by <actor> at <time>`, else 404 `gone`;
    2. **claim first** (#623): `holder = needs_log.claim(row.id, row.appeared_at, action, actor, surface, now)`; a holder → 409 `already done by <holder.actor> at <time>`;
    3. `provider.act(...)`; on `ActionFailed` or `AlreadyDone`, `needs_log.release(row.id, row.appeared_at, actor)` and re-raise;
    4. `ops.mark_done(row.id, actor, surface, now)` (Task 10; best-effort, a no-op until Task 10).
  - `detail` checks `provider.done(...)` as well as `needs_log`, so a Telegram decision shows "Done by telegram:… at …" (#623).
  - `snooze(ctx, kind, subject, actor, now)`: digest rows only, 3 days.
  - Routes:
    - `GET /admin/needs?account=&level=&after=` → `NeedsList`;
    - `GET /admin/needs/{kind}/{subject:path}` → `NeedsDetail`;
    - `POST /admin/needs/{kind}/{subject:path}/{action}` → `ActResult` (actor required);
    - `POST /admin/needs/{kind}/{subject:path}/snooze` (actor required).
  - `subject:path` accepts `:` and `-`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/needs/test_router.py
def test_list_orders_instant_first_then_due(needs_ctx, mixed_rows) -> None:
    rows = list_rows(needs_ctx, NOW).rows
    assert [r.level for r in rows][:2] == ["instant", "instant"]

def test_snoozed_row_hidden(needs_ctx, runway_row) -> None:
    snooze(needs_ctx, "runway_low", "realtalk-clips-en", "web:octo", NOW)
    assert all(r.kind != "runway_low" for r in list_rows(needs_ctx, NOW).rows)

def test_snooze_instant_row_refused(needs_ctx, failed_job) -> None:
    with pytest.raises(ActionFailed, match="digest"):
        snooze(needs_ctx, "job_failed", failed_job, "web:octo", NOW)

def test_second_action_returns_already_done(needs_ctx, failed_job) -> None:      # Review Focus 1
    act(needs_ctx, "job_failed", failed_job, "resume", "web:octo", "web", NOW)
    with pytest.raises(AlreadyDone) as e:
        act(needs_ctx, "job_failed", failed_job, "resume", "telegram:42", "telegram", NOW)
    assert e.value.by == "web:octo"

def test_concurrent_acts_run_the_service_once(pg_url, failed_job_in_db) -> None:   # Review Focus 1, two connections
    calls: list[str] = []
    ctxs = [needs_ctx_on(Database(pg_url), on_resume=calls.append) for _ in range(2)]   # separate engines
    barrier = threading.Barrier(2)
    def tap(ctx, who):
        barrier.wait()
        try: act(ctx, "job_failed", failed_job_in_db, "resume", who, "web", NOW)
        except AlreadyDone: pass
    threads = [threading.Thread(target=tap, args=(c, w)) for c, w in zip(ctxs, ["web:octo", "telegram:42"])]
    [t.start() for t in threads]; [t.join() for t in threads]
    assert len(calls) == 1

def test_failed_service_releases_the_claim(needs_ctx, failed_job_resume_raises) -> None:
    with pytest.raises(ActionFailed):
        act(needs_ctx, "job_failed", failed_job_resume_raises, "resume", "web:octo", "web", NOW)
    assert NeedsLogRepo(needs_ctx.db).get(f"job_failed:{failed_job_resume_raises}", FAILED_AT).acted_at is None

def test_telegram_skip_shows_done_in_act(db_posting_ctx, held_item) -> None:   # real store, no mocks of the provider
    actions.skip(db_posting_ctx.posting, held_item.ref, "telegram:42", NOW)          # the ⏭ tap's own path
    d = detail(db_posting_ctx.needs, "held_clips", held_item.account_id, NOW)
    assert d.state == "done" and d.done.actor == "telegram:42"

def test_detail_of_vanished_row_is_gone_not_500(needs_ctx) -> None:             # Review Focus 2
    assert detail(needs_ctx, "job_failed", "20260101-deadbeef-0001", NOW).state == "gone"

def test_outage_row_first_when_flag_set(needs_ctx, failed_job) -> None:         # Review Focus 4
    needs_ctx.kv.put("posting:outage", "2026-10-19")
    assert list_rows(needs_ctx, NOW).rows[0].kind == "outage"

def test_list_never_writes_needs_log(needs_ctx, failed_job, db) -> None:
    list_rows(needs_ctx, NOW); list_rows(needs_ctx, NOW)
    assert count(db, "needs_log") == 0
```

```python
# tests/api/admin/test_needs_api.py
def test_subject_with_colon_round_trips(admin_client, publish_failed_row) -> None:   # Review Focus 5
    r = admin_client.get("/admin/needs/publish_failed/item123:tiktok", headers=ADMIN)
    assert r.status_code == 200 and r.json()["row"]["subject"] == "item123:tiktok"

def test_action_conflict_is_409_with_who(admin_client, failed_job) -> None:
    admin_client.post(f"/admin/needs/job_failed/{failed_job}/resume", headers=ADMIN | ACTOR)
    r = admin_client.post(f"/admin/needs/job_failed/{failed_job}/resume", headers=ADMIN | ACTOR)
    assert r.status_code == 409 and "web:octo" in r.json()["detail"]

def test_unknown_kind_404(admin_client) -> None:
    assert admin_client.get("/admin/needs/nope/x", headers=ADMIN).status_code == 404
```

The `publish_failed_row` fixture registers a fake provider for `publish_failed`, so this test runs without S2c.

- [ ] **Step 2: Run, implement, pass**

Run: `uv run pytest -q tests/needs tests/api/admin/test_needs_api.py` (FAIL first). Implement. `AlreadyDone` maps to 409, `ActionFailed` to 400 with its message, and an unknown kind or action to 404. Regenerate OpenAPI and the client. Rerun: PASS.

- [ ] **Step 3: Check and record**

Run `scripts/check.sh --python --web`.

### Task 9: Fleet scoreboard and slots

**Files:**
- Create: `src/clipforge/fleet.py`, `src/clipforge/api/admin/fleet.py`
- Modify: `src/clipforge/models.py`, `src/clipforge/api/admin/__init__.py`
- Test: `tests/test_fleet.py`, `tests/api/admin/test_fleet_api.py`

**Interfaces:**
- Produces:
  - `ScoreRow(account_id, handle, kind, rung: str, lifecycle_day: int, posted_yesterday: int, approval_rate: float | None, cost_yesterday_usd: float, runway_days: float, health: Literal["ok","warn","bad"], views: int | None = None, followers: int | None = None, revenue_usd: float | None = None)`:
    - `rung` is the autopilot preset, or `"hands_on"` without a row;
    - `lifecycle_day` comes from `accounts.created_at`;
    - `health` is `bad` with an open instant row for the account, `warn` with a digest row, else `ok`;
    - views, followers and revenue are `None` until S7.
  - `Scoreboard(date: date, rows: list[ScoreRow], ran_without_you: str | None)`.
  - `SlotRow(account_id, at: datetime, state: Literal["posted","failed","next","waiting_approval","missed","planned"], ref: str | None, platforms: list[Platform])`:
    - computed from each schedule copy's slots in the account's time zone;
    - `posted` and `failed` come from `post_events`;
    - `waiting_approval` from `slot_plans` when S2b is merged (otherwise never).
  - `scoreboard(db, deps, kv, day, now) -> Scoreboard`; `slots(db, kv, start, end, account_id=None, now) -> list[SlotRow]`.
  - `GET /admin/fleet/scoreboard?date=` and `GET /admin/slots?from=&to=&account=`. A range is at most 14 days (400 beyond).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_fleet.py
def test_scoreboard_row_per_account_with_day(db, deps, kv, two_accounts) -> None:
    sb = scoreboard(db, deps, kv, date(2026, 10, 19), NOW)
    assert {r.account_id for r in sb.rows} == {"realtalk-clips-en", "founder-tapes-en"}
    assert sb.rows[0].lifecycle_day >= 1 and sb.rows[0].views is None

def test_slots_in_account_timezone_across_dst(db, kv, ny_account) -> None:
    day = slots(db, kv, datetime(2026, 11, 1, tzinfo=UTC), datetime(2026, 11, 2, tzinfo=UTC), now=NOW)
    assert [s.at.astimezone(ZoneInfo("America/New_York")).strftime("%H:%M") for s in day] == ["08:00", "13:00", "19:00"]

def test_slots_range_over_14_days_rejected(admin_client) -> None:
    assert admin_client.get("/admin/slots?from=2026-10-01&to=2026-10-30", headers=ADMIN).status_code == 400
```

- [ ] **Step 2: Run, implement, pass**

Run: `uv run pytest -q tests/test_fleet.py tests/api/admin/test_fleet_api.py` (FAIL first). Implement with one query per table; reuse `schedule.py` for slot times. Regenerate OpenAPI and the client. Rerun: PASS.

- [ ] **Step 3: Check and record**

Run `scripts/check.sh --python --web`.

### Task 10: Open buttons and the alert redraw

**Files:**
- Modify: `src/clipforge/ops.py`, `src/clipforge/needs/router.py` (call `mark_done`), `src/clipforge/bot/messages.py` and `bot/webhook.py` (the failure alert gains a **[Resume]** callback button `n:job_failed:resume:<job>`; that callback and typed `/resume <id>` call `needs.router.act(kind="job_failed", subject=<job>, action="resume", actor=telegram:<id>, surface="telegram")` when the database is wired, else `service.resume_job` as today), the callers of `ops.alert` for row kinds (`pipeline` failure path → `row_id="job_failed:<job>"`; `bot/posting.py` permission hold → `permission_expired:<source>`; `posting/daily.py` outage → `outage:posting`); if merged: `review/cards.py` (Open ↗ to `/act/review_due/<item>`), `publishing/problems.alert_problem` (passes `row_id`), and `dispatch/digest.py` (`EXISTING_PAGES` gains `"/act/"` and `"/?needs="`)
- Test: `tests/test_ops.py` (add), `tests/review/test_cards.py` (add, if merged), `tests/dispatch/test_digest.py` (add, if merged)

**Interfaces:**
- Produces:
  - `OpsAlerts.alert(..., row_id: str | None = None)`. When `row_id` is set and `path` is `None`, `path = "/act/" + row_id.replace(":", "/", 1)`.
  - After a successful send, `kv.put(f"alert:msg:{row_id}", json.dumps({"chat": chat_id, "message": message_id, "text": text}))`, overwriting any older value (only the latest message per row is kept). The sender's `send_message` returns the message id, as the bot fakes already do.
  - Held alerts store `row_id` in the held key's value as JSON (`{"text":…, "row_id":…}`; a plain string is still accepted for alerts held before the deploy). `_flush` records the fold message under each listed row id, as `{"chat", "message", "text", "line": i}`.
  - `OpsAlerts.mark_done(row_id, actor, surface, at) -> bool`:
    - reads the key and edits the message. A direct alert becomes "✅ Done by <actor> at HH:MM (<surface>)" with no buttons; for a fold message, only its `line` gets " ✅".
    - Returns False and logs on any error; never raises.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ops.py (add)
def test_row_alert_records_message_and_act_path(ops_env) -> None:
    ops_env.ops.alert("Job failed", "job_failed", "J1", row_id="job_failed:J1", now=DAY)
    sent = ops_env.sender.sent[-1]
    assert sent.buttons[0][0][1].endswith("/act/job_failed/J1")
    assert json.loads(ops_env.kv.get("alert:msg:job_failed:J1"))["message"] == sent.message_id

def test_latest_message_wins(ops_env) -> None:
    ops_env.ops.alert("a", "job_failed", "J1", row_id="job_failed:J1", now=DAY)
    ops_env.ops.alert("b", "job_failed", "J1", row_id="job_failed:J1", now=DAY + timedelta(hours=1))
    assert json.loads(ops_env.kv.get("alert:msg:job_failed:J1"))["text"].endswith("b")

def test_mark_done_edits_and_drops_buttons(ops_env) -> None:
    ops_env.ops.alert("Job failed", "job_failed", "J1", row_id="job_failed:J1", now=DAY)
    assert ops_env.ops.mark_done("job_failed:J1", "web:octo", "web", DAY) is True
    edit = ops_env.sender.edited[-1]
    assert "Done by web:octo" in edit.text and edit.buttons is None

def test_fold_records_each_row_and_marks_its_line(ops_env) -> None:
    ops_env.ops.alert("a", "job_failed", "J1", row_id="job_failed:J1", now=NIGHT)
    ops_env.ops.alert("b", "job_failed", "J2", row_id="job_failed:J2", now=NIGHT)
    ops_env.ops.flush(MORNING)
    ops_env.ops.mark_done("job_failed:J2", "web:octo", "web", MORNING)
    assert ops_env.sender.edited[-1].text.splitlines()[2].endswith("✅")

def test_mark_done_failure_never_raises(ops_env_broken_sender) -> None:
    assert ops_env_broken_sender.ops.mark_done("job_failed:J1", "web:octo", "web", DAY) is False

def test_telegram_resume_goes_through_the_router(bot_env_db, failed_job) -> None:
    bot_env_db.callback(f"n:job_failed:resume:{failed_job}", user=42)
    d = detail(bot_env_db.needs_ctx, "job_failed", failed_job, NOW)
    assert d.state == "done" and d.done.actor == "telegram:42" and d.done.surface == "telegram"

def test_old_plain_held_value_still_flushes(ops_env) -> None:
    ops_env.kv.put("notify:held:2026-10-19T23:30:00+00:00:job_failed:J9", "plain text")
    ops_env.kv.put("notify:pending", "1")
    assert ops_env.ops.flush(MORNING) == 1
```

- [ ] **Step 2: Run, implement, pass**

Run: `uv run pytest -q tests/test_ops.py tests/review tests/dispatch` (FAIL first). Implement, then pass `row_id` at the call sites listed above. Rerun: PASS.

- [ ] **Step 3: Check and record**

Run `scripts/check.sh --python`.

### Task 11: Home, `/act` and the link-contract test

**Files:**
- Create:
  - pages: `web/app/(app)/act/[kind]/[...subject]/page.tsx`;
  - Home components: `web/components/home/NeedsList.tsx`, `AttentionMeter.tsx`, `Scoreboard.tsx`, `TodaySlots.tsx`;
  - `/act` components: `web/components/act/ActView.tsx`, `ActEvidence.tsx`, `ActBar.tsx`;
  - route handlers: `web/app/api/cf/needs/route.ts`, `needs/[kind]/[...subject]/route.ts` (GET detail, POST action and snooze), `fleet/scoreboard/route.ts`, `slots/route.ts`;
  - tests: `web/e2e/home.spec.ts`, `web/e2e/act.spec.ts`, `web/e2e/links.spec.ts`, `web/tests/unit/needs.test.ts`.
- Modify: `web/package.json` (a `gen:links` script that writes `web/lib/links.json` from `web/lib/links.ts`; `gen:check` also checks that file), `web/app/(app)/page.tsx` (Home becomes needs, then scoreboard, then slots; S3a's posting summary moves into the slots panel), `web/lib/mocks.ts`, `web/lib/queries.ts`, `web/lib/polling.ts` (`NEEDS_POLL_MS = 15_000`), `web/components/nav.ts` (§6's sidebar and phone tabs; pages that don't exist yet are left out until their task)

**Interfaces:**
- Consumes: the Task 8 and Task 9 routes through `upstreamGet` and `upstreamWrite` (Task 5); `actorFor(session)`.
- Produces:
  - **The link contract.** `web/lib/links.ts` exports `LINK_CONTRACT: { path: string; since: string; exists: boolean }[]`, §7.10's table. Rows for pages not built yet carry `exists: false` and are flipped by their task. **`links.spec.ts` resolves every `exists: true` path after login at both sizes**: the page renders its heading, and an unknown id shows "not found" (never a blank page).
  - **The Python side:** `tests/test_link_contract.py` reads the same table (exported to `web/lib/links.json` by `npm run gen:links` and checked by `gen:check`). It asserts that every `path=` passed to `ops.alert` and every `EXISTING_PAGES` entry matches an `exists: true` prefix.

- [ ] **Step 1: Write the failing tests**

```ts
// web/e2e/act.spec.ts
test("act shows the row, acts, then Next", async ({ page, context }) => {
  await context.addCookies([await sessionCookie()]);
  await page.goto("/act/job_failed/20261019-3fa9c1d2-4b7e");
  await expect(page.getByRole("heading", { name: /Job failed/ })).toBeVisible();
  await page.getByRole("button", { name: "Resume" }).click();
  await expect(page.getByText("Resumed")).toBeVisible();
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page).toHaveURL(/\/act\/held_clips\//);
});

test("act shows who handled it", async ({ page, context }) => {
  await context.addCookies([await sessionCookie()]);
  await page.goto("/act/job_failed/20261019-done0000-0001");
  await expect(page.getByText("Done by telegram:42 at 13:02, in Telegram")).toBeVisible();
});

test("act shows not found for an unknown id", async ({ page, context }) => {   // Review Focus 2
  await context.addCookies([await sessionCookie()]);
  await page.goto("/act/job_failed/20260101-deadbeef-0001");
  await expect(page.getByText("isn't in the list any more; nothing was changed")).toBeVisible();
});

test("a subject with a colon lands on its row", async ({ page, context }) => {  // Review Focus 5
  await context.addCookies([await sessionCookie()]);
  await page.goto("/act/publish_failed/item123:tiktok");
  await expect(page.getByText("item123")).toBeVisible();
});
```

```ts
// web/e2e/home.spec.ts
test("home: needs first, meter, then scoreboard and slots", async ({ page, context }) => {
  await context.addCookies([await sessionCookie()]);
  await page.goto("/");
  const headings = page.getByRole("heading", { level: 2 });
  await expect(headings.nth(0)).toHaveText(/Needs you/);
  await expect(page.getByText(/of ~20 min today/)).toBeVisible();
  await expect(headings.nth(1)).toHaveText(/Accounts/);
  await expect(headings.nth(2)).toHaveText(/Today's slots/);
});

test("home empty says nothing needs you", async ({ page, context }) => {
  await context.addCookies([await sessionCookie()]);
  await page.goto("/?mock=empty");
  await expect(page.getByText("Nothing needs you")).toBeVisible();
});
```

```ts
// web/e2e/links.spec.ts
for (const link of LINK_CONTRACT.filter((l) => l.exists)) {
  test(`link ${link.path} resolves`, async ({ page, context }) => {
    await context.addCookies([await sessionCookie()]);
    const res = await page.goto(link.path.replace("<id>", MOCK_IDS.known).replace("<kind>", "job_failed"));
    expect(res?.status()).toBeLessThan(400);
    await expect(page.locator("h1")).not.toBeEmpty();
  });
  if (link.path.includes("<id>")) {
    test(`link ${link.path} unknown id shows not found`, async ({ page, context }) => {
      await context.addCookies([await sessionCookie()]);
      await page.goto(link.path.replace("<id>", MOCK_IDS.unknown).replace("<kind>", "job_failed"));
      await expect(page.getByText(/not found|isn't in the list/)).toBeVisible();
    });
  }
}
```

```python
# tests/test_link_contract.py
def test_every_alert_path_is_in_the_contract() -> None:
    contract = json.loads(Path("web/lib/links.json").read_text())
    prefixes = [c["path"].split("<")[0] for c in contract if c["exists"]]
    for path in alert_paths_in_source():          # greps `path="/...` and `row_id=` kinds in src/
        assert any(path.startswith(p) for p in prefixes), path
```

- [ ] **Step 2: Run and see them fail**

Run: `npm --prefix web run test` and `npm --prefix web run e2e -- home act links`
Expected: FAIL.

- [ ] **Step 3: Implement**

- **Pages:** follow the mockups `home.html` and `act.html` and `docs/design/dashboard/DESIGN.md`. `/act` reads `?after=` for Next; actions call `POST /api/cf/needs/...`; a 409 shows the "already handled" state with who, when and where.
- **Mocks:** `MOCK_NEEDS` and `MOCK_SCOREBOARD`, plus `?mock=empty` for the empty state (allowed only with `MOCK_API=1`).
- **Link contract:** set `exists: true` for `/`, `/?needs=<kind>`, `/act/<kind>/<id>` and `/jobs/<id>`.

- [ ] **Step 4: Run and see them pass**

Run: `npm --prefix web run check` and `npm --prefix web run e2e`, then `uv run pytest -q tests/test_link_contract.py`
Expected: PASS.

- [ ] **Step 5: Check and record — checkpoint S3-2**

1. Run the full `scripts/check.sh` and `scripts/check.sh --e2e`.
2. Ask `pr-reviewer` to review.
3. Write the report: list the S2 providers registered, and those left for the S2 cards' follow-ups.
4. Suggested commit: `NNN: s3-2: needs API, Home, act view, link contract, alert Open buttons`.

**Owner steps (S3-2):**
0. **Pre-deploy check (#623):** no other code card is on `main` undeployed (`docs/ops/deploys.md` against `git log`), and `uv run modal run src/clipforge/app.py::db_doctor` shows the expected head (S3's `NNNN`).
1. `scripts/deploy.sh --dry-run`, then `scripts/deploy.sh --reason "S3-2: needs, Home, act"`. There is no migration.
2. Online (after card 004): redeploy the dashboard from `main` (`vercel deploy --prod` in `web/`, or the Git integration). Open Home on the phone: needs, the meter, the scoreboard, slots.
3. The next ops alert with a row (a failed job, a permission hold) carries Open ↗ → `/act/...`. Act on it in the dashboard; the Telegram message turns into "✅ Done by web:<login>".

**What the owner sees:** Home as the daily check-in; Open buttons that land on `/act`; alerts marked done after acting.

**Rollback (S3-2):** a revert deploy. `alert:msg:*` keys are short-lived and ignored by the old code; `needs_log` rows stay and are harmless. Revert the dashboard's deploy in Vercel (Promote the previous deployment).

---

# Part S3-3: Review and Calendar

### Task 12: Move to the front (`posting/actions.pin`)

**Files:**
- Modify: `src/clipforge/models.py` (`PostRecord.pinned_at: datetime | None = None`), `src/clipforge/posting/repo.py` (`set_pin` on `PostingRepo`; Dict raises `PinUnsupported`; Dual calls the primary only and never mirrors), `src/clipforge/db/posting.py` (reads `queue_pin`; `set_pin`), `src/clipforge/posting/actions.py` (`pin`), `src/clipforge/posting/queue.py` (`pick_next`), `src/clipforge/posting/migrate.py` (verify excludes `queue_pin` and `pinned`/`unpinned` events)
- Test: `tests/posting/test_pin.py`, `tests/posting/test_queue.py` (add), `tests/posting/test_migrate.py` (add)

**Interfaces:**
- Produces:
  - `PostingRepo.set_pin(ref: str, at: datetime | None, actor: str) -> None` (SQL: `UPDATE content_items SET queue_pin=:at`, plus a `post_events` row of kind `pinned` or `unpinned` with `actor`);
  - `PinUnsupported(Exception)`;
  - `actions.pin(posting: Posting, ref: str, on: bool, actor: str, now: datetime) -> None`. It raises `ActionFailed("Move to the front needs the database")` when the repo raises `PinUnsupported`; the route maps that to 409.
  - **`active_pin(r: PostRecord) -> datetime | None`:** the pin, if `pinned_at` is later than the last send's `at`, else `None`.
  - **`pick_next`:** among eligible records with an active pin, the oldest pin wins, then today's rules. The video and channel rule applies to pinned items too.
  - On accounts that publish through Upload-Post, the slot plan is made at 08:50 (S2's `dispatch/plan.py`, which also calls `pick_next`), so a pin made after the plan takes effect at the next plan; the Queue tab says so on those accounts.

- [ ] **Step 1: Write the failing tests**

```python
# tests/posting/test_pin.py
def test_pin_moves_item_to_front(sql_posting) -> None:
    low = add_item(sql_posting, score=0.81); add_item(sql_posting, score=0.95)
    actions.pin(sql_posting, low, True, "web:octo", NOW)
    assert pick_next(sql_posting.repo.records("realtalk-clips-en"), NOW).item.id == low

def test_send_ends_the_pin_without_writing_it(sql_posting) -> None:
    ref = add_item(sql_posting); actions.pin(sql_posting, ref, True, "web:octo", NOW)
    sql_posting.repo.add_send(ref, PostSend(n=1, at=NOW + timedelta(minutes=5)))
    rec = sql_posting.repo.get(ref)
    assert rec.pinned_at == NOW and active_pin(rec) is None          # column untouched, pin inactive

def test_old_pin_after_rollback_does_not_jump(sql_posting) -> None:
    ref = add_item(sql_posting); actions.pin(sql_posting, ref, True, "web:octo", NOW)
    sql_posting.repo.add_send(ref, PostSend(n=1, at=NOW + timedelta(days=1)))
    other = add_item(sql_posting, score=0.99)
    assert pick_next(sql_posting.repo.records("realtalk-clips-en"), NOW + timedelta(days=3)).item.id == other

def test_pin_in_dict_mode_answers_needs_database(dict_posting) -> None:
    with pytest.raises(ActionFailed, match="needs the database"):
        actions.pin(dict_posting, add_item(dict_posting), True, "web:octo", NOW)

def test_pin_writes_event_with_actor(sql_posting, db) -> None:
    ref = add_item(sql_posting); actions.pin(sql_posting, ref, True, "web:octo", NOW)
    assert last_event(db, ref) == ("pinned", "web:octo")

def test_pin_while_braked_records_and_sends_nothing(sql_posting, bot_ctx) -> None:   # Review Focus 4
    actions.pause(bot_ctx, "realtalk-clips-en", True, "telegram:42", NOW)
    ref = add_item(sql_posting); actions.pin(sql_posting, ref, True, "web:octo", NOW)
    assert sql_posting.repo.get(ref).pinned_at == NOW and bot_ctx.sender.sent_videos == []
```

```python
# tests/posting/test_migrate.py (add)
def test_verify_ignores_pins(dual_env) -> None:
    actions.pin(dual_env.posting, dual_env.ref, True, "web:octo", NOW)
    assert verify(dual_env.dict_repo, dual_env.sql_repo).differences == []
```

- [ ] **Step 2: Run, implement, pass**

Run: `uv run pytest -q tests/posting` (FAIL first). Implement; Dual's `set_pin` calls the primary and skips `_mirror`. Rerun: PASS.

- [ ] **Step 3: Check and record**

Run `scripts/check.sh --python`.

### Task 13: Queue routes, batch approve and pause

**Files:**
- Create: `src/clipforge/api/admin/posting.py`, `src/clipforge/api/admin/review.py`
- Modify: `src/clipforge/models.py`, `src/clipforge/api/admin/__init__.py`
- Test: `tests/api/admin/test_posting_api.py`, `tests/api/admin/test_review_batch_api.py`

**Interfaces:**
- Produces:
  - `QueueRow(ref, account_id, title, score, status: PostStatus, pinned: bool, held: str | None, next_up: bool, sends: int, posted: list[Platform])`; `QueueView(account_id, paused: bool, brake: bool, rows: list[QueueRow])`.
  - `GET /admin/posting/queue?account=` → `QueueView` (eligible first in `pick_next` order, then held, then the rest).
  - `POST /admin/posting/{ref}/pin` and `DELETE /admin/posting/{ref}/pin` → 204 (409 in dict mode).
  - `POST /admin/posting/{ref}/skip`, `POST …/reject` with `{reason: RejectReason | None}`, `PUT …/reason` with `{reason: RejectReason}` (a reason added after a reject), and `PUT …/posted` with `{platform, on}` → 204; each through `posting/actions` (`skip`, `reject`, `set_reason`, `set_posted`) with the actor; every action redraws the item's Telegram messages (`actions.redraw_all`).
  - `POST /admin/accounts/{id}/pause` with `{on: bool, reason: str | None}` → `{reply: str}`, through `posting/actions.pause` (S2 writes the brake key and `posting_state`).
  - **Only if S2b's review service is on `main`:** `POST /admin/review/batch` with `{refs: list[str], action: Literal["approve"]}` → `list[BatchDecision(ref, kind, by, at, message)]`, looping `ReviewService.approve(ref, actor, now)` and continuing past `already` and `missed`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/api/admin/test_posting_api.py
def test_queue_lists_next_up_first(admin_client, three_queued) -> None:
    rows = admin_client.get("/admin/posting/queue?account=realtalk-clips-en", headers=ADMIN).json()["rows"]
    assert rows[0]["next_up"] is True

def test_skip_requires_actor_and_redraws(admin_client, sent_item, sender) -> None:
    assert admin_client.post(f"/admin/posting/{sent_item}/skip", headers=ADMIN).status_code == 400
    assert admin_client.post(f"/admin/posting/{sent_item}/skip", headers=ADMIN | ACTOR).status_code == 204
    assert sender.edited                                     # the Telegram card redrawn

def test_posted_correction_through_actions(admin_client, sent_item, db) -> None:
    admin_client.put(f"/admin/posting/{sent_item}/posted", headers=ADMIN | ACTOR, json={"platform": "tiktok", "on": False})
    assert last_event(db, sent_item)[1] == "web:octo"

def test_pause_account_writes_brake(admin_client, kv) -> None:
    admin_client.post("/admin/accounts/realtalk-clips-en/pause", headers=ADMIN | ACTOR, json={"on": True})
    assert json.loads(kv.get("brake:realtalk-clips-en"))["on"] is True
```

```python
# tests/api/admin/test_review_batch_api.py (only with S2b)
def test_batch_approve_continues_past_already(admin_client, two_review_items, review_service) -> None:
    review_service.approve(two_review_items[0], "telegram:42", NOW)
    out = admin_client.post("/admin/review/batch", headers=ADMIN | ACTOR,
                            json={"refs": two_review_items, "action": "approve"}).json()
    assert [d["kind"] for d in out] == ["already", "approved"]
```

- [ ] **Step 2: Run, implement, pass**

Run: `uv run pytest -q tests/api/admin` (FAIL first). Implement. Regenerate OpenAPI and the client. Rerun: PASS.

- [ ] **Step 3: Check and record**

Run `scripts/check.sh --python --web`.

### Task 14: Review page (Queue and Review lane)

**Files:**
- Create: `web/app/(app)/review/page.tsx`, `web/components/review/QueueTab.tsx`, `ReviewLaneTab.tsx`, `ReviewDetail.tsx`, `BatchBar.tsx`, the route handlers `web/app/api/cf/posting/queue/route.ts`, `posting/[ref]/[action]/route.ts`, `review/route.ts`, `review/[item]/[action]/route.ts`, `review/batch/route.ts`, and `web/e2e/review.spec.ts`
- Modify: `web/lib/mocks.ts`, `web/components/nav.ts` (Review), `web/lib/links.ts` (`/review?account=<id>` → `exists: true`)

**Interfaces:**
- Consumes: Task 13's routes; S2's `GET /admin/review`, `POST /admin/review/{item}/approve|reject` and `PUT /admin/review/{item}/copy`, when merged. The handler returns 404 → the page shows "The review lane arrives with publishing (S2b)".
- Produces:
  - `/review?tab=queue|lane&account=` (default `lane` when it has rows, else `queue`).
  - Queue: per account, next up, Move to the front, Skip, Reject with a reason, ✅ per platform.
  - Lane: the queue with reasons and due times, the selected item's video (S2's signed media link), gate answers, copy per platform (editable, `PUT …/copy`), Approve, Reject, the batch bar (laptop only), and the hook 👍/👎 (shown only when the hooks build is merged).
  - **Re-render:** a disabled button titled "arrives with the hooks build" (#619).
  - **Phone:** lists only; a row opens `/act/review_due/<item>` or `/act/held_clips/<account>`.

- [ ] **Step 1: Write the failing tests**

```ts
// web/e2e/review.spec.ts
test("queue: move to the front reorders", async ({ page, context }) => {
  await context.addCookies([await sessionCookie()]);
  await page.goto("/review?tab=queue&account=realtalk-clips-en");
  const third = page.getByRole("row").nth(3);
  await third.getByRole("button", { name: "Move to the front" }).click();
  await expect(page.getByRole("row").nth(1)).toContainText(await third.textContent() ?? "");
});

test("lane without S2b says when it arrives", async ({ page, context }) => {
  await context.addCookies([await sessionCookie()]);
  await page.goto("/review?tab=lane&mock=nolane");
  await expect(page.getByText("The review lane arrives with publishing (S2b)")).toBeVisible();
});

test("re-render is disabled until the hooks build", async ({ page, context }) => {
  await context.addCookies([await sessionCookie()]);
  await page.goto("/review?tab=lane");
  await expect(page.getByRole("button", { name: "Re-render" })).toBeDisabled();
});

test("phone: a lane row opens act", async ({ page, context, isMobile }) => {
  test.skip(!isMobile);
  await context.addCookies([await sessionCookie()]);
  await page.goto("/review?tab=lane");
  await page.getByRole("link").filter({ hasText: "realtalk" }).first().click();
  await expect(page).toHaveURL(/\/act\/review_due\//);
});
```

- [ ] **Step 2: Run, implement, pass**

Run: `npm --prefix web run e2e -- review` (FAIL first). Implement from `review.html`. Rerun: PASS, then `npm --prefix web run check`.

- [ ] **Step 3: Check and record**

Run `scripts/check.sh --web`.

### Task 15: Calendar

**Files:**
- Create: `web/app/(app)/calendar/page.tsx`, `web/components/calendar/Week.tsx`, `web/e2e/calendar.spec.ts`
- Modify: `web/lib/mocks.ts`, `web/components/nav.ts` (Calendar)

**Interfaces:**
- Consumes: `GET /admin/slots?from=&to=&account=` (Task 9), `POST /admin/accounts/{id}/pause` (Task 13).
- Produces: `/calendar?week=YYYY-Www&account=`. It shows a week per account and platform (posted, failed, next, waiting for approval, missed) and a Pause/Go toggle per account, with the reply shown. **There is no drag to reschedule in S3:** slot moves belong to the S2 planner and wait for a later card. The page says "Rescheduling comes later; pause an account or edit its slots with `clipforge account edit`".

- [ ] **Step 1: Write the failing test**

```ts
// web/e2e/calendar.spec.ts
test("calendar shows the week and pauses an account", async ({ page, context }) => {
  await context.addCookies([await sessionCookie()]);
  await page.goto("/calendar?week=2026-W43");
  await expect(page.getByText("realtalk-clips-en")).toBeVisible();
  await page.getByRole("button", { name: "Pause realtalk-clips-en" }).click();
  await expect(page.getByText(/paused/i)).toBeVisible();
});
```

- [ ] **Step 2: Run, implement, pass**

Run: `npm --prefix web run e2e -- calendar` (FAIL first). Implement. Rerun: PASS.

- [ ] **Step 3: Check and record — checkpoint S3-3**

1. Run the full `scripts/check.sh` and `scripts/check.sh --e2e`.
2. Ask `pr-reviewer` and `migration-reviewer` (posting repo and verify changes) to review.
3. Write the report.
4. Suggested commit: `NNN: s3-3: review (queue and lane), move to the front, calendar`.

**Owner steps (S3-3):**
0. **Pre-deploy check (#623):** no other code card is on `main` undeployed (`docs/ops/deploys.md` against `git log`), and `uv run modal run src/clipforge/app.py::db_doctor` shows the expected head (S3's `NNNN`).
1. `scripts/deploy.sh --dry-run`, then `scripts/deploy.sh --reason "S3-3: review and calendar"`.
2. `uv run clipforge posting verify`: still 0 differences (pins are excluded).
3. Online: open Review → Queue, move one clip to the front, and check that the next slot sends it.
4. **After 7 days of Review online with no problems (#617):** set `REVIEW_BATCH=off` with the `docs/ops/secrets.md` procedure, then `scripts/deploy.sh --reason "REVIEW_BATCH off"`. Only the 2 h cards remain.

**What the owner sees:** Review with both tabs; the queue reorderable from the phone; Calendar.

**Rollback (S3-3):** a revert deploy. `queue_pin` values stay, and the old `pick_next` ignores them. `REVIEW_BATCH=on` brings the morning batch back.

---

# Part S3-4: Produce, Jobs and Sources

### Task 16: The batch planner (`produce/`)

**Files:**
- Create: `src/clipforge/produce/__init__.py`, `src/clipforge/produce/estimate.py`, `src/clipforge/produce/batches.py`
- Modify: `src/clipforge/models.py`, `src/clipforge/needs/providers.py` (`SpendLineProvider`)
- Test: `tests/produce/test_estimate.py`, `tests/produce/test_batches.py`

**Interfaces:**
- Produces:
  - `BatchInput(source_id: str, volume_path: str | None = None, url: HttpUrl | None = None)`: exactly one of `volume_path` and `url`. `volume_path` must be under `JOBS_ROOT/uploads/` and pass `jobs`' path checks.
  - `BatchRequest(account_id: str, kind: Literal["clips"] = "clips", inputs: list[BatchInput] (1–50), options: ClipOptions = ClipOptions())`.
  - `StageEstimate(stage: str, usd: float)`.
  - `BatchPreview(estimate: list[StageEstimate], total_usd: float, review_minutes: float, month_spend_usd: float, cap_usd: float, line_usd: float, over_line: bool, held: list[HeldInput])`; `HeldInput(source_id, reason)`.
  - `BatchCreated(job_ids: list[str] | None, pending_row: str | None)`.
  - `estimate(db, account, request) -> BatchPreview`:
    - stage costs = source hours × the account's median USD per source hour per stage, over its last 20 done jobs (from `jobs.costs`);
    - before any history, `Prices` × typical seconds (transcribe 0.05 $/h, highlights 0.07 $/h, CPU 0.03 per job, §Observability);
    - source hours come from `ffmpeg.probe_info` on Volume inputs, or 1 h for links (labelled "estimated");
    - `review_minutes` uses §2.7 at the account's rung;
    - `line_usd` and `cap_usd` come from `AutopilotService.get(account_id)`;
    - `month_spend_usd` is the sum of the month's `jobs.costs` for the account.
  - `preview(ctx, request) -> BatchPreview`.
  - `create(ctx, request, actor, now) -> BatchCreated`:
    - every `source_id` must exist and belong to the account, else `UnknownSource(ActionFailed)` → **400**; and pass `sources.hold_reason`, else `SourceHeld(ActionFailed)` naming the rule → **409** (held ones are listed in the preview);
    - under the line, one `service.create_job` per input with `JobInput(channel=…, source_credit=…, permission=…, source_label=…)` as `clipforge clip` builds it;
    - over the line, `BatchesRepo.add` → `pending_row = f"spend_line:{id}"`.
  - `approve(ctx, batch_id, actor, now) -> BatchCreated`:
    - `BatchesRepo.decide(id, "approved")`; False → `AlreadyDone(by, at)` from the row;
    - then create the jobs, `BatchesRepo.created(id, job_ids)`.
  - `decline(ctx, batch_id, actor, now)`.
  - `SpendLineProvider`: instant rows from `BatchesRepo.pending()`; actions `approve` and `decline`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/produce/test_batches.py
def test_under_line_creates_jobs_with_source_fields(produce_env) -> None:
    out = create(produce_env.ctx, req(n=1, hours=1.0), "web:octo", NOW)
    job = produce_env.jobs[out.job_ids[0]]
    assert job.input.source_credit == "Billy Garton Jr." and job.input.permission == "creator_agreement"

def test_over_line_writes_pending_and_a_row(produce_env) -> None:
    out = create(produce_env.ctx, req(n=10, hours=3.0), "web:octo", NOW)
    assert out.job_ids is None and out.pending_row.startswith("spend_line:")
    assert REGISTRY[NeedsKind.SPEND_LINE].rows(produce_env.needs_ctx, NOW)[0].level == "instant"

def test_double_approve_creates_jobs_once(produce_env) -> None:          # Review Focus 1
    bid = int(create(produce_env.ctx, req(n=10, hours=3.0), "web:octo", NOW).pending_row.split(":")[1])
    approve(produce_env.ctx, bid, "web:octo", NOW)
    with pytest.raises(AlreadyDone):
        approve(produce_env.ctx, bid, "telegram:42", NOW)
    assert len(produce_env.jobs) == 10

def test_unknown_or_foreign_source_refused(produce_env) -> None:
    with pytest.raises(UnknownSource):
        create(produce_env.ctx, req(source_id="someone-else"), "web:octo", NOW)

def test_held_source_flagged_in_preview_refused_on_create(produce_env_expired_source) -> None:
    p = preview(produce_env_expired_source.ctx, req())
    assert p.held and p.held[0].reason.startswith("permission")
    with pytest.raises(SourceHeld, match="permission"):
        create(produce_env_expired_source.ctx, req(), "web:octo", NOW)

def test_line_and_cap_come_from_autopilot(produce_env) -> None:
    produce_env.autopilot.set("realtalk-clips-en", "batch_line_usd", 5.0, "web:octo", "test", NOW)
    assert preview(produce_env.ctx, req()).line_usd == 5.0

def test_caps_shown_not_enforced(produce_env_month_over_cap) -> None:
    assert create(produce_env_month_over_cap.ctx, req(n=1, hours=0.2), "web:octo", NOW).job_ids
```

```python
# tests/produce/test_estimate.py
def test_estimate_uses_measured_median(db, account_with_jobs) -> None:
    p = estimate(db, account_with_jobs, req(hours=2.0))
    assert p.total_usd == pytest.approx(2.0 * MEDIAN_PER_HOUR, rel=0.01)

def test_estimate_without_history_uses_prices(db, new_account) -> None:
    assert estimate(db, new_account, req(hours=1.0)).total_usd == pytest.approx(0.05 + 0.07 + 0.03, rel=0.05)
```

- [ ] **Step 2: Run, implement, pass**

Run: `uv run pytest -q tests/produce` (FAIL first). Implement. Rerun: PASS.

- [ ] **Step 3: Check and record**

Run `scripts/check.sh --python`.

### Task 17: Produce, jobs and episodes routes

**Files:**
- Create: `src/clipforge/api/admin/produce.py`
- Modify: `src/clipforge/api/admin/__init__.py` (it calls `accounts/runway.episodes`, from Task 7)
- Test: `tests/api/admin/test_produce_api.py`

**Interfaces:**
- Produces:
  - `POST /admin/batches/preview` (`BatchRequest`) → `BatchPreview`, which writes nothing;
  - `POST /admin/batches` (`BatchRequest`, actor required) → `BatchCreated`;
  - `GET /admin/jobs?account=&status=&limit=50` → `list[JobSummary]` (S1's `jobs` table, newest first);
  - `GET /admin/accounts/{id}/sources` → `list[Source]`;
  - `GET /admin/accounts/{id}/episodes` → `list[Episode]`, where `Episode(source_id, name, volume_path, hours, state: Literal["clipped","clipping","imported"], job_id: str | None)` is defined in Task 7.

- [ ] **Step 1: Write the failing tests**

```python
# tests/api/admin/test_produce_api.py
def test_preview_writes_nothing(admin_client, db, source) -> None:
    admin_client.post("/admin/batches/preview", headers=ADMIN, json=BODY)
    assert count(db, "batches") == 0 and count(db, "jobs") == 0

def test_create_requires_actor(admin_client, source) -> None:
    assert admin_client.post("/admin/batches", headers=ADMIN, json=BODY).status_code == 400

def test_input_needs_exactly_one_of_path_or_url(admin_client, source) -> None:
    bad = BODY | {"inputs": [{"source_id": "billy", "volume_path": "uploads/a.mp4", "url": "https://x/a.mp4"}]}
    assert admin_client.post("/admin/batches/preview", headers=ADMIN, json=bad).status_code == 422

def test_unknown_source_400_held_source_409(admin_client, source, expired_source) -> None:
    assert admin_client.post("/admin/batches", headers=ADMIN | ACTOR, json=BODY | {"inputs": [{"source_id": "nope", "url": "https://x/a.mp4"}]}).status_code == 400
    assert admin_client.post("/admin/batches", headers=ADMIN | ACTOR, json=BODY | {"inputs": [{"source_id": expired_source, "url": "https://x/a.mp4"}]}).status_code == 409

def test_path_outside_uploads_rejected(admin_client, source) -> None:
    bad = BODY | {"inputs": [{"source_id": "billy", "volume_path": "../etc/passwd"}]}
    assert admin_client.post("/admin/batches/preview", headers=ADMIN, json=bad).status_code == 422

def test_episodes_list_states(admin_client, clipped_and_imported) -> None:
    states = {e["state"] for e in admin_client.get("/admin/accounts/realtalk-clips-en/episodes", headers=ADMIN).json()}
    assert states == {"clipped", "imported"}
```

- [ ] **Step 2: Run, implement, pass**

Run: `uv run pytest -q tests/api/admin/test_produce_api.py` (FAIL first). Implement. Regenerate OpenAPI and the client. Rerun: PASS.

- [ ] **Step 3: Check and record**

Run `scripts/check.sh --python --web`.

### Task 18: Produce page, the Jobs tab, Resume on the job page, Sources pages

**Files:**
- Create:
  - pages: `web/app/(app)/produce/page.tsx`, `web/app/(app)/sources/page.tsx`, `web/app/(app)/sources/[id]/page.tsx`;
  - components: `web/components/produce/Planner.tsx`, `Estimate.tsx`, `JobsTab.tsx`, `web/components/sources/SourceForm.tsx`;
  - route handlers under `web/app/api/cf/` for batches, jobs, accounts episodes and sources, sources (GET, POST, PUT through S1's `/sources` routes) and job resume;
  - tests: `web/e2e/produce.spec.ts`, `web/e2e/sources.spec.ts`.
- Modify: `web/app/(app)/jobs/[id]/page.tsx` (a Resume button for failed jobs, `POST /jobs/{id}/resume`), `web/components/nav.ts` (Produce, Sources; Jobs leaves the top level, `/jobs` and `/jobs/<id>` stay), `web/lib/links.ts` (`/sources/<id>`, `/jobs/<id>`), `web/lib/mocks.ts`

**Interfaces:**
- Consumes: Task 17's routes; S1's `/sources` and `POST /jobs/{id}/resume`.
- Produces:
  - **`/produce?account=&tab=plan|jobs`:** pick a source and its imported episodes (or paste a link) → the live preview (stage costs, total, review minutes, month spend against the cap, the line, held sources) → "Queue N jobs", or "Ask me on Home" when over the line;
  - **the Jobs tab:** the jobs list with status and cost, and a job id lookup;
  - **`/sources` and `/sources/<id>`:** list, detail with the permission record and history, add and edit.

- [ ] **Step 1: Write the failing tests**

```ts
// web/e2e/produce.spec.ts
test("plan under the line queues jobs", async ({ page, context }) => {
  await context.addCookies([await sessionCookie()]);
  await page.goto("/produce?account=realtalk-clips-en");
  await page.getByLabel("Source").selectOption("billy-garton");
  await page.getByRole("checkbox", { name: /Episode 12/ }).check();
  await expect(page.getByText(/Total \$0\.\d\d/)).toBeVisible();
  await page.getByRole("button", { name: "Queue 1 job" }).click();
  await expect(page.getByRole("link", { name: /20261020-/ })).toBeVisible();
});

test("over the line asks on Home", async ({ page, context }) => {
  await context.addCookies([await sessionCookie()]);
  await page.goto("/produce?account=realtalk-clips-en&mock=overline");
  await expect(page.getByRole("button", { name: "Ask me on Home" })).toBeVisible();
});

test("failed job page has Resume", async ({ page, context }) => {
  await context.addCookies([await sessionCookie()]);
  await page.goto("/jobs/20261019-3fa9c1d2-4b7e");
  await expect(page.getByRole("button", { name: "Resume" })).toBeVisible();
});
```

- [ ] **Step 2: Run, implement, pass**

Run: `npm --prefix web run e2e -- produce sources` (FAIL first). Implement from `produce.html`. Rerun: PASS.

- [ ] **Step 3: Check and record — checkpoint S3-4**

1. Run the full `scripts/check.sh` and `scripts/check.sh --e2e`.
2. Ask `pr-reviewer` and `security-reviewer` (input paths and URLs for job creation) to review.
3. Write the report.
4. Suggested commit: `NNN: s3-4: produce with batches, jobs tab and resume, sources`.

**Owner steps (S3-4):**
0. **Pre-deploy check (#623):** no other code card is on `main` undeployed (`docs/ops/deploys.md` against `git log`), and `uv run modal run src/clipforge/app.py::db_doctor` shows the expected head (S3's `NNNN`).
1. `scripts/deploy.sh --dry-run`, then `scripts/deploy.sh --reason "S3-4: produce"`.
2. Online: Produce → one imported episode → Queue 1 job; the job appears in the Jobs tab and finishes as with `clipforge clip`.
3. Try a batch over $2: it shows up on Home as a spend row; approve it there.
4. **Start the 7-day clock** for `/clip`, `/status <id>` and typed `/resume` (§11.9); S3-5b retires them.

**What the owner sees:** clip jobs started from the phone with the cost first; Resume on a failed job's page; Sources editable in the dashboard.

**Rollback (S3-4):** a revert deploy. `batches` rows stay; pending ones are inert without the code.

---

# Part S3-5: Results, Compare, the account view

### Task 19: Results → Costs

**Files:**
- Create: `src/clipforge/results.py`, `src/clipforge/api/admin/results.py`, `web/app/(app)/results/page.tsx`, `web/components/results/CostsTab.tsx`, `web/components/results/CumulativeChart.tsx`, `web/e2e/results.spec.ts`, `tests/test_results.py`
- Modify: `src/clipforge/models.py`, `web/components/nav.ts` (Results), `web/lib/links.ts` (`/results?tab=costs&account=<id>`)

**Interfaces:**
- Produces:
  - `CostsReport(from_: date, to: date, by_account: list[AccountCost(account_id, usd, cap_usd, by_stage: dict[str, float])], daily_cumulative: list[DayCost(day, usd)], fleet_cap_usd: float, fixed: list[FixedSubscription], fixed_total_usd: float)`.
  - `costs(db, settings_db, start, end, accounts: list[str] | None) -> CostsReport`, from `jobs.costs`; caps from `autopilot`; the fleet cap and the fixed list from `settings`.
  - `GET /admin/results/costs?from=&to=&accounts=` (at most 92 days).
  - **The page:**
    - tabs Stats, Money and Costs; Stats and Money show "Views and revenue arrive with analytics (S7)";
    - Costs has the cumulative line with the cap as a reference line, per-account caps, and the fixed subscriptions "not counted against caps";
    - a table view under the chart, following the dataviz rules (§7.7).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_results.py
def test_costs_sum_jobs_by_account_and_stage(db, two_accounts_with_jobs) -> None:
    r = costs(db, db, date(2026, 10, 1), date(2026, 10, 31), None)
    assert {a.account_id for a in r.by_account} == {"realtalk-clips-en", "founder-tapes-en"}
    assert r.by_account[0].by_stage["transcribe"] > 0

def test_fixed_not_in_variable_total(db, two_accounts_with_jobs) -> None:
    r = costs(db, db, date(2026, 10, 1), date(2026, 10, 31), None)
    assert r.daily_cumulative[-1].usd == pytest.approx(sum(a.usd for a in r.by_account))
```

```ts
// web/e2e/results.spec.ts
test("costs tab has a chart, a table and fixed subscriptions", async ({ page, context }) => {
  await context.addCookies([await sessionCookie()]);
  await page.goto("/results?tab=costs&account=realtalk-clips-en");
  await expect(page.getByRole("img", { name: /Cumulative variable spend/ })).toBeVisible();
  await expect(page.getByRole("table")).toBeVisible();
  await expect(page.getByText("not counted against caps")).toBeVisible();
});
```

- [ ] **Step 2: Run, implement, pass**

Run: `uv run pytest -q tests/test_results.py` and `npm --prefix web run e2e -- results` (FAIL first). Implement from `results.html`; load the `dataviz` skill before writing the chart. Regenerate OpenAPI and the client. Rerun: PASS.

- [ ] **Step 3: Check and record**

Run `scripts/check.sh --python --web`.

### Task 20: Compare, overview, activity and strikes routes

**Files:**
- Create: `src/clipforge/api/admin/accounts.py`
- Modify: `src/clipforge/fleet.py`, `src/clipforge/models.py`, `src/clipforge/api/admin/__init__.py`
- Test: `tests/test_fleet.py` (add), `tests/api/admin/test_accounts_admin_api.py`

**Interfaces:**
- Produces:
  - `CompareRow(account_id, handle, kind, rung, lifecycle_day, runway_days, approval_rate: float | None, cost_per_item_usd: float | None, owner_minutes_day: float, last_autopilot_change: str | None, views: int | None = None)`.
  - `Focus(account_id, reason: str, score: float)`; `CompareView(rows, focus: list[Focus])`.
  - **The focus ranking:** one point per open instant row, 0.5 per digest row, plus 1 when runway is under 14 days, plus 1 for an open review window. The top 3 accounts, each with its main reason.
  - `GET /admin/accounts/compare?days=7` → `CompareView`.
  - `AccountOverview(account: Account, autopilot: dict | None, loop: list[LoopPanel(step, control, number, label, href)], next_rung: dict | None, lifecycle_day: int, payout: list[PayoutProgress])`. `next_rung` comes from S2's ladder route data when S2c is merged.
  - `GET /admin/accounts/{id}/overview` → `AccountOverview`.
  - `ActivityLine(at, kind: Literal["produced","auto_approved","posted","demoted","promoted","autopilot_change","strike"], text, href: str | None)`, from `post_events`, `jobs` and `autopilot_events`.
  - `GET /admin/accounts/{id}/activity?date=` → `list[ActivityLine]`.
  - `POST /admin/accounts/{id}/strikes` with `{platform: Platform, note: str | None}`, actor required: calls `AutopilotService.record_strike(account_id, platform, actor, now)` (S2 Task 21). The strike event carries `web:<login>`; the demotion it triggers stays `system:demotion` (ADR-48). Without S2c it answers 404 "arrives with S2c".

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_fleet.py (add)
def test_focus_ranks_open_rows_and_runway(db, deps, kv, three_accounts) -> None:
    v = compare(db, deps, kv, days=7, now=NOW)
    assert v.focus[0].account_id == "realtalk-clips-en" and "runway" in v.focus[0].reason

def test_activity_reads_autopilot_events(db, account_with_demotion) -> None:
    lines = activity(db, "realtalk-clips-en", date(2026, 10, 19))
    assert any(l.kind == "demoted" and "system:demotion" in l.text for l in lines)
```

```python
# tests/api/admin/test_accounts_admin_api.py
def test_strike_records_owner_and_demotion_by_system(admin_client, supervised_account, db) -> None:   # with S2c
    admin_client.post("/admin/accounts/realtalk-clips-en/strikes", headers=ADMIN | ACTOR, json={"platform": "tiktok"})
    events = autopilot_events(db, "realtalk-clips-en")
    assert events[-2].actor == "web:octo" and events[-1].actor == "system:demotion"

def test_overview_unknown_account_404(admin_client) -> None:
    assert admin_client.get("/admin/accounts/nope/overview", headers=ADMIN).status_code == 404
```

- [ ] **Step 2: Run, implement, pass**

Run: `uv run pytest -q tests/test_fleet.py tests/api/admin` (FAIL first). Implement. Regenerate OpenAPI and the client. Rerun: PASS.

- [ ] **Step 3: Check and record**

Run `scripts/check.sh --python --web`.

### Task 21: Compare page and the account read view

**Files:**
- Create: `web/app/(app)/accounts/page.tsx`, `web/app/(app)/accounts/[id]/page.tsx`, `web/components/accounts/Compare.tsx`, `Overview.tsx`, `AutopilotTab.tsx`, `ActivityTab.tsx`, `SourcesEpisodesTab.tsx`, `StrikeForm.tsx`, the route handlers under `web/app/api/cf/accounts/**` (compare, overview, activity, strikes, and S2's autopilot, promote and ladder), and `web/e2e/accounts.spec.ts`
- Modify: `web/components/nav.ts` (Accounts), `web/lib/links.ts` (`/accounts/<id>`, `/accounts/<id>?tab=<tab>`, `/accounts?view=compare` → `exists: true`)

**Interfaces:**
- Consumes: Task 20's routes; S2's `GET|PUT /admin/accounts/{id}/autopilot`, `POST …/autopilot/promote` and `GET …/ladder`.
- Produces:
  - **`/accounts?view=compare`:** three focus cards, then the table. Map isn't built here (S3c); the page says "The studio map comes with account workspaces (S3c)".
  - **`/accounts/<id>?tab=overview|autopilot|activity|sources`:**
    - Autopilot shows the presets, the controls with what each waits on, a required reason for dial changes (the form refuses an empty reason before calling), Promote enabled only when the ladder says ready, and the strike form;
    - the `sources` tab appears only for `kind == "clips"`;
    - `?tab=` values the view doesn't have (S3c's) fall back to Overview with a note "comes with account workspaces (S3c)", so 08 §2b's links never break.

- [ ] **Step 1: Write the failing tests**

```ts
// web/e2e/accounts.spec.ts
test("compare leads with three focus cards", async ({ page, context }) => {
  await context.addCookies([await sessionCookie()]);
  await page.goto("/accounts?view=compare");
  await expect(page.getByTestId("focus-card")).toHaveCount(3);
});

test("dial change needs a reason", async ({ page, context }) => {
  await context.addCookies([await sessionCookie()]);
  await page.goto("/accounts/realtalk-clips-en?tab=autopilot");
  await page.getByLabel("Review dial").selectOption("sample");
  await page.getByRole("button", { name: "Apply" }).click();
  await expect(page.getByText("A reason is required to change the Review dial")).toBeVisible();
});

test("unknown tab falls back to overview", async ({ page, context }) => {
  await context.addCookies([await sessionCookie()]);
  await page.goto("/accounts/realtalk-clips-en?tab=style");
  await expect(page.getByText("comes with account workspaces (S3c)")).toBeVisible();
});
```

- [ ] **Step 2: Run, implement, pass**

Run: `npm --prefix web run e2e -- accounts links` (FAIL first). Implement from `accounts.html` and `account.html`, core tabs only. Rerun: PASS.

- [ ] **Step 3: Check and record**

Run `scripts/check.sh --web`.

- [ ] **Step 4: Check and record — checkpoint S3-5**

1. Run the full `scripts/check.sh` and `scripts/check.sh --e2e`.
2. Ask `pr-reviewer` to review.
3. Update `docs/ARCHITECTURE.md`; write the report.
4. Suggested commit: `NNN: s3-5: results costs, compare, account view`.

**Owner steps (S3-5):**
0. **Pre-deploy check (#623):** no other code card is on `main` undeployed (`docs/ops/deploys.md` against `git log`), and `uv run modal run src/clipforge/app.py::db_doctor` shows the expected head (S3's `NNNN`).
1. `scripts/deploy.sh --dry-run`, then `scripts/deploy.sh --reason "S3-5: results, compare, accounts"`.
2. Online: Results → Costs, Accounts → Compare (three focus cards), one account's Overview, Autopilot and Activity.

**What the owner sees:** Results → Costs, Compare for the weekly hour, each account's Overview, Autopilot and Activity.

**Rollback (S3-5):** a revert deploy; it adds no data.

---

# Part S3-5b: retirements and the CLI cut-over (each after its 7-day wait)

S3-5b is its own card. It starts when S3-4's Produce has been used online for 7 days (Task 22) and `admin` has been live for 7 days (Task 23); if only one wait is over, the card does that task and the report names the other.

### Task 22: Retire `/clip`, `/status <id>` and typed `/resume` in Telegram

**Files:**
- Modify: `src/clipforge/bot/commands.py`, `docs/studio/11-owner-runbook.md`, `ROADMAP.md` (the Phase 1 Telegram item: `/clip` retired per ADR-44)
- Test: `tests/bot/test_commands.py` (add)

**Interfaces:**
- Produces:
  - `/clip …` answers "Clip jobs start in Produce now: <DASHBOARD_URL>/produce" and creates nothing;
  - `/status <job_id>` answers with the job page's link `<DASHBOARD_URL>/jobs/<id>`;
  - `/resume <id>` answers with the same link;
  - `/status` with no argument is unchanged;
  - without `DASHBOARD_URL`, the commands keep working as today (nothing to point to).

- [ ] **Step 1: Write the failing tests**

```python
# tests/bot/test_commands.py (add)
def test_clip_points_to_produce(bot_env) -> None:
    bot_env.settings.dashboard_url = "https://dash.example"
    reply = bot_env.command("/clip https://media.example.com/ep.mp4")
    assert "https://dash.example/produce" in reply and bot_env.jobs_created == []

def test_status_without_argument_unchanged(bot_env) -> None:
    bot_env.settings.dashboard_url = "https://dash.example"
    assert "posting" in bot_env.command("/status").lower()

def test_status_with_id_links_job_page(bot_env) -> None:
    bot_env.settings.dashboard_url = "https://dash.example"
    assert "https://dash.example/jobs/20261019-3fa9c1d2-4b7e" in bot_env.command("/status 20261019-3fa9c1d2-4b7e")

def test_without_dashboard_url_commands_still_work(bot_env) -> None:
    bot_env.settings.dashboard_url = None
    bot_env.command("/clip https://media.example.com/ep.mp4")
    assert bot_env.jobs_created
```

- [ ] **Step 2: Run, implement, pass**

Run: `uv run pytest -q tests/bot` (FAIL first). Implement. Write the runbook text: jobs start in Produce (phone or laptop) or with `clipforge clip` for local files; the failure alert keeps [Resume]; `clipforge status <id>` and `clipforge resume <id>` stay on the laptop; `/status` still summarizes posting. Rerun: PASS.

- [ ] **Step 3: Check and record**

Run `scripts/check.sh --python --docs`.

### Task 23: The CLI cut-over to `admin` (#618)

**Files:**
- Modify: `src/clipforge/config.py` (`clipforge_admin_url: str | None`, `modal_proxy_key: SecretStr | None`, `modal_proxy_secret: SecretStr | None`, read by the CLI only), `src/clipforge/cli.py` (the HTTP client sends the proxy headers and `ADMIN_API_TOKEN` to `CLIPFORGE_ADMIN_URL` for every route of `cli_router`, listed in Task 1; uploads keep `modal volume put` and `--fetch` keeps `ModalCliDownloader`, neither touches `web`; `set-webhook` talks to Telegram and needs only the public `web` URL), `src/clipforge/api/main.py` (`cli_router` is mounted on `admin` only: **proposed (#623), S1's `/accounts` and `/sources` writes leave `web` too**, so `web` serves only the public routes; `API_TOKEN` retires a week later. If the owner keeps S1's routes on `web`, split `cli_router` into `s2_admin_router` (leaves) and `s1_router` (stays) in this task), `.env.example`, `docs/ops/secrets.md`, `CLAUDE.md` (Commands: the CLI talks to `admin`)
- Test: `tests/test_cli.py` (add), `tests/api/admin/test_surfaces.py` (add)

**Interfaces:**
- Produces:
  - `cli.ApiClient(base_url, token, proxy: tuple[str, str] | None)`;
  - `web` no longer mounts any `/admin/*` route;
  - the CLI refuses to start an admin call without the three settings, naming the missing ones.

- [ ] **Step 1: Write the failing tests**

```python
# tests/api/admin/test_surfaces.py (add)
def test_web_serves_only_public_routes_after_cut_over(tmp_path) -> None:
    web = create_app(ApiContext(settings=make_settings(tmp_path, api_token="t0ken"), deps=lambda: None, sender=lambda: None), "web")
    paths = {r.path for r in web.routes}
    assert not [p for p in paths if p.startswith("/admin/")]
    assert paths <= PUBLIC_PATHS          # /telegram/webhook, /jobs/{job_id}/download, /webhooks/upload-post, /media/{item_id}.mp4, /go/{slug}
```

```python
# tests/test_cli.py (add)
def test_cli_sends_proxy_headers(recording_transport, monkeypatch) -> None:
    monkeypatch.setenv("CLIPFORGE_ADMIN_URL", "https://admin.example")
    monkeypatch.setenv("MODAL_PROXY_KEY", "wk"); monkeypatch.setenv("MODAL_PROXY_SECRET", "ws"); monkeypatch.setenv("ADMIN_API_TOKEN", "adm")
    main(["autopilot", "show", "realtalk-clips-en"], transport=recording_transport)
    h = recording_transport.requests[0].headers
    assert h["Modal-Key"] == "wk" and h["Authorization"] == "Bearer adm"

def test_cli_names_missing_settings(monkeypatch, capsys) -> None:
    monkeypatch.delenv("MODAL_PROXY_KEY", raising=False)
    assert main(["autopilot", "show", "realtalk-clips-en"]) == 2
    assert "MODAL_PROXY_KEY" in capsys.readouterr().err
```

- [ ] **Step 2: Run, implement, pass**

Run: `uv run pytest -q tests/test_cli.py tests/api/admin/test_surfaces.py` (FAIL first). Implement. Rerun: PASS.

- [ ] **Step 3: Check and record — checkpoint S3-5b**

1. Run the full `scripts/check.sh` and `scripts/check.sh --e2e`.
2. Ask `pr-reviewer`, `security-reviewer` (the cut-over: nothing but public routes left on `web`) and `docs-auditor` to review.
3. Tick S3 in `ROADMAP.md` and `docs/studio/04-roadmap.md` when the exit is met. Update `docs/ARCHITECTURE.md`.
4. Write the report.
5. Suggested commit: `NNN: s3-5b: telegram retirements, CLI on admin`.

**Owner steps (S3-5b):**
0. **Pre-deploy check (#623):** no other code card is on `main` undeployed (`docs/ops/deploys.md` against `git log`), and `uv run modal run src/clipforge/app.py::db_doctor` shows the expected head (S3's `NNNN`).
1. Add `CLIPFORGE_ADMIN_URL`, `MODAL_PROXY_KEY`, `MODAL_PROXY_SECRET` and `ADMIN_API_TOKEN` to the laptop's `.env`, using a second proxy token for the laptop, so either one can be revoked alone.
2. `scripts/deploy.sh --dry-run`, then `scripts/deploy.sh --reason "S3-5b: retirements, CLI on admin"`.
3. Run `uv run clipforge autopilot show realtalk-clips-en` and `uv run clipforge source list` (both through `admin`). Then `curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer <API_TOKEN>" <web url>/admin/review` → `404` (and `<web url>/sources` → `404` if S1's routes moved). A week later, remove `API_TOKEN` from `clipforge-secrets` (the `docs/ops/secrets.md` procedure).
4. In Telegram, `/clip <link>` answers with the Produce link; `/status` still summarizes posting.
5. **The exit (04's S3):** for a week, the daily check-in from the phone in under 20 minutes; every Telegram alert opens its row in `/act`.

**What the owner sees:** Telegram pointing to the dashboard for jobs; the CLI working through `admin`.

**Rollback (S3-5b):** a revert deploy. Then `/clip` creates jobs again, the CLI's old `CLIPFORGE_API_URL` and `API_TOKEN` work again (keep them in `.env` until the cut-over has run for a week), and `web` mounts `/admin/*` again.

---

## Deployable steps

| Step | Tasks | Deployable alone | What the owner sees |
|---|---|---|---|
| S3-1 | 1–5 | yes (after card 010 done and card 014 deployed with its owner steps; migration) | Settings; Home and jobs unchanged, over `admin` |
| S3-2 | 6–11 | yes (after S3-1) | Home as the check-in; `/act`; Open buttons; alerts marked done |
| S3-3 | 12–15 | yes (after S3-2) | Review (Queue, Review lane), move to the front, Calendar; `REVIEW_BATCH` off after 7 days |
| S3-4 | 16–18 | yes (after S3-3) | Produce with batches and estimates, Jobs tab, Resume, Sources |
| S3-5 | 19–21 | yes (after S3-4 is deployed) | Results → Costs, Compare, account view |
| S3-5b | 22–23 | yes (after S3-5; each task after its 7-day wait) | `/clip`, `/status <id>`, `/resume` retired; CLI on `admin`; `web` public routes only |

Card 004 (the S3a Vercel deploy) is the prerequisite for using any checkpoint online. Before it, each checkpoint is checked locally against the deployed `admin`.

## Coverage

**04's S3 list:**

| 04's S3 item | Task(s) | Test(s) |
|---|---|---|
| `web/` app: Next.js, Auth.js, TanStack Query, hey-api client from the exported OpenAPI | S3a (built); the export switches to `admin` in 1 | `openapi contract`, `web gen:check` |
| API additions | 1 (surfaces), 4, 8, 9, 13, 17, 19, 20; **S2, reused**: autopilot, promote, ladder, review approve/reject/copy, policy dry-run, publisher check, links | `tests/api/admin/*` |
| Home (needs, meter, scoreboard, slots) | 6–9, 11 | `test_router.py`, `test_fleet.py`, `home.spec.ts` |
| `/act/<kind>/<id>` | 8, 11 | `test_needs_api.py`, `act.spec.ts` |
| Review inbox | 12–14 (Queue, Review lane, batch approve); approve, reject and copy are **S2, reused**; re-render arrives with the hooks build (#619) | `test_pin.py`, `test_posting_api.py`, `review.spec.ts` |
| Calendar | 9, 15 | `test_fleet.py`, `calendar.spec.ts` |
| Sources | 18 (pages over S1's `/sources` routes, reused) | `sources.spec.ts` |
| Produce (batch planner, Jobs tab) | 16–18 | `test_batches.py`, `test_produce_api.py`, `produce.spec.ts` |
| Results (Costs; Stats and Money in S7) | 19 | `test_results.py`, `results.spec.ts` |
| Settings | 3, 4 | `test_settings_service.py`, `settings.spec.ts` |
| Accounts → Compare (read view) | 20, 21 | `test_fleet.py`, `accounts.spec.ts` |
| Account Overview, Autopilot, Activity tabs | 20, 21 (Autopilot over **S2, reused** routes) | `test_accounts_admin_api.py`, `accounts.spec.ts` |
| The link-contract test | 11 (and each page task flips its rows) | `links.spec.ts`, `test_link_contract.py` |
| Ops alerts with Open buttons | 10 | `test_ops.py` |
| Review is a queue manager until S2 (D8) | 12–14 | as above |
| Vercel project; proxy auth plus bearer to `admin`, `ADMIN_API_TOKEN` (D9) | 1, 2, 5; owner steps S3-1 | `test_surfaces.py`, `test_app.py`, `upstream.test.ts` |
| Exit: phone check-in under 20 minutes; every alert opens `/act` | 10, 11, 22; owner step S3-5b.5 | `test_link_contract.py` |
| Personas, Decisions, Stats, Money (08 §2 pages not in S3) | not S3: Personas S8, Decisions S6, Stats and Money S7 | — |

**§10.2 (as revised by §11):**

| §10.2 item | Task(s) |
|---|---|
| `GET /admin/needs`, `GET /admin/needs/{kind}/{id}`, `POST …/{action}` (and snooze); `Provider.done` and the claim-first action (#623) | 6, 8, 10 |
| `GET /admin/fleet/scoreboard`, `GET /admin/slots` | 9 |
| `GET /admin/accounts/{id}/activity` | 20 |
| `POST /admin/batches/preview`, `POST /admin/batches` | 16, 17 |
| `GET /admin/results/costs` | 19 |
| `GET|PUT /admin/settings` | 4 |
| Data: `needs_log` (with snoozes), `settings`, `batches`, `queue_pin` | 3, 12 |
| Caps shown, not enforced | 16 (`test_caps_shown_not_enforced`), 19 |
| Link-contract test, ops alerts with Open buttons | 10, 11 |

**Routes S2 owns, reused and never re-implemented here:**
- `GET|PUT /admin/accounts/{id}/autopilot`, `POST …/autopilot/promote`, `GET …/ladder`
- `GET /admin/policy/dry-run`
- `GET /admin/review`, `POST /admin/review/{item}/approve|reject`, `PUT /admin/review/{item}/copy`
- `GET /admin/publisher/check/{account}`
- `POST|GET /admin/links`

S3 adds only routes that call S2's services: batch approve (loops `ReviewService.approve`), strikes (`record_strike`) and pause (`actions.pause`).
