# Studio S3c: account workspaces (design)

Date: 2026-09-30 · Status (revised by card 003, 2026-09-30; **accepted by the owner on 2026-09-30**, with ADR-42, decision log #131). **Revised 2026-10-02 (card 018)** for ADR-48, ADR-50 and the migration landing order; the list of changes is right below. The rest of this status block is card 003's record:
- §0 goal and scope, §1 data model: **approved** (given by the owner before this design). §1.1 now states D1.
- §2 pages: **approved** (with the Experiments nav item, added only when S3c is built). Revised for D7 (§2.6, §2.7, §2.8) and D10 (§2.3, §2.4 paths, new §2.9).
- §3 producers, §4 results, §5 API/data/migration/rollback, §6 roadmap: **approved** in chat, one section at a time. Revised for D3 (§5.3, §5.5, §5.6) and D4 (§3.4 rewritten, §5.1); §6's phases list the new pieces.
- §7 open points: **written** (six items for the plan).
- The coordinator's addendum:
  - **D1** one setup id: done, §1.1 (`(account_id, account_version)`, #88).
  - **D2** `PATCH /accounts` saves a version with an actor: done, §5.1.
  - **D3** `post_events.actor`: done by card 002 (`data.actor`) and S2a's migration (the column and its backfill); see §5.3.
  - **D4** one dry run: done, §3.4 and §5.1 (`POST /setup/preview`, used by save, restore, apply and experiment start).
  - **D5** edits apply to new items only: done, §3.2.
  - **D6** Telegram's role per page: done in 08 §2; S3c's pages in §2.9.
  - **D7** keep or revert only on the experiment page: done, §2.6, §2.7.
  - **D8** the pre-S2 Review page as a queue manager, and **D9** `admin` as a second ASGI app: S3's, added to 06's S3 card.
  - **D10** deep links: done, §2.9 (08 §2b formats, plus `/categories/<code>` and `/blueprints/<name>`).
- ADR-44 (home per task) and ADR-45 (notifications) for S3c: §2.9. ADR-43 and ADR-46 are referenced, not redefined (§0).
- ADR-42: revised with D1, D3, D4 and D7; **accepted 2026-09-30** (#131). Its text is in [docs/DECISIONS.md](../../DECISIONS.md#adr-42-versioned-categories-blueprints-and-accounts-in-the-database).
- Implementation plan: [docs/superpowers/plans/2026-10-02-studio-s3c.md](../plans/2026-10-02-studio-s3c.md) (card 018, checkpoint B): four parts, 21 tasks.

**Card 018's revision (2026-10-02).** Every change is made in place. The S3 dashboard spec §10.3 list is applied item by item:
- **ADR-48 (autopilot):**
  - The review tier and the budget leave the versioned setup. They live in S2's `autopilot` table (`review_dial`, `monthly_cap_usd`), whose one writer is `accounts/autopilot.py` (§1, §1.3, §3.5).
  - `format_changed` stays in the setup. §3.5 now says exactly what S2's routing reads from it (S3c's `SetupRepo.format_window`, injected into S2).
  - The actor check allows `system:<component>` (§5.3).
  - The experiment page shows autopilot changes as markers (§2.7, §4.2).
- **ADR-50 (hooks):**
  - The hook library, its versions and its weights stay outside the setup (§1.3).
  - The hook stamp sits next to `setup_version` on items, never inside it (§1.1).
  - Rotation weights freeze while an experiment runs: card 020 owns the freeze, and S3c pushes it through its `HookFreezer` protocol (start calls `freeze`, stop and decide call `release`, §4.4).
  - Hook metrics are on the Hooks tab, not in the metric registry (§4.1).
- **Pages:**
  - Accounts has two views: S3 builds Compare first, and S3c adds the Map and enriches Compare (§2.2).
  - The account workspace is S3's shared core plus type tabs, with Overview, Autopilot, Style, Hooks and Activity (§2.5).
- **Migration:**
  - It is "the next in landing order (S2a's 0002 first, then whichever of the hooks, S3 and S3c migrations lands next, one at a time), numbered at landing". It moves `EXPECTED_HEAD` in the same change (§5.3, §6).
  - `post_events.actor` and its backfill are dropped, because S2a's 0002 carries them. The `*_versions` append-only triggers stay.
- **"pause" leaves the `live` class.** It is runtime state in `posting_state` (ADR-41), written only by `/pause` and `/go`. "cadence" is spelled as what it is today, the slots (§3.5).
- **§1.4 adds the field registry v1**, taken from S1's final `Account` and `Blueprint` contracts (it was a §7 open item).
- **§7's open items** are answered where S1's merged code settles them; the rest were the owner's questions at checkpoint A (§7).
- **§8 is new.** It lists the changes for 04, 06 and 08. Those in S3c's files (04's S3c section, 06's S3c card, 08 §2 and §2b) are applied directly; 04's graph and HK section are left to the coordinator.
- **The coordinator's review of checkpoint A** added:
  - every setup write that changes `posting` rewrites the schedule copy through the one writer (S2a's `write_schedule_copy`, which keeps `publish_via` and `profile`) after its commit, with S1's `_checked` validation (§5.3);
  - the hooks freeze is pushed by experiment start, stop and decide (§4.4);
  - `SETUP_SOURCE=off` means edit and review only, with live posting fields still reaching production (§5.6);
  - registry fixes (§1.4);
  - the landing order is S2a's 0002 first, then whichever of the hooks, S3 and S3c migrations lands next (§5.3);
  - at checkpoint B: start conditions as "deployed"; the schedule copy through S2a's `write_schedule_copy`; S2's publisher edit kept; `/admin/` routes and S3's `cli_router`; one `HookFreezer` protocol; sends attributed by claim time; the needs row through `needs_providers` (log #263);
  - the format window and the digest line are injected into S2 (option (a), log #261): `SetupRepo.format_window` and `experiments.digest_line`, wired in `runtime.build_deps`; no S2 module changes (§2.9, §3.5).

Decision: [ADR-42](../../DECISIONS.md#adr-42-versioned-categories-blueprints-and-accounts-in-the-database) in `docs/DECISIONS.md` (accepted 2026-09-30), which replaces ADR-35's "blueprints are files" part. It is refined by ADR-48 (the review tier and the budget leave the setup) and ADR-50 (the hook library lives outside it).
Background: ADR-25, 26, 29, 35, 38, 41, 43–50; [01](../../studio/01-vision-and-strategy.md), [07](../../studio/07-channel-portfolio.md), [08 §2](../../studio/08-dashboard-and-operations.md#2-dashboard-information-architecture-nextjs) and §2c, [09](../../studio/09-account-registry.md); the S1 spec and plan (2026-09-29); the S3a spec (2026-09-29); the [S3 dashboard spec](2026-10-01-studio-s3-dashboard-design.md) (2026-10-01) and the [S2 spec](2026-10-01-studio-s2-design.md) and [plan](../plans/2026-10-02-studio-s2.md) (2026-10-02).

## 0. Goal and scope

Each account type is very different, and the owner needs to think about and improve **each category and each account within it**. "Improve" means three linked things:
1. **Edit the setup:** category, blueprint and account settings, from the dashboard.
2. **Keep notes and run experiments:** ideas, learnings and questions; and experiments that change the setup on purpose.
3. **See results:** before vs during an experiment, per version, per account.

An **experiment** ties them together: a change, measured over a window, then kept or reverted.

**Decided before this design (not reopened):**
- **The database is the source of truth** for categories, blueprints and accounts, with versions (option A). The dashboard edits them directly. S1's `blueprints/*.toml` become the version-1 import, like `channels.toml` became sources. ADR-42 records this.
- **Data model:** section 1 below (approved).

**Out of scope here:**
- S7's engagement metrics: only their slot in the metric registry is designed.
- S2's enforcement of the review windows: S3c records `format_changed`, and S2 enforces it (§3.5).
- The autopilot settings (ADR-48, S2) and the hook library (ADR-50, card 020). S3c shows them on the workspace, but never versions or writes them (§1.3).

**Facts designed against** (the coordinator's audit of 2026-09-30, updated by card 018 on 2026-10-02):
- **S1:**
  - S1's code is merged and deployed Dict-only: Tasks 1–21 (card 002) and `posting_daily` (ADR-46).
  - The rollout (Task 22, card 010) wires Neon and moves reads to Postgres. Task 23 retires the Dict writes later.
  - The `/accounts` and `/sources` routes and CLI (Task 18) are reused here.
  - The DB and `blueprints/` reach Modal with the rollout. Hashtags come from the account (Task 15).
- **Migrations:**
  - 0001 is frozen as explicit DDL (log #84).
  - New migrations land one card at a time, in landing order (S3 dashboard spec §8.7, log #438, #141): S2a's 0002 first (card 014), then whichever of the hooks card's, S3's (card 019: `needs_log`, `settings`, batches) and S3c's lands next, one at a time. Each is numbered at landing and moves `EXPECTED_HEAD`, so S3c's number is assigned at landing.
- **S2a's 0002** carries:
  - the deferred `jobs.error`;
  - `post_events.actor`, backfilled from `data.actor`, with a check that allows `system:`;
  - `posting_state.changed_by` and `reason`;
  - `accounts.publisher`;
  - the `autopilot` and `autopilot_events` tables.
- **`content_items`:**
  - It already carries `producer_version`, now **derived from the output logic** (ADR-43: stage versions, prompt names and model ids; the git SHA is only `build`; legacy Dict items keep `"plan-c"`), and a license from the source or job permission (#75).
  - `setup_version` is a new, separate column: `producer_version` says which code made an item, `setup_version` which account setup.
  - The hooks card adds `hook_pattern_id`, `hook_version` and `hook_weights` beside them (S3 dashboard spec §8.5).
- **Accepted ADRs that apply to S3c:**
  - **ADR-44** (one home per task): each page in 08 §2 gets its Telegram role; experiment decisions and setup edits are dashboard tasks, and Telegram only deep-links to them.
  - **ADR-45** (notification budget): for example, "experiment needs a decision" is digest-level, not instant.
  - **ADR-46** (daily reconcile).
  - **ADR-48** (autopilot), **ADR-49** (the producer-version window) and **ADR-50** (hooks).
- **Contract rule (#49):** `GET /posting` and `GET /jobs/{id}` change only additively; otherwise `web/openapi.json` is regenerated in the same checkpoint.
- **Vercel previews are build-only** (no login there, log #83). Checks run locally and in production.

## 1. Data model (approved)

- **Three versioned levels:**
  - **Category** (the 5 fixed codes: `clips`, `story`, `band`, `avatar`, `model`):
    - a playbook text;
    - **rules**, the compliance profile the policy gate reads;
    - **production defaults**: lengths, minimum score, caption preset, reframe mode, prompt versions.
  - **Blueprint:** pillars, series formats, voice and visual briefs, money, prompts, platform defaults (as in S1's `Blueprint` contract).
  - **Account:**
    - overrides of any category or blueprint value;
    - its own fields: handles, language, pair, persona, and the posting chat, time zone, slots and hashtags.
- **Effective setup** = category defaults, overridden by the blueprint, overridden by the account. The dashboard shows where each value comes from.
- **Not in the setup (ADR-48, ADR-50):** the review tier, the budget and caps, the autopilot switches, the hook library, the pause and the publisher profile. §1.3 lists who owns each.
- **Versions:**
  - Every save writes a full, validated snapshot, with an author and a note.
  - The author is an actor string (§5.3): `web:<login>`, `telegram:<id>`, `session:<name>`, S1's `cli:<os user>`, or `system:<component>` for writes nobody tapped. A version written by an experiment also records its `experiment_id`.
  - **Restore** saves an old version as a new one; history is never rewritten.
  - Every content item records the account version it was made from.
- **Experiments:**
  - hypothesis, the change (from and to version), one metric, and a window (N days or N items);
  - status `draft`, `running`, `done` (plus `stopped`, §4.4); the result (before vs during); a decision, **keep** or **revert**, with a reason;
  - one running experiment per account;
  - category- or blueprint-level experiments run on the accounts you choose.
- **Notes:**
  - kind `idea`, `learning` or `question`, attached to a category, blueprint, account or experiment; status `open`, `done` or `dropped`;
  - an idea becomes an experiment in one click, and a finished result can become a learning on the category playbook;
  - a **+ Hook idea** from the phone is a note too. The hooks card also turns it into a draft pattern in its own tables (S3 dashboard spec §1, §3.6).
- **Seed data:** S1's blueprints and accounts imported as version 1, and the 5 category playbooks drafted from 01, 07 and 09 for the owner to edit (§5.4).

### 1.1 Accounts pin their parent versions (approved in §3)

Each **account version** stores the exact category version and blueprint version it builds on, plus its overrides and identity fields. So `(account_id, account_version)` fully determines the effective setup, and that pair is what a content item records.

**The setup's identity (D1, log #88).** There is no separate setup id:
- A setup is identified by `(account_id, account_version)`. The pinned parent versions inside that account version make the pair complete.
- Everything that refers to a setup uses that pair: `JobInput.setup`, `content_items.setup_version` (with the item's `account_id`), the version in force at a send's claim time (`SetupRepo.version_at`), `experiment_accounts.from_version`/`to_version` and the `/setup/preview` request (§3.4).

**The hook stamp sits next to the setup, never inside it (ADR-50).**
- An item's full recipe is `(account_id, setup_version)` plus the hooks card's `hook_pattern_id`, `hook_version` and `hook_weights`, each in its own `content_items` column.
- Editing a hook pattern never writes an account version, and an account version never names a hook.

**How parent saves reach accounts:**
- Saving a category or blueprint **doesn't flow silently** into accounts. The save dialog offers **"Apply to accounts"** (all ticked by default).
  - Each ticked account gets a new version with the note "adopts blueprint v5".
  - Accounts with a running experiment are skipped and listed ("will adopt when their experiment ends").
- A category- or blueprint-level experiment moves only the chosen accounts to the new parent version. **Keep** offers to move the rest; **Revert** moves the chosen accounts back.
- Rejected alternative: live inheritance (a category edit reaches every account at once). An item's setup would then depend on three moving versions, and experiments couldn't isolate their accounts.

### 1.2 The resolver and the field registry

- `accounts/setup.py` (Modal-free): a pure `effective_setup(category_v, blueprint_v, account_v) -> EffectiveSetup`. It returns every value with its origin (`category`, `blueprint`, `account`) and, for an override, the value it replaces.
- **Field registry:** one table of every setup field, with its level(s), type, validation and **change class** (§3.5). The dashboard, the API and the experiment form all read it. Version 1 is §1.4.
- `EffectiveSetup` is the contract producers read: clips now, and the story, band, avatar and model producers from their first version.

### 1.3 What the setup doesn't hold, and who does (ADR-41, ADR-48, ADR-50)

| Value | Lives in | One writer | On the workspace |
|---|---|---|---|
| Review dial (ADR-29's tier), presets, Produce/Publish/Scale switches, runway target, batch line, monthly cap | `autopilot`, `autopilot_events` (S2a's migration) | `accounts/autopilot.py` | the **Autopilot** tab (S3), read-only from S3c's code |
| Pause | `posting_state` and the `brake:<scope>` Dict keys | `posting/actions.pause` | the header's "Pause this account" (S3) |
| Upload-Post profile and Facebook page id | `accounts.publisher` (S2a's migration) | the accounts service's edit (`clipforge account edit --publisher-profile`) | Autopilot's "waiting on" line |
| Hook patterns, versions, rotation weights, ratings | the hooks card's tables | the hooks service (card 020) | the **Hooks** tab (card 020) |

- S1's columns `accounts.review_tier` and `accounts.monthly_budget_usd` stay in the table. S2 reads `monthly_budget_usd` once, to seed `autopilot.monthly_cap_usd`, and nothing reads `review_tier` after S2.
- S3c's projection (§5.3) never writes either column.
- S1's `AccountEdit.review_tier` is answered as §5.1 says.

### 1.4 Field registry v1 (from S1's final contracts)

Paths are the effective setup's namespace. "Stored as" names the S1 field the importer reads (§5.4) and the projection writes back (§5.3). A level marked ✓ may hold the field. An account override of a blueprint `platform_defaults` value is stored under the account's `platforms`.

| Path | Category | Blueprint | Account | Type and validation | Class | Stored as (S1) |
|---|---|---|---|---|---|---|
| `playbook` | ✓ | | | text, ≤ 20,000 chars | identity (never experimented on) | (new) |
| `rules.require_credit` | ✓ | ✓ | | bool | rules | `Blueprint.compliance` |
| `rules.required_tags` | ✓ | ✓ | | list of tags without `#` | rules | `Blueprint.compliance` |
| `rules.disclosures` | ✓ | ✓ | | subset of `ai`, `sponsored` | rules | `Blueprint.compliance` |
| `rules.banned_claims` | ✓ | ✓ | | list of codes | rules | `Blueprint.compliance` |
| `production.min_len`, `production.max_len` | ✓ | | ✓ | seconds, `ClipOptions` bounds (min ≥ 5, max ≤ 180, min < max) | recut | `ClipOptions` defaults |
| `production.min_score` | ✓ | | ✓ | 0–1 | live (the next job, enqueue or send) | `ClipOptions.min_score` |
| `production.n` | ✓ | | ✓ | 1–30 or empty (automatic) | live (the next job, enqueue or send) | `ClipOptions.n` |
| `production.reframe` | ✓ | | ✓ | `auto`, `center`, `blur` | recut | `ClipOptions.reframe` |
| `production.caption_preset` | ✓ | | ✓ | a preset name the captions stage knows (`default` today); it fills `ClipOptions.caption_style`, a `Literal`, so a new preset is a contract change (`models.py` first) | recut | `Account.brand.caption_preset` → `ClipOptions.caption_style` |
| `prompts.highlights`, `prompts.keywords` | ✓ | ✓ | | a released version in `prompts/metadata.json`; any other `prompts` key is refused (422) until a producer needs it | format | `Blueprint.prompts` |
| `niche` | | ✓ | ✓ | text | format | `Blueprint.niche`, `Account.niche` |
| `languages` | | ✓ | | subset of `en`, `es`; the create-time check for an account's `language` | identity | `Blueprint.languages` |
| `pillars` | | ✓ | | 1–12 short texts | format | `Blueprint.pillars` |
| `series` | | ✓ | | list of `{name, description}` | format | `Blueprint.series` |
| `voice_brief`, `visual_style` | | ✓ | | text | format | `Blueprint` |
| `money` | | ✓ | | list of texts | live | `Blueprint.money` |
| `platforms.<p>.enabled` | | ✓ | ✓ | bool | live | `platform_defaults`, `Account.platforms` |
| `platforms.<p>.min_len`, `.max_len` | | ✓ | ✓ | seconds or empty | recut | `PlatformProfile` |
| `platforms.<p>.hashtags` | | ✓ | ✓ | list without `#` | live | `PlatformProfile.hashtags` |
| `platforms.<p>.handle` | | | ✓ | `HANDLE` | identity | `PlatformProfile.handle` |
| `language` | | | ✓ | one of the blueprint's `languages` | identity | `Account.language` |
| `paired_account_id`, `persona_id` | | | ✓ | an existing account or persona id, or empty | identity | `Account` |
| `posting.chat_id`, `posting.timezone` | | | ✓ | an allowed chat id; an IANA zone | identity | `Account.posting` |
| `posting.slots` | | | ✓ | 1–12 `HH:MM` (normalized as today) | live | `Account.posting.slots` |
| `posting.hashtags` | | | ✓ | list without `#` | live | `Account.posting.hashtags` |
| `brand.cta`, `brand.bio_link` | | | ✓ | text; an https URL | live | `Account.brand` |

Never fields:
- `kind` always comes from the blueprint's category.
- `blueprint` (the name) is set at create; moving an account to another blueprint isn't offered (create a new account).
- `ClipOptions.language` (Whisper's hint) is always empty: the account's `language` is never passed to Whisper (#254, §3.1).

## 2. Pages, phone and laptop (approved)

Every page works on phone and laptop, on S3a's responsive shell (S3a spec §6b): bottom tabs and one column on a phone; sidebar, multi-column pages and tables from 1024 px.

### 2.1 Navigation

`web/components/nav.ts` gains **Experiments** **when S3c is built** (not before), in 08 §2c's order: Home · Review · Calendar · Accounts · Produce · Experiments · Results · Sources · More.
- "Accounts" is the way into the workspaces. It stays highlighted on `/categories/…` and `/blueprints/…` too.
- On the phone (tabs Home · Review · Accounts · Results · More), Experiments is the first item under More.

### 2.2 Accounts: Compare and the studio map (`/accounts`)

The Accounts page has two views of the same list (S3 dashboard spec §7.4):

- **Compare** (`/accounts?view=compare`): the weekly side-by-side view. S3 builds it first as a read view (G3).
  - S3c-1b adds two columns: blueprint and account versions, and the running experiment.
  - It also adds two reasons to the focus ranking: "experiment needs a decision" and "format window open".
- **Map** (`/accounts`, the default once S3c-1b ships): one section per category in fixed order (clips, story, band, avatar, model).
  - A category header shows its playbook link, account count and running experiments, and opens the category workspace.
  - Laptop: a table per category (account, status, blueprint and version, rung, 7-day posted, ⚗ running experiment). The rung is read from `autopilot`.
  - Phone: cards.
  - Categories without accounts stay visible, so their playbook can be written first.

### 2.3 Category workspace (`/categories/<code>`)

- **Playbook:** editable text (versioned), plus a **Learnings** list (learning notes from finished experiments).
- **Rules:** the compliance profile (change class `rules`, §3.5).
- **Defaults:** production defaults.
- **Blueprints:** each with its accounts.
- **Experiments, Notes, History:** the shared components of §2.5.

### 2.4 Blueprint workspace (`/blueprints/<name>`)

Setup (pillars, series formats, voice and visual briefs, money, prompts, platform defaults), Accounts using it (with the version each is pinned to), Experiments, Notes, History. The hooks card adds a **Hooks** section (patterns shared to the blueprint).

### 2.5 Account workspace (`/accounts/<id>`)

S3's shared core plus tabs by type (S3 dashboard spec §7.3, #431). S3 builds a minimal `/accounts/<id>` read view first; S3c's workspace replaces it, keeping its tabs.

**Header:** handle, id, type, language, pair, blueprint and account versions, rung, "day N of 90", open review windows, + Note, Pause this account. A banner shows a running experiment, with progress ("day 4 of 7" or "18 of 30 items") and a link.

**Tabs:**

| Tab | Content | Built by |
|---|---|---|
| **Overview** | S3's loop panels, next rung and day N of 90, plus S3c's running experiment and open notes and ideas | S3 (panels), S3c-1b (notes), S3c-3 (experiment) |
| Type tabs | clips: **Sources & episodes** (S3), **Framing & captions** (reframe mode, no-face fallback, length and minimum score, caption preset, hook title card, credit line, loudness; S3c's setup routes); others with their producers | S3 / S3c-2 |
| **Autopilot** | the controls, presets, rails and windows, spend (S3 dashboard spec §7.3) | S3 (over S2's autopilot service) |
| **Style** | S3c's setup fields grouped as Look, Voice & persona, Format and Posting. Each value shows its origin and change class. Saving goes through `POST /setup/preview` and the versions service: no new write path. The preview frame comes with Framing & captions in S3c-2. It is a still of the account's last rendered item, because only the `default` caption preset exists; a re-render with the pending change comes with the first second preset (a contract change, §1.4) | S3c-1b (S3c-2 for the preview frame) |
| **Hooks** | the hook library (S3 dashboard spec §7.3) | the hooks card |
| **Activity** | what ran without the owner, per day | S3 |
| More → **Setup & History** | **Setup:** every effective value, with a badge for its origin. An override shows what it replaces and has **Reset** (drop the override, inherit again). **Edit** changes only this level's fields; saving requires a note, validates, and writes version N+1; validation errors show inline and nothing is saved. **Experiment…** starts the experiment flow with the same form. **History:** versions (author, note, date, experiment link). Pick two to **diff** (side by side on a laptop; "field: old → new" on a phone). **Restore this version** saves it again as a new version | S3c-1b |
| More → **Results** | §4 | S3c-3 |
| More → **Experiments**, **Notes** | this account's | S3c-3, S3c-1b |
| More → **Sources** | the account's sources (S1), each linking to the Sources page | S3 |

- **Laptop:** tabs across the workspace. Setup is a 3-column table (field, value, origin with override info).
- **Phone:** the tab row wraps to two rows; Setup shows grouped rows ("max clip length · 45 s · [account ▸ overrides 60 s]").

### 2.6 Experiment flow

1. **Start** from an idea note ("Try this"), from Setup ("Experiment…" instead of Save), or from Experiments → New.
2. **Scope:** one account, or a category or blueprint plus a checklist of its accounts. Accounts with a running experiment are shown disabled, with the reason.
3. **Define:**
   - the hypothesis;
   - the change (the edit form, previewed as a diff against the current version);
   - one metric (only those available now, §4.1);
   - the window (N days or N items);
   - the **cost preview** (§3.4), with the optional "also re-cut the backlog" tick-box.
4. **Run:** Start writes the new version(s) and makes them effective; status `running`. The account shows the banner with progress and before vs during so far, plus the "too few items" warning while it applies.
5. **Decide:**
   - When the window closes and outcomes have settled (§4.2), the experiment shows as **needs a decision** on Home, on Experiments and in the account's banner. Each links to its page, `/experiments/<id>` (§2.7).
   - **Keep and Revert exist only on that page (D7).** Home's card, the lists, the account banner and the 09:00 digest only link to it. No other page, route caller or Telegram message decides an experiment (ADR-44).
   - **Keep:** the version stays; for a category or blueprint experiment, it offers to move the other accounts too. **Revert:** restores the from-version as a new version. Each needs a reason.
   - Either way, "Add a learning to the playbook" is offered, with the result pre-filled.

### 2.7 Experiments (`/experiments`)

Four lists across all accounts: **Needs a decision**, **Running**, **Drafts**, **Ideas** (open idea notes, each with "Try this"). Tables on a laptop, cards on a phone. `/experiments?needs=decision` opens the page filtered to the first list (the digest links there). Hook rotation is never listed here (ADR-50).

**The experiment page (`/experiments/<id>`)** shows:
- the hypothesis, scope and accounts;
- the change as a diff (from and to version);
- the metric, the window and progress;
- the cost line from its preview (§3.4);
- the before and during cards (§4.2) and the verdict (§4.3);
- **markers** for what changed outside the experiment during its window: autopilot changes from `autopilot_events` ("Produce switched on, day 3", "demoted to Hands-on, day 5"), the pause, and source holds. Autopilot changes are allowed during a run (S3 dashboard spec §8.4); the markers keep the result honest.

The actions depend on the status:
- a draft has **Edit**, **Start** and **Delete**;
- a running one has **Stop**;
- one that needs a decision has **Keep** and **Revert** (each with a required reason), then "Add a learning to the playbook".

This is the only place an experiment is decided (D7).

### 2.8 Notes and Home

- **+ Note** (header of category, blueprint and account pages, and S3's global + Note on the phone): kind and text in one step, for ideas that come up while scrolling the feeds.
- **Home:** a "needs me" row of kind `experiment_decision`, digest level (S3 dashboard spec §7.11). It links to each experiment's page and has no Keep or Revert buttons (D7).

### 2.9 Page links, Telegram's role and notifications (D10, ADR-44, ADR-45)

S3c's pages use the deep-link formats of [08 §2b](../../studio/08-dashboard-and-operations.md#2b-two-surfaces-one-product-adr-44-adr-45) and the link contract (S3 dashboard spec §7.10). The formats 08 §2b lists are used as they are. S3c adds the rows marked *new*, which follow the same pattern (a path, plus a query for a filter or tab). Login keeps the target (`callbackUrl`, relative paths only, log #99).

| Page | Path | In 08 §2b | Linked from Telegram |
|---|---|---|---|
| Accounts | `/accounts` (Map), `/accounts?view=compare` | `/accounts?view=compare` (08 §2c) | the weekly digest (Compare) |
| Account workspace | `/accounts/<id>`; a tab with `?tab=overview\|autopilot\|style\|hooks\|activity\|setup\|results\|experiments\|notes\|sources` (or a type tab); a diff with `?tab=setup&from=<n>&to=<n>` | `/accounts/<id>` | yes, as listed in 08 §2b |
| Category workspace | `/categories/<code>` | *new* | no |
| Blueprint workspace | `/blueprints/<name>` | *new* | no |
| Experiments | `/experiments`; filtered with `?needs=decision` | `/experiments?needs=decision` | the digest's "experiments need a decision" line |
| Experiment page | `/experiments/<id>` | `/experiments/<id>` | yes, where a message names one experiment |

- **Paths:**
  - Category and blueprint workspaces sit at top-level paths, not under `/accounts/…`, because an account id (`[a-z0-9][a-z0-9-]{0,39}`) could otherwise be `c`, `b` or any segment name. The paths match the API routes (§5.1).
  - An unknown id on any of these pages shows "not found" with a link back to `/accounts` or `/experiments`, never a blank page.
  - `?tab=history` (card 003's form) redirects to `?tab=setup`, so an older link still lands.
- **Telegram's role (ADR-44):** none for setup edits, notes, versions or experiment decisions. Those are dashboard tasks (08 §2, Accounts and Experiments rows); Telegram only deep-links.
- **Notifications (ADR-45):**
  - "Experiments need a decision" is a **digest** line at 09:00 (not instant), linking to `/experiments?needs=decision`.
  - Version saves, "Apply to accounts", note changes and experiment starts are **dashboard only**. S3c adds no instant alert.
  - The digest itself is S2's (S2 plan, Task 23). S3c-3 provides the line as a **digest provider**, `experiments.digest_line(db, now) -> DigestLine | None` (the S2 plan's `DigestProvider`, Task 23: `None` at 0, else "N experiments need a decision" linking `/experiments?needs=decision`), registered in `runtime.build_deps`. No S2 module changes (owner ruling, §7 Q6, log #261).

## 3. How producers use the setup (approved)

### 3.1 When the setup is read (clips, step by step)

| Moment | Who | Reads | Effect |
|---|---|---|---|
| Job created (`POST /jobs`, `clipforge clip`, Produce) | `service.create_job` | the account's **current** version | Fills `ClipOptions` (min_len, max_len, min_score, n, reframe, caption preset), the prompt versions, and stamps `JobInput.setup = {account_id, version}` (additive). The setup is **frozen for the job**: an edit mid-job doesn't change a running job. Steps still pass only ids and options, so stage modules stay free of DB and Modal code (ADR-9, ADR-12) |
| transcribe, highlights | stages | min_len, max_len, the highlights prompt version (already in the highlights cache key); then min_score and n after the cache | §3.3. The language is never passed to Whisper, so the transcribe key stays `auto` (§7 Q1) |
| highlights → clips | `pipeline/steps.py` | the account's language, from the job's stamped setup | The language-mismatch hold below |
| captions | stage | caption preset, keywords prompt version | §3.3 |
| Enqueue (package) | posting | the **job's** stamped version | Enabled platforms per item (as S1 built). Copies `setup_version` onto each `content_items` row |
| Send (tick, then S2's dispatcher and hand-off) | posting | the account's **current** version | Hashtags, CTA, bio link, slots. These are posting-time settings, not baked into the item. Each send is attributed by time, to the version in force at its hand-off claim (`SetupRepo.version_at`): `sends.at` for an assisted send, `posts.claimed_at` for an Upload-Post hand-off. No posting writer is edited (§4.1; plan Task 14) |

**Prompts stay files** (CLAUDE.md rule 4). The setup stores only which **released** version to use, chosen from `prompts/metadata.json`. Editing prompt text is still a repo change that creates the next version.

**Language** is part of a clips account's identity (EN and ES are separate accounts, 01). It's editable but not an experiment lever.
- When the transcript's detected language differs from the account's, the job is **held** with that reason instead of producing off-language clips.
- The account's language is **never** Whisper's language hint (owner ruling, §7 Q1): Whisper keeps auto-detect, the transcribe key stays `language: auto`, and no source is transcribed again because of S3c. The hold is the only use of the account's language in production.

### 3.2 The setup version and cache keys

- The setup version is **never** part of a cache key. Otherwise a hashtag edit would re-render everything.
- Setup values only feed the key inputs that already exist (ADR-8). **Existing items are never touched;** a change applies to new jobs and to explicit re-cuts.
- The captions key gains the caption preset **only when it isn't `default`**, so today's cached captions stay valid (a pinned-value test guards it).

### 3.3 What a change costs

| Change | Re-runs | Extra cost for a new job | Cost to re-cut an already-clipped source |
|---|---|---|---|
| min_score, n | nothing (applied after the cache) | none | **free** |
| min/max length, highlights prompt version | highlights, then per clip: reframe (cached for the same range), captions, render | none | **~$0.07 per source hour** + ~$0.001 per clip |
| reframe mode | per clip: reframe, captions (cached), render | none | **~$0.001 per clip** (CPU) |
| caption preset, keywords prompt version | per clip: captions (Haiku, ~$0.0005) + render (CPU) | none | **~$0.0015 per clip** |
| platforms, hashtags, CTA, bio link, slots | nothing (posting time) | none | free |

The language isn't in this table: it's an identity field, never a Whisper hint, and never re-cuts (§7 Q1).

Prices come from `config.Prices`. The plan re-checks the per-clip numbers against `metadata.json` costs.

### 3.4 One dry run: `POST /setup/preview` (D4)

Saving a version and starting an experiment show the same preview, from one service function (`accounts/preview.py`, Modal-free) behind one route. `GET …/diff` alone isn't enough: it compares two **saved** versions, while a save or an experiment start has to be previewed **before** anything is written. So the preview is a standalone route, and both flows call it.

- **Request:** `{target: {kind: category|blueprint|account, id}, expected_version, proposed: <the full snapshot the form would save>, accounts?: [ids], recut_backlog?: bool}`.
  - `accounts` holds the "Apply to accounts" ticks for a category or blueprint save, or the chosen accounts for an experiment.
- **Response:**
  - `diff`: field by field, `{path, from, to, change_class}` (§3.5). This is the same shape `GET …/diff` returns for saved versions.
  - `reruns`: which stages a new job re-runs because of the change (from §3.3: none, highlights onward, or captions and render), and whether the change takes effect at the next enqueue or send (`live`) or on new jobs.
  - `affected`:
    - the accounts that get a new version, with those skipped because of a running experiment, and why;
    - per account, the queued items whose next send uses a changed `live` field;
    - whether `format_changed` is set (the first 10 new items go to `review`, §3.5);
    - with `recut_backlog`, the sources and clips that would be re-cut.
  - `estimate`: "new jobs: no extra cost". With `recut_backlog` it adds the re-cut cost, from `config.Prices` and the source hours in S1's `jobs` table. For example: "Re-cutting the 3 sources already clipped for this account (4.2 source hours): ~$0.29 + ~$0.09 for 60 clips = **~$0.38**".
  - `blocked`: the reasons the save or start would be refused, with the same codes the write route returns:
    - a running experiment and a non-identity change (§4.4);
    - a rules field in an experiment;
    - loosening a rule without `confirm_loosen`.
- **Validation:** a proposal that doesn't validate answers 422 with field errors (§5.2), exactly as the save would. A stale `expected_version` answers 409 with the latest version.
- **It writes nothing:**
  - The save (`PUT …`) and the experiment start (`POST /admin/experiments/{id}/start`) recompute the same function inside their transaction and refuse if the result is `blocked`, so the preview and the write can't disagree.
  - A drift between preview and write (someone saved in between) is caught by `expected_version` (409).
- **In the dashboard:**
  - The save dialog shows the diff, what re-runs, who is affected and "no extra cost for new jobs" before the required note and Save.
  - The experiment form shows the same block, plus the "also re-cut the backlog" tick-box, which reruns the preview with `recut_backlog`.
  - Without the tick, the experiment uses only new jobs and costs nothing extra. A plain save never re-cuts (existing items are never touched, §3.2).

### 3.5 Change classes: what's live-editable and what needs review

Every field in the registry (§1.4) has one class; the dashboard and API enforce it.

| Class | Fields | Takes effect | Experiments |
|---|---|---|---|
| **live** | hashtags, CTA, bio link, slots, platforms, min_score, n, money | the next enqueue or send | yes |
| **recut** | min/max length (account-wide and per platform), reframe mode, caption preset | new jobs; the cost is shown (§3.3) | yes |
| **format** | prompt versions, series formats, pillars, niche, voice and visual briefs | new jobs; see the format window below | yes |
| **rules** | the compliance profile (category, overridden by the blueprint) | saved only by the owner, with a note; **loosening** a rule needs an explicit confirmation | **no** (policy isn't A/B-tested) |
| **identity** | handles, language, pair, persona, posting chat and time zone, playbook | saved directly | no |

- **Moved out (ADR-48):**
  - The review tier was "rules"; it is now `autopilot.review_dial`.
  - The budget was "identity"; it is now `autopilot.monthly_cap_usd`.
  - Both are written only by `accounts/autopilot.py`, never by a setup save (§1.3).
- **Moved out (ADR-41):** "pause" was "live"; it is runtime state in `posting_state`, written only by `/pause` and `/go`.
- **"cadence"** is the slots: there is no separate cadence field until a producer needs one.

**The format window: what S3c stores and what S2 reads.** ADR-29 says "a new format starts in `review`", and ADR-48 makes it a 10-item rail.
- **The flag:** the versions service sets `account_versions.format_changed = true` when the new effective setup differs from the previous version's in any `format`-class field. This includes a change that arrives through "Apply to accounts" and a restore.
- **What S2 asks for** (the S2 plan, Task 6, as amended for the owner's ruling, log #142): a `FormatWindowSource` protocol with `format_window(account_id) -> tuple[int, int] | None`. `ReviewRepo(db, format_source=NoFormatWindow())` defaults to "no window", and `route` reads `counts.format_version`.
- **What S3c provides:**
  - `content_items.setup_version` on every new item;
  - `SetupRepo.format_window(account_id) -> tuple[int, int] | None`, which implements `FormatWindowSource`. It returns `None` when no version of the account has `format_changed`. Otherwise it returns `(n, decided)`:
    - `n` is the highest version with `format_changed`;
    - `decided` counts the account's items with `setup_version >= n` that have a counted decision under S2's rule (a `post_events` row of kind `approved` or `reviewed` whose `actor` doesn't start with `system:`).
  - The window is open while `decided < 10`.
- **Wiring (S3c-2):** `runtime.build_deps` passes `SetupRepo(db)` as `format_source`. No S2 module changes. Until S3c-2 deploys, S2 uses `NoFormatWindow()` and the window stays closed, as S2's spec says.

### 3.6 Timing against S1, and other producers

The setup reaches production only after S1's rollout (card 010): the database and `blueprints/` in Modal, reads on Postgres. Before that, S3c can't be deployed at all, because every route needs the database. After S3c-1a deploys and before `verify` passes, S3c shows and edits versions, and producers keep today's constants (`SETUP_SOURCE=off`, §5.6).

The story, band, avatar and model producers (S6 and later) take `EffectiveSetup` as an input from their first version (voice style, series rotation, briefs) and use the same field registry.

## 4. Results (approved)

### 4.1 Metrics

A metric registry: name, unit, direction (higher is better or not), availability (now or S7), and attribution (per item via `content_items.setup_version`, or per send via the version in force at its claim time, `SetupRepo.send_versions`).

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

**After S7:** views at 24 h and 7 d, retention or average watch %, followers gained, link clicks (S2 tracking links), revenue and RPM. They are attributed per item through `posts`, each with a **maturity age**.

- The experiment form offers only metrics available now. S7 metrics show greyed out ("after S7").
- Posting-time experiments default to per-send metrics; production experiments to per-item metrics.
- **Hook-pattern metrics** (approval rate per pattern, 👍/👎, later the 3-second hold) are reported on the **Hooks** tab by the hooks card. They are not in this registry, because hook rotation is never an experiment (ADR-50).

### 4.2 Before vs during

- **During:** items (or sends) stamped with the experiment's to-version, from the start until the window closes (N days or N items).
- **Before:** the same account's most recent items under the from-version, over a window of the same size (same number of days, or the same N items). If fewer exist, it uses what's there and says so.
- **Only settled outcomes count:**
  - Items still queued, or sent but undecided, at the window's end show as "pending".
  - The experiment becomes **needs a decision** once ≥ 80% are decided, or 3 days after the window closes, whichever is first.
  - S7 metrics wait for their maturity age ("done: waiting for data").
- **Category or blueprint experiments:** results per account and pooled. The scope's non-chosen accounts appear as a same-period **comparison group** when there are any.
- **Display:**
  - Two cards (before, during) with value, counts ("3 of 20 rejected") and difference.
  - The account's Results tab: a table per version (dates, items, posted, reject rate and top reason, cost per item; S7 columns later) and one chart of the chosen metric over time.
  - The chart has a marker at each version change, and the §2.7 markers (autopilot changes, pauses, holds).

### 4.3 Judging, and the "too few items" warning

- **Too few to judge** when either side has fewer than **10 decided items (or sends)**. Keep and Revert still work; the experiment records `thin_data`.
- **Rates:** a 90% Wilson interval on each side. The verdict reads **likely better**, **no clear difference** (intervals overlap) or **likely worse**.
- **Continuous metrics** (score, cost, views): medians with the p25–p75 range; overlapping ranges mean no clear difference.
- No p-values: plain labels and the counts.

### 4.4 Keeping results clean while an experiment runs

- While an account has a running experiment, its setup saves are limited to **identity** fields. Any other change asks to **stop** the experiment first (status `stopped`: partial numbers kept, no decision).
- Category and blueprint "Apply to accounts" skips accounts with a running experiment (§1.1).
- A pause, a source hold or a posting outage during a **day-based** window extends it by the days nothing was sent. The banner says so.
- **Autopilot changes aren't blocked** (they aren't setup, §1.3). They show as markers (§2.7). A demotion or a dial change mid-run is visible next to the result, not hidden in it.
- **Hook rotation weights freeze** while the account runs an experiment (ADR-50), so both sides rotate hooks the same way. The hooks card (card 020) owns the weights and the freeze; S3c **pushes** the change:
  - One protocol, `HookFreezer`, with `freeze(conn, account_id, experiment_id)` and `release(conn, account_id, experiment_id)`, lives in `src/clipforge/hooks/freezer.py` with `NoHookFreezer`. Whichever of S3c-3 and the hooks build (HK-1) lands first creates the file, with identical content, and the other imports it. The hooks build implements the protocol. `POST /admin/experiments/{id}/start` calls `freeze` for each chosen account; `stop` and `decide` call `release`.
  - Until the hooks build deploys, `runtime.build_deps` passes a no-op freezer. If the hooks build deploys after S3c-3, it freezes the experiments already running at its deploy.
  - Each call runs inside the same transaction that flips `experiment_accounts.running`, so the freeze and the running flag can't disagree.
  - Both are no-ops for an account with no hook weights.
  - A `running` experiment whose window closed still counts as running until `decide` or `stop`, so the weights stay frozen until the decision.
  - `db/experiments.py::running_experiment(conn, account_id) -> ExperimentRef | None` stays as a **read guard only** (the `experiment_accounts` row with `running`, the rows the one-running index guards). The hooks card may check it before a weight change; it never drives the freeze.
  - Before S3c-3 ships there are no experiments, so nothing is ever frozen.

## 5. API, errors, data, migration, tests, rollback, cost (approved)

### 5.1 Routes

All on S3's **`admin`** endpoint (ADR-38, D9) with `ADMIN_API_TOKEN`. The author comes from S1's `X-Clipforge-Actor` header, which the dashboard's route handlers set to `web:<login>` (§5.3). S1's `/accounts` and `/sources` routes and CLI (S1 Task 18) are reused.

**`PATCH /accounts/{id}` after S3c-1a** keeps S1's request shape and writes a new version through the versions service (owner ruling, §7 Q2):
- Its setup fields (handles, chat, slots, time zone, hashtags) become a proposal against the current version, with the CLI's actor and an automatic note ("account edit from the CLI").
- `review_tier` in the request is refused with 422 "the review tier is the Review dial: `clipforge autopilot set <account> review_dial …`" (ADR-48).

Every route in this table is under `/admin/` (for example `GET /admin/categories`), in S3's `admin_routers`, on the `admin` surface only. The CLI's routes (`PATCH /accounts/{id}`, `/setup/import`, `/setup/verify`, `/setup/export`) are in S3's `cli_router`, which S3-5b's cut-over moves to `admin` (log #146).

| Area | Routes |
|---|---|
| Categories | `GET /categories`, `GET /categories/{code}`, `PUT /categories/{code}` (save → new version), `GET …/versions`, `GET …/versions/{n}`, `POST …/versions/{n}/restore` |
| Blueprints | the same under `/blueprints/{name}`, plus `POST /blueprints` (copy an existing one), `POST /blueprints/{name}/apply {version, accounts[]}` |
| Accounts | `GET /accounts/{id}/setup` (effective setup, origins, version; Style and Setup read it), `PUT /accounts/{id}/setup`, `GET …/versions`, `GET …/diff?from=&to=`, `POST …/versions/{n}/restore`, `GET …/results?metric=` |
| Setup preview | `POST /setup/preview` (§3.4): the one dry run for a save, a restore, "Apply to accounts" and an experiment start; writes nothing |
| Experiments | `POST /experiments` (draft), `PUT /experiments/{id}` and `DELETE /experiments/{id}` (drafts only), `GET /experiments?status=&needs=decision`, `GET /experiments/{id}` (with the live result, the markers and the draft's preview), `POST …/{id}/start`, `…/stop`, `…/decide {keep\|revert, reason, promote?, learning?}` (called only from the experiment page, D7) |
| Notes | `POST /notes`, `GET /notes?target=&status=`, `PATCH /notes/{id}`, `POST /notes/{id}/experiment` |
| Pickers | `GET /metrics` (§4.1), `GET /prompts` (released versions from `prompts/metadata.json`), `GET /setup/fields` (the field registry, §1.4) |

- **No new cron:** "window closed" and "needs a decision" are **derived on read** from the stored `running` status and the data (ADR-27 keeps three crons). Only `decide` and `stop` write a final status.
  - The same derived read, `experiments.needs_decision(db, now) -> list[ExperimentRef]`, feeds the digest provider `experiments.digest_line` (§2.9), S3's "needs me" row `experiment_decision`, and Compare's focus ranking.
- **Start, stop and decide push the hooks freeze** (§4.4): `HookFreezer.freeze`/`release` run in the same transaction as the `running` flag.
- **Every write that changes `posting`** calls the schedule-copy writer after its commit (§5.3).
- **Every write runs the preview first.** `PUT …` saves, `…/restore`, `…/apply` and `…/start` call the §3.4 function in their transaction and refuse with its `blocked` reason, so there is one dry-run path. The earlier `GET /experiments/{id}/estimate` is folded into it.
- **Contract (#49):** `POST /jobs` gains an optional `setup` in `JobInput`. `GET /jobs/{id}` and `GET /posting` don't change (`PostingOverview.accounts` already carries per-account data). `web/openapi.json` is regenerated in the same checkpoint.

### 5.2 Error paths

- **422 `{errors: [{path, msg}]}`:** every save is a full snapshot validated by pydantic; nothing is saved on failure. This is an exception to S3a's "never pass upstream bodies through": structured field errors from our own `admin` endpoint are shown inline.
- **409, version conflict:** saves carry `expected_version`. A save in between (another tab, a session, an experiment) returns "changed since you opened it" plus the latest version, and the dashboard shows the diff to re-apply.
- **409, experiment conflicts:** starting an experiment on an account that already runs one, or editing non-identity fields during a run (§4.4). Both return the experiment's id.
- **404** unknown ids; **503** database unreachable (S1's convention; the dashboard shows "API unavailable").
- **Loosening a rule** without `confirm_loosen=true` → 422.

### 5.3 Data: S3c's migration (the next in landing order)

- **Its number** is the next after the head on `main` when it lands (S2a's 0002 first, then whichever of the hooks, S3 and S3c migrations lands next, one at a time; S3 dashboard spec §8.7, log #438). It comes after S2a's 0002, guaranteed by S3c-1a's start condition (§6); otherwise §8.7 applies. It may land before or after the hooks and S3 migrations. The same change moves `EXPECTED_HEAD` in `src/clipforge/db/doctor.py`. A card whose migration waits behind another rebases and renumbers before it lands. It is expand-only, and 0001 is frozen.
- **It carries none of the deferred items:** `jobs.error`, `post_events.actor` (with its backfill and check constraint) and `posting_state.changed_by`/`reason` land with S2a's 0002. S3c reads them; it never adds or backfills them.

**Tables and columns:**
- `categories(code PK, current_version)`, seeded with the 5 codes.
- `category_versions(code, n, data jsonb, author, note, created_at)`, primary key `(code, n)`. `data` = playbook text, rules, defaults.
- `blueprints(name PK, category → categories, current_version)`; `blueprint_versions(name, n, data jsonb, author, note, created_at)`, primary key `(name, n)`.
- `account_versions(account_id, n, category, category_version, blueprint, blueprint_version, overrides jsonb, identity jsonb, format_changed bool, author, note, experiment_id, created_at)`. `category` and `blueprint` carry the parents' keys for the composite FKs:
  - primary key `(account_id, n)`;
  - composite FKs to the pinned parent versions (§1.1);
  - `format_changed` feeds S2's format window (§3.5);
  - `identity` holds the §1.4 identity fields only: no review tier, no budget.
- `accounts.current_version int NULL` (filled by the import, then always set).
  - The existing `accounts` columns that §1.4 maps (`blueprint`, `blueprint_version`, `kind`, `language`, `niche`, `platforms`, `brand`, `posting`, `paired_account_id`, `persona_id`) become a **projection** of the current version, written only by the versions service. S1 and S2 code reading `accounts` keeps working (one writer per column group, ADR-41).
  - `review_tier` and `monthly_budget_usd` are left as they are (§1.3), and `publisher` keeps S2's writer.
  - **The posting schedule copy (ADR-41).** The tick, and S2's dispatcher after it, read `posting:schedule:<account>`, whose one writer is S2a's `accounts/service.write_schedule_copy(kv, account, autopilot)` (it replaced S1's `publish_schedule` and adds `publish_via` and `profile`). Every write that changes an account's projected `posting`:
    - a save, a restore, "Apply to accounts" and `PATCH /accounts/{id}`;
    - calls `write_schedule_copy` after its transaction commits, for each account it changed, with that account's `autopilot` row (or `hands_on(account)` when it has none), so the copy keeps its one writer and an Upload-Post account keeps `publish_via="upload_post"`;
    - validates the proposed schedule with S1's `_checked` first (the posting chat must be in `TELEGRAM_ALLOWED_USER_IDS`, 1–12 slots, a valid time zone and hashtags), refusing with 422 as the save would.
  - S2's publisher edit (`--publisher-profile`, `--facebook-page-id`, `--clear-publisher`) keeps its own path: it writes `accounts.publisher` (not a projected column) and writes no version. `PATCH /accounts/{id}` splits a request that carries both.
  - A failed copy write after a commit is an error the caller sees. Repeating the save, or the daily sync (`sync_schedules`), rewrites it, as for S1's edit today.
- `experiments(id, scope_type, scope_id, hypothesis, change jsonb, metric, window_kind, window_size, recut_backlog, status, started_at, ended_at, decision, reason, decided_at, decided_by, thin_data, author, created_at)`.
- `experiment_accounts(experiment_id, account_id, from_version, to_version, running bool)`. A partial unique index on `(account_id) WHERE running` allows **one running experiment per account**; `start` sets `running`, and `stop` and `decide` clear it in the same transaction as the experiment's status.
- `notes(id, target_type, target_id, kind, status, text, experiment_id, author, created_at, updated_at)`. A learning is a `learning` note on the category, listed under the playbook; the playbook text itself is versioned in `category_versions`.
- `content_items.setup_version int NULL`, FK `(account_id, setup_version)` → `account_versions`. It is NULL for items made before versioning ("before versioning").
- Sends carry no stamp: they are attributed by time (§3.1).

**Actors and append-only rules:**
- The `author` columns of the `*_versions` tables, `experiments` and `notes`, and `experiments.decided_by`, use the actor format S2a's 0002 checks on `post_events.actor`: `telegram:<id>`, `web:<login>`, `session:<name>`, `cli:<user>` or `system:<component>`. They are `NOT NULL` except `decided_by`, with a check constraint using the same pattern, at most 80 characters.
  - Every setup write carries the person who made it: the import's version-1 rows carry whoever ran `setup import` (`cli:<user>`), and "Apply to accounts" carries whoever tapped it. S3c itself writes nothing as `system:`; the prefix is allowed so the check matches S2's, whose `system:demotion` and `system:filler` write `autopilot`, not the setup.
- The `*_versions` tables are **append-only**, enforced by a trigger that rejects UPDATE and DELETE (like S2's `autopilot_events`).

### 5.4 Migration: `clipforge setup import [--dry-run]` and `setup verify`

Modelled on S1's `source import-toml`.
1. **Categories v1:**
   - rules from the 07/09 "must have" table;
   - defaults = today's constants (30–60 s, min_score 0.80, n automatic, reframe `auto`, caption preset `default`, `highlights_v1`, `keywords_v2`);
   - the playbook: a short draft (about 150–300 words) per category, written by S3c-1a from 01, 07 and 09 into the importer's seed file, for the owner to edit in the dashboard (owner ruling, §7 Q3).
2. **Blueprints v1** from `blueprints/*.toml` (the note records the file name and hash). A blueprint's `compliance` becomes a rules override only where it differs from its category.
3. **Accounts v1**, pinned to category v1 and blueprint v1:
   - A value S1 copied into the account (`niche`, `platforms`) is kept as an override **only where it differs** from the blueprint; identical copies are dropped, so they inherit.
   - `kind` is **never** an override: it always comes from the blueprint's category.
   - The §1.4 identity fields go into `identity`.
   - `review_tier` and `monthly_budget_usd` are not imported (they are S2's `autopilot` seed, §1.3).
4. Re-running is safe: it skips anything already imported.
5. **`setup verify`** checks, field by field, that each account's effective setup, projected back onto S1's columns, equals its `accounts` row. It must report **0 differences** before the switch.

After the import, `blueprints/*.toml` is no longer read:
- `account create --blueprint` reads the DB, and `load_blueprint` survives only in the importer.
- The files stay in the repo, untouched, until the move has been verified for 7 days.

### 5.5 Tests

Local Postgres, as in S1. Previews are build-only, so the checks run locally and in production.
- **Pure:**
  - the resolver and origins (an override wins; reset inherits);
  - field-registry classes, and that no registry path names the review tier, the budget, the pause or a hook;
  - the preview (diff, re-runs, affected accounts and items, blocked reasons, the estimate with and without the re-cut);
  - `format_changed` set exactly when a format-class field differs, including through apply and restore;
  - before/during windows, including a window extended by a pause;
  - the Wilson verdict and the 10-item floor.
- **DB:**
  - `*_versions` append-only (trigger);
  - restore writes a new version;
  - 409 on `expected_version`;
  - one running experiment per account;
  - non-identity edits blocked during a run;
  - import re-runnable and `verify` at 0 differences;
  - the `accounts` projection equals the current version and never touches `review_tier`, `monthly_budget_usd` or `publisher`;
  - a save, a restore, an apply and a `PATCH` that change `posting` rewrite `posting:schedule:<account>` after the commit (and only then), and a disallowed posting chat is refused with nothing written;
  - the author check accepts `system:migration` and rejects a bad actor;
  - a save refused by the preview writes nothing;
  - `start` calls `HookFreezer.freeze` and `stop`/`decide` call `release` in the transaction that flips `running` (a failed call rolls the flip back); `running_experiment` answers while the window is closed but undecided;
  - `SetupRepo.format_window` returns `None` without a flagged version, else the newest flagged version and the decisions counted under S2's rule (system actors and assisted taps excluded);
  - the migration's head equals `EXPECTED_HEAD`.
- **Pipeline:**
  - `create_job` stamps the setup and fills `ClipOptions`;
  - the **setup version is in no cache key** (a hashtag change gives identical keys);
  - a pinned captions key for the `default` preset;
  - a language mismatch holds the job;
  - with `SetupRepo` as S2's `format_source`, `route` opens the format window after a format change and closes it after 10 counted decisions;
  - `experiments.digest_line` answers `None` at 0 and a line with the link otherwise, and a raising provider leaves the rest of S2's digest intact (S2's `gather` skips it);
- **API:**
  - every route answers 401 without the token, 422 with field errors, and 409 and 503 where they apply;
  - `POST /setup/preview` and the matching write agree (the same `blocked` reasons and diff);
  - `decide` refuses an experiment that doesn't need a decision;
  - `PATCH /accounts/{id}` writes a version and refuses `review_tier`.
- **Web:**
  - Playwright in the phone and desktop projects, against a mocked admin API, for the account workspace (Style, Setup & History), the edit → preview → save → diff → restore loop, and the experiment flow with its markers;
  - every §2.9 path loads, an unknown id shows "not found", and `?tab=history` redirects;
  - Keep and Revert appear only on `/experiments/<id>`.

### 5.6 Rollback

- **Everything is additive:** new tables, one nullable column on `content_items` (`setup_version`), one on `accounts` (`current_version`), one optional `JobInput` field.
- **`SETUP_SOURCE=db|off`** (default `off` until `verify` passes):
  - With `off`, job creation ignores the setup: `create_job` uses today's constants and stamps no `JobInput.setup`. The dashboard still edits and reviews versions (edit and review only, as §3.6, §6, 04 and 06 say).
  - The live posting fields (slots, hashtags, CTA, bio link, platforms) still reach production while it's off, because a save rewrites the `accounts` projection and the schedule copy (§5.3), which the tick reads today.
  - Rolling back is a config change plus a redeploy (or `modal app rollback`).
- **Last resort:** `alembic downgrade` to the previous head drops the new tables and columns. Take a `setup export` JSON snapshot first, because that loses history. Downgrading never touches S2's or the hooks card's tables.

### 5.7 Cost

- Design: $0.
- Build: tests run locally; no Modal or LLM spend beyond one smoke run (~$0.01).
- Runtime: a few small queries per job and per send, and results queries on Neon's free tier.
- Real money is spent only when the owner ticks "also re-cut the backlog" (priced in §3.3–3.4).

## 6. Roadmap (approved)

**S3c "Account workspaces"** is its own item in four deployable parts (owner ruling, §7 Q4: S3c-1 is split into data and pages). S3 drops its "Accounts (profile editor)" page; S3 builds Compare and a minimal account read view, and S3c's Map and workspaces build on them.

| Part | Builds | Can start | Switch |
|---|---|---|---|
| **S3c-1a: data and routes** | its migration (the next in landing order; no deferred items), the resolver and field registry, the versions service (projection, `format_changed`, 409), `POST /setup/preview` (diff, re-runs, affected, blocked; D4), `setup import` (with the drafted playbooks) and `verify`, the admin routes for categories, blueprints, account setup, versions, diff, restore, notes and pickers, `PATCH /accounts/{id}` writing versions, the CLI | S1's rollout (card 010) done, S2a deployed (card 014) and S3-1 deployed (card 022: the `admin` endpoint); its migration is numbered after any hooks or S3 migration already on `main`. | `SETUP_SOURCE=off`; nothing visible yet; the owner runs `setup import` and `setup verify` in production |
| **S3c-1b: pages** | the Accounts Map and Compare's versions and experiment columns, the category, blueprint and account workspaces at the §2.9 paths (Style, Setup & History with origins, diff and restore; Overview's experiment and notes slots), notes and + Note | S3c-1a deployed, and S3-5 deployed (card 026: Compare and the account read view) (§7 Q5, log #263) | `SETUP_SOURCE=off`: edit and review only |
| **S3c-2: wiring into the clip producer** | `create_job` reads and stamps the setup; `content_items.setup_version`; sends attributed by their claim time (`SetupRepo.send_versions`); caption preset in the captions key (only when not `default`); prompts from released versions; the language-mismatch hold; `SetupRepo.format_window` wired as S2's `format_source` in `runtime.build_deps`; the Framing & captions tab and Style's preview frame | S3c-1b; S2a deployed (it defines `FormatWindowSource` and `ReviewRepo`'s `format_source`) | `SETUP_SOURCE=db` after `verify` reports 0 differences |
| **S3c-3: experiments and results** | the experiment flow and page (`/experiments/<id>`, the only place to keep or revert, D7) with autopilot markers, the re-cut estimate in the preview, one running per account, the edit block during a run, the `HookFreezer` calls (a no-op until the hooks build), results with the metrics available now, the Wilson verdict and 10-item floor, the Experiments nav item, the `experiment_decision` row (an S3 needs provider registered in `runtime.build_deps`), the derived count and `experiments.digest_line` registered as a digest provider in `runtime.build_deps`, learnings in the playbook | S3c-2 deployed; S2c deployed (card 016: `DigestProvider`) | — |
| **In S7** | views, retention, followers, clicks and revenue in the metric registry, with maturity ages | S7 | — |

- **Other cards that read S3c:**
  - **S2** enforces §3.5's "a format change sends the first 10 items to `review`" through its `FormatWindowSource`; S3c-2 provides `SetupRepo.format_window` and wires it in `runtime.build_deps` (§3.5). S2c's digest takes S3c-3's `experiments.digest_line` as a provider.
  - **The hooks build** implements the `HookFreezer` protocol in `src/clipforge/hooks/freezer.py` (`freeze`/`release`, given the transaction's connection; the file is created by S3c-3 or HK-1, whichever lands first), which S3c-3's start, stop and decide call (§4.4).
  - **S3's needs router** takes S3c-3's `experiment_decision` provider from `runtime.build_deps` (log #147).
  - **S6 and later producers** read `EffectiveSetup` from their first version, so S3c-2's contract should come **before S6** (a soft dependency).
- **Graph:** `S1 → S3c`, `S3 → S3c` (admin endpoint), `S2a → S3c` (migration order, format window), `HK -.-> S3c` (migration order only), `S3c -.-> S6` (soft), `S7 → S3c` (engagement metrics).
- **Done when:** the owner changes realtalk's max clip length through an experiment, sees before and during for reject rate and posted rate, chooses Keep, and the learning shows in the clips playbook; all through the dashboard, on phone and laptop.
- **Cost:** ~$1 (tests and one smoke run); a backlog re-cut, if ticked, is extra.

## 7. Open for the implementation plan

**Settled by S1's merged code and the accepted ADRs (card 018):**
- **The actor's place.** Card 002's `posting/actions.py` passes the actor to `SqlPostingRepo`, and `db/posting._event` writes it into `post_events.data.actor` (checked in `src/clipforge/db/posting.py`). S2a's 0002 adds the column and backfills it from exactly that key. S3c does nothing for `post_events.actor`.
- **The exact field list and validation per level:** §1.4, from S1's final `Account`, `Blueprint`, `BrandKit`, `PlatformProfile`, `PostingSchedule`, `ComplianceProfile` and `ClipOptions`.
- **The review tier and the budget:** S2's `autopilot` table (ADR-48), not the setup (§1.3).

**The owner's rulings at checkpoint A (2026-10-02; decision log #254–#258 and #261, which superseded #259):**
- **Q1, the language hint: never passed to Whisper.** Auto-detect stays, the transcribe key stays `auto`, and nothing is re-transcribed because of S3c. The account's language is used only for the mismatch hold (§3.1, §3.3).
- **Q2, `PATCH /accounts/{id}`: same request shape, writing a version** through the versions service, with `review_tier` refused (422, pointing to `clipforge autopilot`) (§5.1).
- **Q3, the category playbooks: drafted** by S3c-1a from 01, 07 and 09 (about 150–300 words each), for the owner to edit in the dashboard (§5.4).
- **Q4, the build split: four parts.** S3c-1a (data and routes), S3c-1b (pages), S3c-2 (producer wiring), S3c-3 (experiments and results); each deploys alone (§6).
- **Q5, the start order:** S3c-1a starts once S2a and S3-1 (`admin`) are deployed; S3c-1b once S3-5 (Compare and the account read view) is deployed (§6; restated as "deployed" by the coordinator's review of the plan, log #144, #263).
- **Q6, the digest line, and the format window (the coordinator's finding 2): option (a).** S2's plan was amended instead of S3c editing S2's modules (log #142, #261, superseding #259):
  - S2 takes an injected `FormatWindowSource` (Task 6) and `DigestProvider`s (Task 23);
  - S3c-2 implements `SetupRepo.format_window`, and S3c-3 implements `experiments.digest_line`;
  - both are wired only in `runtime.build_deps` (§2.9, §3.5).

## 8. Changes to other documents

**Applied by card 018 (S3c-only):**
- **04, the S3c section:**
  - the migration as "the next in landing order", without `post_events.actor`;
  - the start conditions as "deployed" (S2a and S3-1 for 1a; S3-5 for 1b; S2c for 3);
  - four parts (Q4): S3c-1a data and routes, S3c-1b pages (the Map, Compare's columns, Style and Setup & History), S3c-2, S3c-3;
  - S3c-2 wires the format window into S2's routing and builds Framing & captions;
  - S3c-3 adds autopilot markers, the `HookFreezer` calls (a no-op until the hooks build), the derived decision count and its digest provider; S3c-2 the format-window source.
- **06, the S3c card:**
  - the same, plus the read list (the S3 dashboard spec §7.3, §7.4, §8.4, §8.5, §8.7; the S2 plan's Tasks 2, 3 and 6);
  - the start order (Q5) and the plan link (added at checkpoint B);
  - "card 018" in its pointer line.

**Applied by card 018 in 08 (in its scope, at the coordinator's request):**
- **08 §2, the Accounts row:** Compare and the Map; "tier" became "rung" (from `autopilot`); the workspace tabs follow §2.5 and 08 §2c.
- **08 §2b, Deep links:** `?tab=` takes S3 §7.3's tab names; `/categories/<code>` and `/blueprints/<name>` are dashboard-only formats.

**For the coordinator to fold in (outside S3c's files):**
- **04's dependency graph and the paragraph under it:** add `S2 --> S3c` (S2a's migration lands first, and S3c-2 wires S2's routing call site), and say S3c starts after S1's rollout, S2a's migration and S3's `admin` endpoint.
- **04's S2 section:** nothing more to change (the coordinator amended S2's plan and cards 014 and 016 for the injected sources, log #142).
- **04's HK section:** say that S3c-3's experiment start, stop and decide call the `HookFreezer` protocol in `src/clipforge/hooks/freezer.py` (`freeze`/`release`, given the transaction's connection; §4.4), and that migrations land S2a's 0002 first, then whichever of the hooks, S3 and S3c migrations lands next, one at a time, each numbered at landing.
- **No new ADR.** ADR-42's status line already says it is refined by ADR-48 and ADR-50, and nothing here changes a decision. The language ruling (Q1) is a log row, not an ADR, because it changes no contract.
