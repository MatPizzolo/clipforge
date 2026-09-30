import "server-only";

import type { z } from "zod";
import { zJobView, zPostingOverview } from "@/lib/api/zod.gen";
import { isJobId } from "@/lib/jobId";
import { isMock } from "@/lib/mockGuard";
import { MOCK_POSTING, mockJob } from "@/lib/mocks";
import type { Job, Posting } from "@/lib/types";

// The only module that reads API_TOKEN. Handlers return its result as-is; upstream bodies,
// the URL and the token never reach a response or a log line (spec §5).

export type UpstreamResult<T> = { ok: true; data: T } | { ok: false; status: 404 | 502 | 503; error: string };
export type UpstreamEnv = { apiUrl?: string; apiToken?: string; mock: boolean };

// GET /posting scans the whole Dict: 6–7 s warm (measured 2026-09-29), more on a cold start.
export const UPSTREAM_TIMEOUT_MS = 25_000;
const UNAVAILABLE = { ok: false, status: 502, error: "API unavailable" } as const;
const REJECTED = { ok: false, status: 502, error: "API rejected the token" } as const; // wrong API_TOKEN
const NOT_CONFIGURED = { ok: false, status: 503, error: "API not configured" } as const;
const UNKNOWN_JOB = { ok: false, status: 404, error: "unknown job" } as const;

export function readEnv(env: Record<string, string | undefined> = process.env): UpstreamEnv {
  return { apiUrl: env.CLIPFORGE_API_URL || undefined, apiToken: env.API_TOKEN || undefined, mock: isMock(env) };
}

async function call<S extends z.ZodType>(
  route: string, // for logs: "/posting" or "/jobs/{id}"
  path: string,
  schema: S,
  env: UpstreamEnv,
  fetchImpl: typeof fetch,
  onNotFound: UpstreamResult<z.output<S>> = UNAVAILABLE,
): Promise<UpstreamResult<z.output<S>>> {
  if (!env.apiUrl || !env.apiToken) return NOT_CONFIGURED;
  const base = env.apiUrl.endsWith("/") ? env.apiUrl : `${env.apiUrl}/`;
  let res: Response;
  try {
    res = await fetchImpl(new URL(path, base), {
      headers: { Authorization: `Bearer ${env.apiToken}`, Accept: "application/json" },
      cache: "no-store",
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    });
  } catch {
    console.warn(`upstream ${route}: network error or timeout`);
    return UNAVAILABLE;
  }
  if (res.status === 404) {
    console.warn(`upstream ${route}: status 404`);
    return onNotFound;
  }
  if (res.status === 401 || res.status === 403) {
    console.warn(`upstream ${route}: status ${res.status}, token rejected`);
    return REJECTED;
  }
  if (!res.ok) {
    console.warn(`upstream ${route}: status ${res.status}`);
    return UNAVAILABLE;
  }
  let body: unknown;
  try {
    body = await res.json();
  } catch {
    console.warn(`upstream ${route}: status ${res.status}, body is not JSON`);
    return UNAVAILABLE;
  }
  const parsed = schema.safeParse(body);
  if (!parsed.success) {
    console.warn(`upstream ${route}: status ${res.status}, body does not match the contract`);
    return UNAVAILABLE;
  }
  return { ok: true, data: parsed.data };
}

export async function getPosting(env: UpstreamEnv = readEnv(), fetchImpl: typeof fetch = fetch): Promise<UpstreamResult<Posting>> {
  if (env.mock) return { ok: true, data: MOCK_POSTING };
  return call("/posting", "posting", zPostingOverview, env, fetchImpl);
}

export async function getJob(id: string, env: UpstreamEnv = readEnv(), fetchImpl: typeof fetch = fetch): Promise<UpstreamResult<Job>> {
  if (!isJobId(id)) return UNKNOWN_JOB;
  if (env.mock) {
    const job = mockJob(id);
    return job ? { ok: true, data: job } : UNKNOWN_JOB;
  }
  return call("/jobs/{id}", `jobs/${id}`, zJobView, env, fetchImpl, UNKNOWN_JOB);
}

export function toResponse<T>(result: UpstreamResult<T>): Response {
  const headers = { "Cache-Control": "no-store" };
  return result.ok
    ? Response.json(result.data, { headers })
    : Response.json({ error: result.error }, { status: result.status, headers });
}
