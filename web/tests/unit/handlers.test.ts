import { afterEach, beforeEach, expect, test, vi } from "vitest";

const auth = vi.fn();
const getPosting = vi.fn();
const getJob = vi.fn();
vi.mock("@/auth", () => ({ auth: () => auth() }));
vi.mock("@/lib/upstream", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/upstream")>();
  return { ...real, getPosting: () => getPosting(), getJob: (id: string) => getJob(id) };
});

const { GET: postingGET } = await import("@/app/api/cf/posting/route");
const { GET: jobGET } = await import("@/app/api/cf/jobs/[id]/route");
const params = (id: string) => ({ params: Promise.resolve({ id }) });

beforeEach(() => {
  auth.mockReset();
  getPosting.mockReset();
  getJob.mockReset();
});

afterEach(() => vi.unstubAllEnvs());

test("no session → 401 and no upstream call", async () => {
  auth.mockResolvedValue(null);
  const r1 = await postingGET();
  expect(r1.status).toBe(401);
  expect(await r1.json()).toEqual({ error: "unauthorized" });
  const r2 = await jobGET(new Request("http://x"), params("20260929-3fa9c1d2-4b7e"));
  expect(r2.status).toBe(401);
  expect(getPosting).not.toHaveBeenCalled();
  expect(getJob).not.toHaveBeenCalled();
});

test("with a session the upstream result is returned", async () => {
  auth.mockResolvedValue({ user: { email: "owner@x.com" } });
  getPosting.mockResolvedValue({ ok: false, status: 502, error: "API unavailable" });
  const r = await postingGET();
  expect(r.status).toBe(502);
  expect(await r.json()).toEqual({ error: "API unavailable" });

  getJob.mockResolvedValue({ ok: true, data: { job_id: "20260929-3fa9c1d2-4b7e" } });
  const j = await jobGET(new Request("http://x"), params("20260929-3fa9c1d2-4b7e"));
  expect(j.status).toBe(200);
  expect(getJob).toHaveBeenCalledWith("20260929-3fa9c1d2-4b7e");
});

test("AUTH_DISABLED=1 skips the session check (local only)", async () => {
  vi.stubEnv("AUTH_DISABLED", "1");
  auth.mockResolvedValue(null);
  getPosting.mockResolvedValue({ ok: true, data: { channels: [] } });
  const r = await postingGET();
  expect(r.status).toBe(200);
  expect(auth).not.toHaveBeenCalled();
});

test("AUTH_DISABLED on Vercel (even a preview) fails closed", async () => {
  vi.stubEnv("AUTH_DISABLED", "1");
  vi.stubEnv("VERCEL_ENV", "preview");
  auth.mockResolvedValue({ user: { email: "owner@x.com" } });
  await expect(postingGET()).rejects.toThrow("AUTH_DISABLED is for local testing only");
  expect(getPosting).not.toHaveBeenCalled();
});
