# ClipForge dashboard (`web/`)

Owner-only Next.js dashboard over the ClipForge job API (Studio S3a; ADR-2, ADR-38).
Pages: Home (posting progress per channel, `GET /posting`), Jobs (lookup and recent) and a job page
(`GET /jobs/{id}`). Everything else is a placeholder until S3.

How it works: the browser only talks to this app's `/api/cf/*` route handlers. They check the
Auth.js session, call the deployed API with the bearer token on the server, validate the response
against the exported OpenAPI contract, and return the data or a short error. The token never
reaches the browser.

| Error on the phone | Meaning |
|---|---|
| `API rejected the token` | The API answered 401/403: `API_TOKEN` here doesn't match `clipforge-secrets` |
| `API unavailable` | Timeout (25 s), 5xx, a missing route (e.g. `/posting` before it's deployed) or a response that doesn't match the contract |
| `API not configured` | `CLIPFORGE_API_URL` or `API_TOKEN` is unset |
| `unknown job` | No such job id |

## Environment

| Variable | Where | What |
|---|---|---|
| `CLIPFORGE_API_URL` | Vercel, `.env.local` | Deployed job API (the Modal `web` endpoint URL) |
| `API_TOKEN` | Vercel, `.env.local` | Bearer token, same value as `API_TOKEN` in `clipforge-secrets` |
| `AUTH_SECRET` | Vercel, `.env.local` | Session signing key: `npx auth secret`. A session ends after 7 days **without use** (each request renews it); **rotating the secret logs everyone out.** |
| `AUTH_GITHUB_ID`, `AUTH_GITHUB_SECRET` | Vercel, `.env.local` | GitHub OAuth app. Vercel: the production app (callback `https://<domain>/api/auth/callback/github`). Local: a second app (see below). |
| `OWNER_EMAIL` | Vercel, `.env.local` | The one allowed GitHub account's primary, verified email |
| `MOCK_API` | `.env.local`, CI, Vercel preview | `1` serves fixtures instead of the API. Previews always use it. The build fails if it's set in Vercel production. |
| `AUTH_DISABLED` | `.env.local` only | `1` turns the GitHub login off for **local** testing: every request counts as the owner and a banner says so. **Never on Vercel:** previews use `MOCK_API=1`, production uses GitHub login. The build and every request fail if it's set on any Vercel environment. |

Nothing is `NEXT_PUBLIC_*`. `.env.local` is gitignored; start from `.env.example`.

## Local development

```bash
cd web
npm ci
cp .env.example .env.local        # MOCK_API=1 works without the API
npm run dev                        # http://localhost:3000 (bound to 127.0.0.1 only: with AUTH_DISABLED
                                   # and a real token, nothing else on the network can reach it)
```

To test locally without any OAuth app, set `AUTH_DISABLED=1` in `.env.local` (local only; see the table).

GitHub login locally uses a second OAuth app (Homepage `http://localhost:3000`, callback
`http://localhost:3000/api/auth/callback/github`); put its id and secret in `.env.local`. Without it,
sign in with a minted cookie: run `AUTH_SECRET=<the value in .env.local> node e2e/print-cookie.mjs`
and add the printed value as the `authjs.session-token` cookie for `localhost` in the browser's
dev tools.

## Checks

```bash
npm run check                      # lint, typecheck (next typegen + tsc), unit tests, build
npm run gen:check                  # lib/api matches openapi.json
npm run e2e                        # builds, starts with MOCK_API=1, runs the Playwright smoke (Pixel 7)
uv run python scripts/export_openapi.py --check   # from the repo root: contract file is fresh
```

CI runs the same (`.github/workflows/web.yml`) on changes to `web/`, the export script or the API.

## API contract

`openapi.json` is exported from the FastAPI app (`scripts/export_openapi.py`, no Modal needed), and
`npm run gen` regenerates `lib/api/` (types and zod schemas; never edit by hand). Posting times carry
the posting timezone's offset, so the zod plugin accepts offsets (`openapi-ts.config.ts`). After an
API change:

```bash
uv run python scripts/export_openapi.py && (cd web && npm run gen)
```

## Deploy (Vercel Pro)

The project is linked from this folder (`vercel link` inside `web/`). Until the git repo exists,
deploy with the CLI:

```bash
cd web
vercel deploy            # preview
vercel deploy --prod     # production (after checking the preview)
```

Rules: production uses GitHub login and never `MOCK_API`; previews use `MOCK_API=1`;
`AUTH_DISABLED` is never set on Vercel (it's refused there). `.vercelignore` keeps `.env.local` out
of every upload.

| Variable | Production | Preview |
|---|---|---|
| `CLIPFORGE_API_URL`, `API_TOKEN` | yes | no (mock data) |
| `AUTH_SECRET` | yes | yes (a different value is fine) |
| `AUTH_GITHUB_ID`, `AUTH_GITHUB_SECRET` | yes (the production OAuth app) | no (GitHub login can't work on random preview URLs) |
| `OWNER_EMAIL` | yes | no |
| `MOCK_API` | never | `1` (set) |

Add a value interactively (it isn't echoed or saved in shell history):
```bash
vercel env add API_TOKEN production
vercel env add AUTH_SECRET preview ""     # the "" means all preview branches (the CLI insists)
``` Once the repo is on GitHub, connect it in Vercel with Root Directory `web`.

**What a preview proves:** it runs on mock data and has a random URL, and a GitHub OAuth app has one
callback URL, so **no login is possible on a preview**. It only proves the build works and that pages
redirect to `/login` (and `/api/cf/*` answers 401). The real checks are local (run it with
`AUTH_DISABLED=1` or the local OAuth app against the deployed API; owner runbook 11 §5a) and
production.

Polling: Home every 15 s, a running job every 5 s, nothing while the tab is hidden (each request
wakes the Modal container).
