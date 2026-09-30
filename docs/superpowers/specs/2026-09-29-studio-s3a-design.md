# Studio S3a: dashboard shell (design)

Date: 2026-09-29 · Status: approved (2026-09-29); updated to match the implementation plan (docs/superpowers/plans/2026-09-29-studio-s3a.md)
Card: docs/studio/04-roadmap.md "S3a", docs/studio/06 (S3a). Background: ADR-2, ADR-38, 02 §8, 08 §2.

## 1. Goal and scope

A phone-first, owner-only web app in `web/` over today's deployed job API.

- **Home:** posting progress per channel from `GET /posting` (`PostingOverview`).
- **Job page:** one job from `GET /jobs/{id}` (`JobView`).
- **Jobs tab:** a job-id lookup box and a "recent jobs" list kept in the browser's localStorage. The API has no list route. Adding one is a Python change, which is out of scope for S3a; S1's `jobs` table is the natural source later.
- **More tab:** placeholders for Review, Calendar, Accounts, Produce and Costs.

**Done when:** the owner logs in on the phone and sees live posting progress from the deployed API.

**Out of scope:**
- the `admin` Modal endpoint and proxy auth (S3);
- writes of any kind (submit, resume, rebuild, restore);
- R2 media;
- any database access (ADR-2);
- any change under `src/`, `tests/`, `pyproject.toml` or `uv.lock`.

**Session ownership** (shared folder, no git repo yet): this work owns `web/`, `scripts/export_openapi.py` and a new `.github/workflows/web.yml` (approved). At the end it also ticks S3a in `docs/studio/04-roadmap.md` and `ROADMAP.md`, and adds one line about `web/` to `CLAUDE.md`.

## 2. Stack

| Concern | Choice |
|---|---|
| Framework | Next.js (App Router), TypeScript strict, npm, versions pinned exactly, `package-lock.json` committed |
| UI | Tailwind v4 + shadcn/ui components copied into `web/components/ui` (Card, Badge, Progress, Button, Input, Skeleton); dark by default, follows the system setting |
| Auth | Auth.js v5, GitHub provider, JWT sessions (no adapter, no database) |
| Data | hey-api (`@hey-api/openapi-ts`) generates types and zod schemas only (no client) from `web/openapi.json`; `lib/upstream.ts` uses `fetch` with those schemas; TanStack Query in client components |
| Tests | Vitest (unit), Playwright (smoke) |
| Hosting | Vercel Pro, project root `web/` |

Rejected alternatives: Mantine (a heavier runtime and awkward with React Server Components; S3 may revisit it) and server-component-only pages with `router.refresh()` polling (contradicts 08 §2 and doesn't fit S3's live pages).

## 3. Layout

As built (synced 2026-09-30):

```
scripts/export_openapi.py          writes web/openapi.json from clipforge.api.main.create_app; --check fails if stale
.github/workflows/web.yml          web CI (read-only; paths: web/**, the export script, src/clipforge/**, pyproject.toml, uv.lock)
web/
  package.json, package-lock.json, tsconfig.json, eslint.config.mjs, next.config.ts (build guards)
  openapi-ts.config.ts             hey-api: openapi.json -> lib/api/ (types + zod schemas only; no client or SDK)
  openapi.json                     committed export
  scripts/pin-versions.mjs         package.json ranges -> exact installed versions
  scripts/check-gen.mjs            `npm run gen:check`: lib/api matches openapi.json
  auth.ts                          Auth.js config (GitHub, JWT 7 days without use) + signIn allowlist
  proxy.ts                         session gate (Next 16's name for middleware.ts); bypass-aware
  lib/api/                         generated types + zod schemas; never edited by hand
  lib/upstream.ts                  server-only: readEnv, upstream calls (25 s timeout), error mapping
  lib/session.ts                   server-only: hasSession() for the /api/cf handlers (bypass-aware)
  lib/authMode.ts                  AUTH_DISABLED guard: local only, refused on every Vercel environment
  lib/mockGuard.ts                 MOCK_API guard: refused in Vercel production
  lib/owner.ts                     isOwner (primary + verified email) and fetchGitHubEmails
  lib/mocks.ts                     typed fixtures (PostingOverview, JobView)
  lib/fetchJson.ts                 browser -> /api/cf calls; ApiError; 401 -> /login
  lib/queries.ts                   TanStack hooks usePosting / useJob
  lib/polling.ts                   15 s Home, 5 s running job, none when finished
  lib/summaries.ts                 summarizePosting, summarizeJob, clipProgress ("3 of 6 done · 1 failed")
  lib/format.ts                    formatSlot, ago, formatUsd, formatTime, staleText
  lib/jobId.ts                     isJobId, normalizeJobInput, canonicalJobId, jobCreatedDay
  lib/statusBar.ts                 PostStatus counts -> ordered bar segments
  lib/recentJobs.ts                localStorage {id, openedAt} list (try/catch, max 10; reads old plain ids)
  lib/types.ts                     Posting, ChannelProgress, Job, Clip (zod output types)
  app/api/auth/[...nextauth]/route.ts
  app/api/cf/posting/route.ts
  app/api/cf/jobs/[id]/route.ts
  app/login/page.tsx
  app/(app)/layout.tsx             phone header + bottom tabs, laptop sidebar, QueryClientProvider, bypass banner
  app/(app)/page.tsx               Home
  app/(app)/jobs/page.tsx          lookup + recent
  app/(app)/jobs/[id]/page.tsx     job page (redirects uppercase ids to lowercase)
  app/(app)/more/page.tsx          the S3 pages, disabled
  components/ui/*                  shadcn (Base UI flavor)
  components/nav.ts, SidebarNav.tsx, BottomTabs.tsx, Providers.tsx, StaleNote.tsx, JobLookup.tsx, statusColors.ts
  components/home/*                HomeView, PostingCard, ChannelCard
  components/job/*                 JobDetail, ClipList, CostCard, RecentJobs
  tests/unit/*.test.ts             Vitest
  e2e/*.spec.ts, e2e/session.ts    Playwright (phone + desktop projects)
  e2e/print-cookie.mjs             prints a session cookie for manual local checks
  README.md
  .gitignore, .vercelignore        .env*.local never committed or uploaded
```

## 4. Auth

- **Login:** `/login` shows one "Sign in with GitHub" button.
- **Allowlist:** the `signIn` callback allows a login only when the GitHub account's primary, **verified** email (from the `/user/emails` API, scope `user:email`) equals `OWNER_EMAIL`, case-insensitively. The editable profile email isn't trusted. If `OWNER_EMAIL` is unset, every login is refused (fail closed).
- **Sessions:** JWT, signed with `AUTH_SECRET`, `maxAge` 7 days of inactivity (each request renews it). Rotating `AUTH_SECRET` logs everyone out.
- **Test bypass (owner decision, 2026-09-29):** `AUTH_DISABLED=1` treats every request as the owner (proxy, `/api/cf` handlers, login page) and shows a banner. **Local only:** the build and every request fail when `VERCEL` or `VERCEL_ENV` is set. Previews use `MOCK_API=1`; production uses GitHub login.
- **Proxy:** `proxy.ts` (Next 16's name for `middleware.ts`) redirects every path except `/login`, `/api/auth/*` and static assets to `/login` when there's no session.
- **Deep links (2026-09-30):** a signed-out page visit redirects to `/login?callbackUrl=<path+query>` (`/` goes to plain `/login`). The login page passes it to `signIn`'s `redirectTo` only when it's a relative path (starts with `/`, not `//`, no backslash or control characters, not `/login…`); anything else returns to Home (`lib/callback.ts`). `npm run dev` binds to 127.0.0.1.
- **Route handlers:** each `/api/cf/*` handler also calls `auth()` itself and returns `401 {"error":"unauthorized"}` without a session, so a proxy mistake can't expose the API.

## 5. Data flow

```
browser (TanStack Query) --GET--> /api/cf/*  (Vercel, session checked)
      --GET + Authorization: Bearer API_TOKEN--> CLIPFORGE_API_URL (Modal `web` endpoint)
```

- **Server-only upstream calls:** `lib/upstream.ts` imports `server-only`. It is the only module that reads `API_TOKEN` (through `readEnv`), and it calls the API with `fetch` and a 25 s timeout (raised from 10 s: `GET /posting` takes 6–7 s warm).
- **Allowed upstream calls:** `GET /posting` and `GET /jobs/{id}`. The job id is checked against `^\d{8}-[0-9a-f]{8}-[0-9a-f]{4}$` (same as `jobs.is_job_id`) before any request. An invalid id returns `404 {"error":"unknown job"}` without calling upstream.
- **Response validation:** successful upstream bodies are parsed with the generated zod schema before they're returned. A body that fails to parse counts as an upstream failure.
- **Error mapping:** the upstream body is never passed through, and the token and URL never appear in responses or logs. The server log records only the route and the upstream status.

  | Upstream | Handler returns |
  |---|---|
  | 200 + valid body | 200 + body |
  | 404 on `/jobs/{id}` | `404 {"error":"unknown job"}` |
  | 401, 403 (a wrong `API_TOKEN`, made visible on the phone) | `502 {"error":"API rejected the token"}` |
  | 5xx, other 4xx, timeout, network error, invalid body | `502 {"error":"API unavailable"}` |
  | `CLIPFORGE_API_URL` or `API_TOKEN` unset (and not mock) | `503 {"error":"API not configured"}` |

- **Download link:** the job's `download_url` is already a signed, expiring link made by the API (ADR-13). The page renders it as a plain link.

### Polling

| Page | Interval | Stops |
|---|---|---|
| Home | 15 s (`GET /posting` scans the whole Dict and keeps the Modal container warm) | while the tab is hidden |
| Job, status `queued` or `running` | 5 s | on `done`/`failed`, and while the tab is hidden |

`refetchIntervalInBackground: false` and `refetchOnWindowFocus: true`. If a refresh fails, the page keeps the last good data and shows "Couldn't refresh · last updated N s ago". With no data at all, it shows the error message and a retry button.

### Mock mode

- **Mock mode:** with `MOCK_API=1`, `lib/upstream.ts` returns the fixtures from `lib/mocks.ts`. There are two jobs: one running with mixed clip states, and one done with a download URL. Every other id is unknown.
- **Mock guard:** mock mode can't reach production. `next.config.ts` throws at build time when `VERCEL_ENV === "production"` and `MOCK_API` is set, and `readEnv` (through `lib/mockGuard.ts`) refuses mock mode at runtime under the same condition. Vercel's production environment never sets `MOCK_API`.

## 6. Pages (phone first; mockups approved 2026-09-29)

- **Home:**
  - A posting card: an on/paused pill (amber when paused, off when `enabled` is false), a red banner with `problem` when set, the next slot in the viewer's local time, the `per_day` rate, and three numbers: waiting, days left, and posted (the sum of `posted` counts across channels).
  - One card per channel: name, slug, episodes clipped/clipping/failed, a stacked status bar (posted, partly posted, sent, queued, skipped, rejected, unavailable, in that order, with fixed colors) and a legend showing only the non-zero counts.
  - A job-id box and "updated N s ago".
  - An empty state when there are no channels.
- **Job page:**
  - The status pill, job id, current stage and progress bar (`progress.pct`, `progress.message`), and "k of n clips done".
  - The clip list: each clip's status, its progress % while running, and its error stage when failed.
  - A cost card: total USD and a per-stage line. Clip stages are summed.
  - Created and updated times, and the download link when present.
  - A job error (stage and sanitized message) in a red card.
  - Visiting the page adds the id to the recent jobs.
- **Jobs tab:** a lookup box, which validates the id before navigating, and the recent jobs, newest first, max 10. localStorage access is wrapped in try/catch, so the page works without it.
- **More tab:** the placeholder list, each marked "coming in S3".
- **Bottom tab bar:** Home · Jobs · More. There's no navigation for placeholders beyond More.

## 6b. Phone and laptop (checkpoint G, approved 2026-09-30)

Every page works on phone and laptop ([08 §2](../../studio/08-dashboard-and-operations.md#2-dashboard-information-architecture-nextjs)). Every laptop style sits behind Tailwind's `lg:` breakpoint (≥ 1024 px), so the phone layout above is unchanged.

- **Navigation:** one list in `web/components/nav.ts`: Home, Jobs, Review, Calendar, Accounts, Sources, Produce, Costs. Only Home and Jobs are links; the others render disabled (`aria-disabled`, "coming in S3"). Phone: bottom tabs Home · Jobs · More, with the six S3 pages listed under More. Laptop: a fixed 224 px left sidebar (brand, nav, Sign out) replaces the header and the bottom tabs; content gets `max-w-6xl`.
- **Home (laptop):** the posting card and the channel cards share a 2-column grid (3 at ≥ 1280 px); the job lookup and the "updated…" line sit below. A posting `problem` banner spans the grid.
- **Job page (laptop):** two columns, `1fr | 20rem`. Left: the job header (status, stage, "k of n done · f failed", progress) and the clips as a table (Clip, Status, Progress, Error stage). Right: cost, created/updated times and the download link, and the "updated…" line.
- **Jobs tab (laptop):** the lookup box (max 32rem) above a Recent table: Job id (link), Created (from the id's `yyyymmdd`, no API call), Last opened. The recent list stores `{id, openedAt}` and still reads the old list of plain ids.
- **One element per list:** the clip and recent-job tables are single `<table>` elements that render as the phone list below 1024 px, so each clip's text exists once in the page.
- **Tests:** Playwright runs the same smoke specs in a `phone` (Pixel 7) and a `desktop` (1440×900) project, plus a layout spec (sidebar vs bottom tabs, S3 items disabled, Home grid, job table and side column, recent table).
- **S1's `accounts` field** on `GET /posting` is optional in the regenerated schema and not shown yet.

## 7. OpenAPI export

`scripts/export_openapi.py` builds `create_app(ApiContext(Settings(_env_file=None), deps=..., sender=...))` with stubs that are never called, and writes `app.openapi()` as sorted, indented JSON to `web/openapi.json`. It needs no Modal and no secrets. The docs routes stay disabled, since `app.openapi()` works with `openapi_url=None`. With `--check`, it exits 1 when the file differs. `npm run gen` runs hey-api against the committed file, and the build uses the committed generated types and schemas. If S1 has `api/main.py` mid-edit and the export breaks, wait and retry; don't patch it.

## 8. Testing and CI

- **Vitest:**
  - the allowlist (verified primary match, unverified email refused, case, unset `OWNER_EMAIL`);
  - the upstream error mapping (every row of the table in §5, and that no upstream text leaks);
  - the job-id check;
  - the mock guard;
  - status-bar segments;
  - the recent-jobs list (dedupe, cap, broken storage).
- **Playwright** (against `next build && next start` with `MOCK_API=1` and a test `AUTH_SECRET`):
  1. Without a session, `/` redirects to `/login`, which shows the GitHub button.
  2. Without a session, `/api/cf/posting` returns 401.
  3. With a session cookie minted in the test via `next-auth/jwt` `encode` (no test-only login code in the app), Home shows the mock channels and the status legend.
  4. With a session, the running mock job's page shows its clips and a bad id shows "unknown job".

  It runs at a phone viewport (Pixel 7).
- **`web.yml`:**
  - `uv run python scripts/export_openapi.py --check`;
  - `uv run ruff check scripts/`;
  - `npm ci`, lint, typecheck, `vitest run`, `next build`;
  - the Playwright smoke.

  It runs on pushes and PRs that touch `web/**` or the script. It never deploys; Vercel's Git integration does, once the repo exists.
- **Local checks:** the same commands, listed in `web/README.md`.

## 9. Configuration and deploy

| Variable | Where | Notes |
|---|---|---|
| `CLIPFORGE_API_URL` | Vercel (all envs), `.env.local` | today's public `web` endpoint |
| `API_TOKEN` | Vercel (server), `.env.local` | same value as in `clipforge-secrets` |
| `AUTH_SECRET` | Vercel, `.env.local` | `npx auth secret` |
| `AUTH_GITHUB_ID`, `AUTH_GITHUB_SECRET` | Vercel, `.env.local` | GitHub OAuth app; callback `https://<domain>/api/auth/callback/github` (the owner creates a second OAuth app for `http://localhost:3000`, used in `.env.local`, so the first real login happens locally) |
| `OWNER_EMAIL` | Vercel, `.env.local` | the owner's verified GitHub email |
| `MOCK_API` | `.env.local`, CI only | never in Vercel production (enforced at build time) |

No variable is `NEXT_PUBLIC_*`. The rollout is a Vercel preview first; production only after the owner's OK.

**What a preview proves (owner decision, 2026-09-30):** a Vercel preview runs on `MOCK_API=1` and has a random URL, while a GitHub OAuth app has one callback URL, so **no login is possible on a preview**. A preview only proves that the build works and that pages redirect to `/login` (and `/api/cf/*` answers 401). The real checks are the local run (owner runbook 11 §5a: `AUTH_DISABLED=1` or the local OAuth app, against the deployed API) and production. Until S0 deploys `GET /posting`, the deployed Home shows "API unavailable" (a 404 upstream on `/posting` maps to 502).

**Owner actions:** confirm Vercel Pro, create the GitHub OAuth app, give the allowlist email, and set the Vercel env vars.

## 10. Later (S3)

- **Logins on previews (not planned):** Auth.js's `AUTH_REDIRECT_PROXY_URL` could route preview logins through the production domain. Kept as an option; previews stay login-less for now.

The pages are defined in [08 §2](../../studio/08-dashboard-and-operations.md#2-dashboard-information-architecture-nextjs); S3 builds them over S1's routes once they're deployed. For this shell that means:

- **Sources page** (new nav item already in place): every source with its permission record (type, granted when and by whom, evidence link, platforms, monetization, translation, expiry, restrictions), campaign terms, an expiry warning, the change history, and add/edit/pause/end. The database is the only copy since S1 (decision log #58–60), so this page replaces `clipforge source` for day-to-day edits.
- **Home:** a banner for any source permission expiring within 14 days, and per-account posting progress from `GET /posting`'s `accounts` field.
- **Accounts page:** each account's category (`clips`, `story`, `band`, `avatar`, `model`) and its sources.
- **Produce:** submit a job by picking a source, so credit and permission come with it.

- Point the handlers at the `admin` endpoint and add Modal proxy-auth headers.
- Add routes for accounts, items, posts and costs, and replace the localStorage recent list with a jobs list from S1's `jobs` table.
- Regenerate the client in CI from the export.
