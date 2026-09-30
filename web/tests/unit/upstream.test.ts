import { describe, expect, test, vi } from "vitest";
import { MOCK_POSTING, MOCK_RUNNING_JOB_ID } from "@/lib/mocks";
import { getJob, getPosting, readEnv, toResponse, UPSTREAM_TIMEOUT_MS, type UpstreamEnv } from "@/lib/upstream";

const env: UpstreamEnv = { apiUrl: "https://api.example.test", apiToken: "tok-secret", mock: false };
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

describe("getPosting", () => {
  test("calls /posting with the bearer token and returns validated data", async () => {
    const fetchImpl = vi.fn(async () => json(MOCK_POSTING));
    const result = await getPosting(env, fetchImpl);
    expect(result).toEqual({ ok: true, data: MOCK_POSTING });
    const [url, init] = fetchImpl.mock.calls[0] as unknown as [URL, RequestInit];
    expect(String(url)).toBe("https://api.example.test/posting");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer tok-secret");
  });

  test("a trailing slash on the base URL is fine", async () => {
    const fetchImpl = vi.fn(async () => json(MOCK_POSTING));
    await getPosting({ ...env, apiUrl: "https://api.example.test/" }, fetchImpl);
    expect(String((fetchImpl.mock.calls[0] as unknown as [URL])[0])).toBe("https://api.example.test/posting");
  });

  test.each([
    ["401", () => json({ detail: "invalid or missing bearer token" }, 401)],
    ["403", () => new Response("Forbidden: tok-secret", { status: 403 })],
  ])("%s → 502 API rejected the token, no upstream text", async (_name, make) => {
    const result = await getPosting(env, vi.fn(async () => make()));
    expect(result).toEqual({ ok: false, status: 502, error: "API rejected the token" });
    expect(JSON.stringify(result)).not.toContain("tok-secret");
  });

  test.each([
    ["404 (not deployed yet)", () => json({ detail: "Not Found" }, 404)],
    ["500", () => new Response("Traceback: secret stuff", { status: 500 })],
    ["200 html", () => new Response("<html>modal error</html>", { status: 200 })],
    ["200 wrong shape", () => json({ channels: "nope" })],
  ])("%s → 502 API unavailable, no upstream text", async (_name, make) => {
    const result = await getPosting(env, vi.fn(async () => make()));
    expect(result).toEqual({ ok: false, status: 502, error: "API unavailable" });
  });

  test("network error and timeout → 502", async () => {
    const boom = vi.fn(async () => { throw new TypeError("fetch failed"); });
    expect(await getPosting(env, boom)).toEqual({ ok: false, status: 502, error: "API unavailable" });
    const timeout = vi.fn(async () => { throw new DOMException("timed out", "TimeoutError"); });
    expect(await getPosting(env, timeout)).toEqual({ ok: false, status: 502, error: "API unavailable" });
  });

  test("missing config → 503 without calling out", async () => {
    const fetchImpl = vi.fn();
    expect(await getPosting({ mock: false }, fetchImpl)).toEqual({ ok: false, status: 503, error: "API not configured" });
    expect(await getPosting({ ...env, apiToken: undefined }, fetchImpl)).toMatchObject({ status: 503 });
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  test("mock mode serves the fixture without calling out", async () => {
    const fetchImpl = vi.fn();
    expect(await getPosting({ mock: true }, fetchImpl)).toEqual({ ok: true, data: MOCK_POSTING });
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  test("logs carry route and status only", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    await getPosting(env, vi.fn(async () => new Response("Traceback tok-secret", { status: 500 })));
    const logged = warn.mock.calls.flat().join(" ");
    expect(logged).toContain("/posting");
    expect(logged).toContain("500");
    expect(logged).not.toContain("tok-secret");
    expect(logged).not.toContain("api.example.test");
    expect(logged).not.toContain("Traceback");
    warn.mockRestore();
  });
});

describe("getJob", () => {
  test("bad ids are 404 without an upstream call (Review Focus 2)", async () => {
    const fetchImpl = vi.fn();
    for (const bad of ["../posting", "%2e%2e", "20260929-3FA9C1D2-4B7E", ""]) {
      expect(await getJob(bad, env, fetchImpl)).toEqual({ ok: false, status: 404, error: "unknown job" });
    }
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  test("upstream 404 → unknown job; 401 → rejected token; 500 → API unavailable", async () => {
    expect(await getJob(MOCK_RUNNING_JOB_ID, env, vi.fn(async () => json({ detail: "unknown job" }, 404))))
      .toEqual({ ok: false, status: 404, error: "unknown job" });
    expect(await getJob(MOCK_RUNNING_JOB_ID, env, vi.fn(async () => json({ detail: "x" }, 401))))
      .toEqual({ ok: false, status: 502, error: "API rejected the token" });
    expect(await getJob(MOCK_RUNNING_JOB_ID, env, vi.fn(async () => json({}, 500))))
      .toEqual({ ok: false, status: 502, error: "API unavailable" });
  });

  test("calls /jobs/<id>", async () => {
    const { mockJob } = await import("@/lib/mocks");
    const fetchImpl = vi.fn(async () => json(mockJob(MOCK_RUNNING_JOB_ID)));
    const result = await getJob(MOCK_RUNNING_JOB_ID, env, fetchImpl);
    expect(result.ok).toBe(true);
    expect(String((fetchImpl.mock.calls[0] as unknown as [URL])[0])).toBe(`https://api.example.test/jobs/${MOCK_RUNNING_JOB_ID}`);
  });

  test("mock mode: known and unknown ids", async () => {
    expect((await getJob(MOCK_RUNNING_JOB_ID, { mock: true })).ok).toBe(true);
    expect(await getJob("20260929-00000000-0000", { mock: true })).toMatchObject({ status: 404 });
  });
});

test("readEnv", () => {
  expect(readEnv({ CLIPFORGE_API_URL: "https://a", API_TOKEN: "t" })).toEqual({ apiUrl: "https://a", apiToken: "t", mock: false });
  expect(readEnv({ MOCK_API: "1" }).mock).toBe(true);
  expect(() => readEnv({ MOCK_API: "1", VERCEL_ENV: "production" })).toThrow();
});

test("toResponse", async () => {
  const ok = toResponse({ ok: true, data: { a: 1 } });
  expect(ok.status).toBe(200);
  expect(ok.headers.get("cache-control")).toBe("no-store");
  expect(await ok.json()).toEqual({ a: 1 });
  const bad = toResponse({ ok: false, status: 502, error: "API unavailable" });
  expect(bad.status).toBe(502);
  expect(await bad.json()).toEqual({ error: "API unavailable" });
});

test("the timeout leaves room for a cold start plus the Dict scan behind GET /posting (6–7 s warm)", async () => {
  expect(UPSTREAM_TIMEOUT_MS).toBe(25_000);
  const fetchImpl = vi.fn(async () => json(MOCK_POSTING));
  await getPosting(env, fetchImpl);
  const [, init] = fetchImpl.mock.calls[0] as unknown as [URL, RequestInit];
  expect(init.signal).toBeInstanceOf(AbortSignal);
});

test("GET /posting with S1's additive `accounts` list parses (and is kept)", async () => {
  const body = {
    ...MOCK_POSTING,
    accounts: [
      { account_id: "realtalk-clips-en", enabled: true, paused: false, waiting: 29, per_day: 6, days_left: 5, held: 1,
        next_slot: "2026-10-01T06:00:00-03:00", channels: MOCK_POSTING.channels },
      { account_id: "founder-tapes-en", enabled: false, paused: false },
    ],
  };
  const result = await getPosting(env, vi.fn(async () => json(body)));
  expect(result.ok).toBe(true);
  if (result.ok) {
    expect(result.data.accounts).toHaveLength(2);
    expect(result.data.accounts?.[1]).toMatchObject({ account_id: "founder-tapes-en", waiting: 0, held: 0 });
  }
});
