# Studio S3c: account workspaces (design)

Date: 2026-09-30 · Status (stop card, 2026-09-30):
- §0 goal and scope, §1 data model: **approved** (given by the owner before this design).
- §2 pages: **approved** (with the Experiments nav item, added only when S3c is built).
- §3 producers, §4 results, §5 API/data/migration/rollback, §6 roadmap: **approved** in chat, one section at a time.
- The written spec as a whole, and ADR-42 (draft in 05): **written, awaiting owner review**.
- §7 open points, the coordinator's addendum D1–D10 (not received in this session), the per-page "home" lines for ADR-44 and the notification policy for ADR-45: **not started**.
- Implementation plan: **not started**, on purpose: it waits until S1 is finished, so it builds on S1's final schema.

Decision: ADR-42 (draft in [docs/studio/05](../../studio/05-proposed-adrs.md)), which replaces ADR-35's "blueprints are files" part.
Background: ADR-25, 26, 29, 35, 38, 41, 43–46; [01](../../studio/01-vision-and-strategy.md), [07](../../studio/07-channel-portfolio.md), [08 §2](../../studio/08-dashboard-and-operations.md#2-dashboard-information-architecture-nextjs), [09](../../studio/09-account-registry.md); the S1 spec and plan (2026-09-29); the S3a spec (2026-09-29).

## 0. Goal and scope

Each account type is very different, and the owner needs to think about and improve **each category and each account within it**. "Improve" means three linked things:
1. **Edit the setup:** category, blueprint and account settings, from the dashboard.
2. **Keep notes and run experiments:** ideas, learnings and questions; and experiments that change the setup on purpose.
3. **See results:** before vs during an experiment, per version, per account.

An **experiment** ties them together: a change, measured over a window, then kept or reverted.

**Decided before this design (not reopened):**
- **The database is the source of truth** for categories, blueprints and accounts, with versions (option A). The dashboard edits them directly. S1's `blueprints/*.toml` become the version-1 import, like `channels.toml` became sources. ADR-42 records this.
- **Data model:** section 1 below (approved).

**Out of scope here:** the implementation plan (after S1), S7's engagement metrics (only their slot in the metric registry is designed), and S2's enforcement of review tiers (S3c records what S2 enforces).

**Facts designed against (coordinator audit, 2026-09-30):**
- S1 Tasks 1–13 are built; 14–21 aren't. S1 Task 18 adds `/accounts` and `/sources` routes and CLI (reused here). The DB and `blueprints/` reach Modal only in S1 Task 21. `PostingOverview.accounts` is `[]` until S1 Task 17. Hashtags come from env until S1 Task 15.
- S1 freezes migration 0001 as explicit DDL (Task 13b, log #84). S3c's migration is 0002.
- `content_items` already carries `producer_version`, now **derived from the output logic** (ADR-43: stage versions, prompt names and model ids; the git SHA is only `build`; legacy Dict items keep `"plan-c"`) and a license from the source or job permission (#75). `setup_version` is a new, separate column: `producer_version` says which code made an item, `setup_version` which account setup.
- Accepted after this design was approved, to apply in the plan: **ADR-44** (one home per task: each page in 08 §2 gets its Telegram role; experiment decisions and setup edits are dashboard tasks; Telegram only deep-links to them), **ADR-45** (notification budget: e.g. "experiment needs a decision" is digest-level, not instant), **ADR-46** (daily reconcile).
- Contract rule (#49): `GET /posting` and `GET /jobs/{id}` change only additively; otherwise `web/openapi.json` is regenerated in the same checkpoint.
- Vercel previews are build-only (no login there, log #83). Checks run locally and in production.

## 1. Data model (approved)

- **Three versioned levels:**
  - **Category** (the 5 fixed codes: `clips`, `story`, `band`, `avatar`, `model`): a playbook text; **rules** = the compliance profile the policy gate reads; **production defaults** (lengths, caption preset, voice style, review tier, cadence, prompt versions).
  - **Blueprint:** pillars, series formats, voice and visual briefs, money, prompts (as in S1's `Blueprint` contract).
  - **Account:** overrides of any category or blueprint value, plus its own fields (handles, budget, pair, posting schedule, review tier).
- **Effective setup** = category defaults, overridden by the blueprint, overridden by the account. The dashboard shows where each value comes from.
- **Versions:** every save writes a full, validated snapshot, with an author (owner, session or experiment) and a note. **Restore** saves an old version as a new one; history is never rewritten. Every content item records the account version it was made from.
- **Experiments:** hypothesis; the change (from and to version); one metric; a window (N days or N items); status `draft`, `running`, `done` (plus `stopped`, §4.4); result (before vs during); decision **keep** or **revert** with a reason. One running experiment per account. Category- or blueprint-level experiments run on the accounts you choose.
- **Notes:** kind `idea`, `learning` or `question`; attached to a category, blueprint, account or experiment; status `open`, `done` or `dropped`. An idea becomes an experiment in one click, and a finished result can become a learning on the category playbook.
- **Seed data:** S1's blueprints and accounts imported as version 1; the 5 category playbooks drafted from 01, 07 and 09 for the owner to edit.

### 1.1 Accounts pin their parent versions (approved in §3)

Each **account version** stores the exact category version and blueprint version it builds on, plus its overrides and identity fields. So `(account_id, account_version)` fully determines the effective setup, and that pair is what a content item records.

- Saving a category or blueprint **doesn't flow silently** into accounts. The save dialog offers **"Apply to accounts"** (all ticked by default); each ticked account gets a new version with the note "adopts blueprint v5". Accounts with a running experiment are skipped and listed ("will adopt when their experiment ends").
- A category- or blueprint-level experiment moves only the chosen accounts to the new parent version. **Keep** offers to move the rest; **Revert** moves the chosen accounts back.
- Rejected alternative: live inheritance (a category edit reaches every account at once). An item's setup would then depend on three moving versions, and experiments couldn't isolate their accounts.

### 1.2 The resolver and the field registry

- `accounts/setup.py` (Modal-free): a pure `effective_setup(category_v, blueprint_v, account_v) -> EffectiveSetup`, returning every value with its origin (`category`, `blueprint`, `account`) and, for an override, the value it replaces.
- **Field registry:** one table of every setup field with its level(s), type, validation and **change class** (§3.5). The dashboard, the API and the experiment form all read it.
- `EffectiveSetup` is the contract producers read (clips now; story, band, avatar and model producers from their first version).

## 2. Pages, phone and laptop (approved)

Every page works on phone and laptop, on S3a's responsive shell (S3a spec §6b): bottom tabs and one column on a phone; sidebar, multi-column pages and tables from 1024 px.

### 2.1 Navigation

`web/components/nav.ts` gains **Experiments** after Accounts **when S3c is built** (not before): Home, Jobs, Review, Calendar, Accounts, Experiments, Sources, Produce, Costs. "Accounts" is the way into the workspaces. On the phone, Accounts and Experiments are the first items under More.

### 2.2 Accounts: the studio map (`/accounts`)

One section per category in fixed order (clips, story, band, avatar, model). A category header shows its playbook link, account count and running experiments, and opens the category workspace. Laptop: a table per category (account, status, blueprint and version, review tier, 7-day posted, ⚗ running experiment). Phone: cards. Categories without accounts stay visible, so their playbook can be written first.

### 2.3 Category workspace (`/accounts/c/<code>`)

- **Playbook:** editable text (versioned), plus a **Learnings** list (learning notes from finished experiments).
- **Rules:** the compliance profile (change class `rules`, §3.5).
- **Defaults:** production defaults.
- **Blueprints:** each with its accounts.
- **Experiments, Notes, History:** the shared components of §2.5.

### 2.4 Blueprint workspace (`/accounts/b/<name>`)

Setup (pillars, series formats, voice and visual briefs, money, prompts), Accounts using it (with the version each is pinned to), Experiments, Notes, History.

### 2.5 Account workspace (`/accounts/<id>`)

Header: handle, category chip, blueprint and version, status, review tier, and a banner for a running experiment (progress "day 4 of 7" or "18 of 30 items", link).

- **Overview:** headline results, the running experiment, open notes and ideas.
- **Setup:** every effective value with a badge for its origin. An override shows what it replaces and has **Reset** (drop the override, inherit again). **Edit** changes only this level's fields; saving requires a note, validates, and writes version N+1; validation errors show inline and nothing is saved. **Experiment…** starts the experiment flow with the same form.
- **History:** versions (author, note, date, experiment link). Pick two to **diff**: side by side on a laptop; "field: old → new" on a phone. **Restore this version** saves it again as a new version.
- **Results:** §4.
- **Experiments** and **Notes:** this account's.
- **Sources:** the account's sources (S1), each linking to the Sources page.

Laptop: tabs across the workspace, Setup as a 3-column table (field, value, origin with override info). Phone: sections as a scrollable chip row; setup as grouped rows ("max clip length · 45 s · [account ▸ overrides 60 s]").

### 2.6 Experiment flow

1. **Start** from an idea note ("Try this"), from Setup ("Experiment…" instead of Save), or from Experiments → New.
2. **Scope:** one account, or a category or blueprint plus a checklist of its accounts. Accounts with a running experiment are shown disabled with the reason.
3. **Define:** hypothesis; the change (the edit form, previewed as a diff against the current version); one metric (only those available now, §4.1); the window (N days or N items); the **cost preview** (§3.4) with the optional "also re-cut the backlog" tick-box.
4. **Run:** Start writes the new version(s) and makes them effective; status `running`. The account shows the banner with progress, before vs during so far, and the "too few items" warning while it applies.
5. **Decide:** when the window closes and outcomes have settled (§4.2), the experiment shows as **needs a decision** on Home and on Experiments. **Keep** (the version stays; for a category or blueprint experiment, offers to move the other accounts too) or **Revert** (restores the from-version as a new version), each with a required reason. Either way, "Add a learning to the playbook" is offered with the result pre-filled.

### 2.7 Experiments (`/experiments`)

Four lists across all accounts: **Needs a decision**, **Running**, **Drafts**, **Ideas** (open idea notes, each with "Try this"). Tables on a laptop, cards on a phone.

### 2.8 Notes and Home

- A floating **+ Note** button on category, blueprint and account pages (phone): kind and text in one step, for ideas that come up while scrolling the feeds.
- **Home:** a "Needs a decision" card, next to S3's permission-expiry banner.

## 3. How producers use the setup (approved)

### 3.1 When the setup is read (clips, step by step)

| Moment | Who | Reads | Effect |
|---|---|---|---|
| Job created (`POST /jobs`, `clipforge clip`, Produce) | `service.create_job` | the account's **current** version | Fills `ClipOptions` (min_len, max_len, min_score, n, language hint), the prompt versions and the caption preset, and stamps `JobInput.setup = {account_id, version}` (additive). The setup is **frozen for the job**: an edit mid-job doesn't change a running job. Steps still pass only ids and options, so stage modules stay free of DB and Modal code (ADR-9, ADR-12). |
| transcribe, highlights | stages | language hint; min_len, max_len, language, highlights prompt version (already in the highlights cache key); then min_score and n after the cache | §3.3 |
| captions | stage | caption preset, keywords prompt version | §3.3 |
| Enqueue (package; S1 Task 14) | posting | the **job's** stamped version | Enabled platforms per item (as S1 built). Copies `setup_version` onto each `content_items` row. |
| Send (tick) | posting | the account's **current** version | Hashtags (from S1 Task 15), CTA, bio link, slots, cadence, pause. These are posting-time settings, not baked into the item. The version used goes into `post_events.data.setup_version`, so posting experiments are attributed by send (§4.1). |

**Prompts stay files** (CLAUDE.md rule 4). The setup stores only which **released** version to use, chosen from `prompts/metadata.json`. Editing prompt text is still a repo change that creates the next version.

**Language** is part of a clips account's identity (EN and ES are separate accounts, 01). It's editable but not an experiment lever. When the detected transcript language differs from the account's, the job is **held** with that reason instead of producing off-language clips. The plan must check whether first wiring the hint changes the transcribe key for sources cached under "auto".

### 3.2 The setup version and cache keys

- The setup version is **never** part of a cache key. Otherwise a hashtag edit would re-render everything.
- Setup values only feed the key inputs that already exist (ADR-8). **Existing items are never touched;** a change applies to new jobs and to explicit re-cuts.
- The captions key gains the caption preset **only when it isn't `default`**, so today's cached captions stay valid (a pinned-value test guards it).

### 3.3 What a change costs

| Change | Re-runs | Extra cost for a new job | Cost to re-cut an already-clipped source |
|---|---|---|---|
| min_score, n | nothing (applied after the cache) | none | **free** |
| min/max length, highlights prompt version | highlights, then per clip: reframe (cached for the same range), captions, render | none | **~$0.07 per source hour** + ~$0.001 per clip |
| language hint | transcribe + highlights, then per clip | none | **~$0.12 per source hour** + per clip |
| caption preset, keywords prompt version | per clip: captions (Haiku, ~$0.0005) + render (CPU) | none | **~$0.0015 per clip** |
| platforms, hashtags, CTA, slots, cadence | nothing (posting time) | none | free |

Prices come from `config.Prices`; the plan re-checks the per-clip numbers against `metadata.json` costs.

### 3.4 Cost shown before an experiment starts

The experiment form classifies each changed field with §3.3 and shows one line, for example: "New jobs: no extra cost. Re-cutting the 3 sources already clipped for this account (4.2 source hours): ~$0.29 + ~$0.09 for 60 clips = **~$0.38**." The re-cut is an explicit tick-box ("also re-cut the backlog"); without it, the experiment uses only new jobs and costs nothing extra. The estimate uses `config.Prices` and the source hours in S1's `jobs` table.

### 3.5 Change classes: what's live-editable and what needs review

Every field in the registry has one class; the dashboard and API enforce it.

| Class | Fields | Takes effect | Experiments |
|---|---|---|---|
| **live** | hashtags, CTA, bio link, slots, cadence, pause, platforms, min_score, n | the next enqueue or send | yes |
| **recut** | min/max length, caption preset | new jobs; the cost is shown (§3.3) | yes |
| **format** | prompt versions, series formats, pillars, voice and visual briefs | new jobs; per ADR-29 "a new format starts in `review`": the first **10 items** made under a version that changed a format field go to `review`, even on `sample` or `auto` accounts. S3c records it on the version; **S2 enforces** it. Until S2, the phone reviews everything anyway | yes |
| **rules** | the category compliance profile, review tier | saved only by the owner, with a note; **loosening** a rule needs an explicit confirmation | **no** (policy isn't A/B-tested) |
| **identity** | handles, language, pair, budget | saved directly; budget is live | no |

### 3.6 Timing against S1, and other producers

The setup reaches production only after S1 is finished: Task 14 (per-account enqueue), Task 15 (hashtags from the account), Task 17 (`PostingOverview.accounts`), Task 21 (DB and `blueprints/` in Modal). Before that, S3c can show and edit versions, and producers keep today's constants (`SETUP_SOURCE=off`, §5.6).

The story, band, avatar and model producers (S6 and later) take `EffectiveSetup` as an input from their first version (voice style, series rotation, briefs) and use the same field registry.

## 4. Results (approved)

### 4.1 Metrics

A metric registry: name, unit, direction (higher is better or not), availability (now or S7), and attribution (per item via `content_items.setup_version`, or per send via `post_events.data.setup_version`).

**Available now (S1 tables):**

| Metric | Unit | Attributed by |
|---|---|---|
| Items produced per source hour | clips/h | item |
| Mean highlight score | 0–1 | item |
| Posted rate: posted on ≥ 1 platform ÷ decided | % | item |
| Reject rate, plus the reason mix (boring, bad_cut, bad_crop, captions, other) | % | item |
| Skip rate (⏭) | % | send |
| Platform completion: all enabled platforms ✅ | % | send |
| Cost per item and per posted item | $ | item |
| Held items (source or permission holds) | count | item |
| Time from send to decision | hours (median) | send |

**After S7:** views at 24 h and 7 d, retention or average watch %, followers gained, link clicks (S2 tracking links), revenue and RPM; per item, through `posts`, each with a **maturity age**.

The experiment form offers only metrics available now; S7 metrics show greyed out ("after S7"). Posting-time experiments default to per-send metrics; production experiments to per-item metrics.

### 4.2 Before vs during

- **During:** items (or sends) stamped with the experiment's to-version, from the start until the window closes (N days or N items).
- **Before:** the same account's most recent items under the from-version, over a window of the same size (same number of days, or the same N items). If fewer exist, it uses what's there and says so.
- **Only settled outcomes count.** Items still queued, or sent but undecided, at the window's end show as "pending". The experiment becomes **needs a decision** once ≥ 80% are decided, or 3 days after the window closes, whichever is first. S7 metrics wait for their maturity age ("done: waiting for data").
- **Category or blueprint experiments:** results per account and pooled; the scope's non-chosen accounts appear as a same-period **comparison group** when there are any.
- **Display:** two cards (before, during) with value, counts ("3 of 20 rejected") and difference. The account's Results tab: a table per version (dates, items, posted, reject rate and top reason, cost per item; S7 columns later) and one chart of the chosen metric over time with a marker at each version change.

### 4.3 Judging, and the "too few items" warning

- **Too few to judge** when either side has fewer than **10 decided items (or sends)**. Keep and Revert still work; the experiment records `thin_data`.
- **Rates:** a 90% Wilson interval on each side; the verdict reads **likely better**, **no clear difference** (intervals overlap) or **likely worse**.
- **Continuous metrics** (score, cost, views): medians with the p25–p75 range; overlapping ranges mean no clear difference.
- No p-values: plain labels and the counts.

### 4.4 Keeping results clean while an experiment runs

- While an account has a running experiment, its saves are limited to **identity** fields. Any other change asks to **stop** the experiment first (status `stopped`: partial numbers kept, no decision).
- Category and blueprint "Apply to accounts" skips accounts with a running experiment (§1.1).
- A pause, a source hold or a posting outage during a **day-based** window extends it by the days nothing was sent; the banner says so.

## 5. API, errors, data, migration, tests, rollback, cost (approved)

### 5.1 Routes

All on S3's **`admin`** endpoint (ADR-38) with the bearer token; the author comes from S1's `X-Clipforge-Actor` header. S1's `/accounts` and `/sources` routes and CLI (S1 Task 18) are reused; after S3c, **`PATCH /accounts/{id}` writes a new version** instead of updating in place.

| Area | Routes |
|---|---|
| Categories | `GET /categories`, `GET /categories/{code}`, `PUT /categories/{code}` (save → new version), `GET …/versions`, `GET …/versions/{n}`, `POST …/versions/{n}/restore` |
| Blueprints | the same under `/blueprints/{name}`, plus `POST /blueprints` (copy an existing one), `POST /blueprints/{name}/apply {version, accounts[]}` |
| Accounts | `GET /accounts/{id}/setup` (effective setup, origins, version), `PUT /accounts/{id}/setup`, `GET …/versions`, `GET …/diff?from=&to=`, `POST …/versions/{n}/restore`, `GET …/results?metric=` |
| Experiments | `POST /experiments` (draft), `GET /experiments?status=`, `GET /experiments/{id}` (with the live result), `GET …/{id}/estimate` (§3.4), `POST …/{id}/start`, `…/stop`, `…/decide {keep\|revert, reason, promote?, learning?}` |
| Notes | `POST /notes`, `GET /notes?target=&status=`, `PATCH /notes/{id}`, `POST /notes/{id}/experiment` |
| Pickers | `GET /metrics` (§4.1), `GET /prompts` (released versions from `prompts/metadata.json`) |

- **No new cron:** "window closed" and "needs a decision" are **derived on read** from the stored `running` status and the data (the ADR-27 cron limit). Only `decide` and `stop` write a final status.
- **Contract (#49):** `POST /jobs` gains an optional `setup` in `JobInput`. `GET /jobs/{id}` and `GET /posting` don't change (`PostingOverview.accounts` already carries per-account data). `web/openapi.json` is regenerated in the same checkpoint.

### 5.2 Error paths

- **422 `{errors: [{path, msg}]}`:** every save is a full snapshot validated by pydantic; nothing is saved on failure. Exception to S3a's "never pass upstream bodies through": structured field errors from our own `admin` endpoint are shown inline.
- **409, version conflict:** saves carry `expected_version`; a save in between (another tab, a session, an experiment) returns "changed since you opened it" plus the latest version; the dashboard shows the diff to re-apply.
- **409, experiment conflicts:** starting an experiment on an account that already runs one; editing non-identity fields during a run (§4.4). Both return the experiment's id.
- **404** unknown ids; **503** database unreachable (S1's convention; the dashboard shows "API unavailable").
- Loosening a rule without `confirm_loosen=true` → 422.

### 5.3 Data: migration 0002 (after S1's frozen 0001)

- `categories(code PK, current_version)`, seeded with the 5 codes.
- `category_versions(code, n, data jsonb, author, note, created_at)`; data = playbook text, rules, defaults.
- `blueprints(name PK, category → categories, current_version)`; `blueprint_versions(name, n, data jsonb, author, note, created_at)`.
- `account_versions(account_id, n, category_version, blueprint_version, overrides jsonb, identity jsonb, format_changed bool, author, note, experiment_id, created_at)`, with composite FKs to the pinned parent versions (§1.1). `format_changed` feeds S2's first-10-in-review rule (§3.5).
- `accounts.current_version`. The existing `accounts` columns become a **projection** of the current version, written only by the versions service, so S1 code reading `accounts` keeps working (one writer per column group, ADR-41).
- `experiments(id, scope_type, scope_id, hypothesis, change jsonb, metric, window_kind, window_size, recut_backlog, status, started_at, ended_at, decision, reason, decided_at, thin_data)`; `experiment_accounts(experiment_id, account_id, from_version, to_version)` with a partial unique index allowing **one running experiment per account**.
- `notes(id, target_type, target_id, kind, status, text, experiment_id, author, created_at, updated_at)`. A learning is a `learning` note on the category, listed under the playbook; the playbook text itself is versioned in `category_versions`.
- `content_items.setup_version int NULL`, FK `(account_id, setup_version)` → `account_versions`. NULL for items made before versioning ("before versioning").
- `post_events.data.setup_version`: a JSON key only.
- The `*_versions` tables are **append-only**, enforced by a trigger that rejects UPDATE and DELETE.

### 5.4 Migration: `clipforge setup import [--dry-run]` and `setup verify`

Modelled on S1's `source import-toml`.
1. **Categories v1:** rules from the 07/09 "must have" table; defaults = today's constants (30–60 s, min_score 0.80, caption preset `default`, `review` tier, `highlights_v1`, `keywords_v2`); the playbook drafted from 01, 07 and 09 for the owner to edit.
2. **Blueprints v1** from `blueprints/*.toml` (the note records the file name and hash). A blueprint's `compliance` becomes a rules override only where it differs from its category.
3. **Accounts v1**, pinned to category v1 and blueprint v1. A value S1 copied into the account (`niche`, `platforms`) is kept as an override **only where it differs** from the blueprint; identical copies are dropped so they inherit. `kind` is **never** an override: it always comes from the blueprint's category. Identity fields (handles, pair, budget, posting, review tier) go into `identity`.
4. Re-running is safe: it skips anything already imported.
5. `setup verify` checks that each account's effective setup equals its S1 row, field by field, and must report **0 differences** before the switch.

After the import, `blueprints/*.toml` is no longer read: `account create --blueprint` reads the DB, and `load_blueprint` survives only in the importer. The files stay in the repo, untouched, until the move has been verified for 7 days.

### 5.5 Tests

Local Postgres, as in S1. Previews are build-only, so the checks run locally and in production.
- **Pure:** the resolver and origins (an override wins; reset inherits); field-registry classes; the cost estimate; before/during windows, including a window extended by a pause; the Wilson verdict and the 10-item floor.
- **DB:** `*_versions` append-only (trigger); restore writes a new version; 409 on `expected_version`; one running experiment per account; non-identity edits blocked during a run; import re-runnable and `verify` at 0 differences; the `accounts` projection equals the current version.
- **Pipeline:** `create_job` stamps the setup and fills `ClipOptions`; the **setup version is in no cache key** (a hashtag change gives identical keys); a pinned captions key for the `default` preset.
- **API:** every route answers 401 without the token, 422 with field errors, and 409 and 503 where they apply.
- **Web:** Playwright in the phone and desktop projects for the account workspace, the edit → diff → restore loop, and the experiment flow, against a mocked admin API.

### 5.6 Rollback

- Everything is additive: new tables, one nullable column, one optional `JobInput` field.
- **`SETUP_SOURCE=db|off`** (default `off` until `verify` passes). With `off`, producers ignore the setup and use today's constants, and the dashboard shows the workspaces read-only. Rolling back is a config change plus a redeploy (or `modal app rollback`).
- Last resort: `alembic downgrade` to 0001 drops the new tables and column. Take a `setup export` JSON snapshot first, because that loses history.

### 5.7 Cost

Design $0. Build: tests run locally; no Modal or LLM spend beyond one smoke run (~$0.01). Runtime: a few small queries per job and per send, and results queries on Neon's free tier. Real money is spent only when the owner ticks "also re-cut the backlog" (priced in §3.3–3.4).

## 6. Roadmap (approved)

**S3c "Account workspaces"**, its own item in three phases. S3 drops its "Accounts (profile editor)" page; S3c's studio map and workspaces replace it.

| Phase | Builds | Depends on | Switch |
|---|---|---|---|
| **S3c-1: versions and workspaces** | migration 0002, the resolver and field registry, `setup import` and `verify`, the category, blueprint and account workspaces (setup with origins, history, diff, restore), notes, the Accounts page | S1 finished (all tasks; 0001 frozen); S3's `admin` endpoint (S3 action 4) | `SETUP_SOURCE=off`: edit and review only |
| **S3c-2: wiring into the clip producer** | `create_job` reads and stamps the setup; `content_items.setup_version`; the send records its version; caption preset in the captions key (only when not `default`); prompts from released versions; the language-mismatch hold | S3c-1; S1 Tasks 14, 15, 17 and 21 live | `SETUP_SOURCE=db` after `verify` reports 0 differences |
| **S3c-3: experiments and results** | the experiment flow and cost preview, one running per account, the edit block during a run, results with the metrics available now, the Wilson verdict and 10-item floor, the Experiments nav item, Home's "Needs a decision" card, learnings in the playbook | S3c-2 | — |
| **In S7** | views, retention, followers, clicks and revenue in the metric registry, with maturity ages | S7 | — |

- **S2** enforces §3.5's "a format change sends the first 10 items to `review`" (reads `account_versions.format_changed`).
- **S6 and later producers** read `EffectiveSetup` from their first version, so S3c-2's contract should come **before S6** (a soft dependency).
- Graph: `S1 → S3c`, `S3 → S3c` (admin endpoint), `S3c -.-> S6` (soft), `S7 → S3c` (engagement metrics).
- **Done when:** the owner changes realtalk's max clip length through an experiment, sees before and during for reject rate and posted rate, chooses Keep, and the learning shows in the clips playbook; all through the dashboard, on phone and laptop.
- **Cost:** ~$1 (tests and one smoke run); a backlog re-cut, if ticked, is extra.

## 7. Open for the implementation plan (after S1)

- Whether first wiring the language hint changes the transcribe key for sources cached under "auto" (§3.1).
- The exact field list and validation per level, taken from S1's final `Account` and `Blueprint` contracts.
- The drafted category playbooks (the plan writes them from 01, 07 and 09; the owner edits them in the dashboard).
- Whether `PATCH /accounts/{id}` keeps S1's request shape (recommended: same shape, now writing a version).
