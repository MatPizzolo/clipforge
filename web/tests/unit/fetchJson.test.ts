import { afterEach, expect, test, vi } from "vitest";
import { ApiError, fetchJson } from "@/lib/fetchJson";

afterEach(() => vi.unstubAllGlobals());

test("returns the body on 200", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => Response.json({ a: 1 })));
  expect(await fetchJson("/api/cf/posting")).toEqual({ a: 1 });
});

test("errors carry the status and the short message", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => Response.json({ error: "unknown job" }, { status: 404 })));
  await expect(fetchJson("/api/cf/jobs/x")).rejects.toMatchObject({ status: 404, message: "unknown job" });
  vi.stubGlobal("fetch", vi.fn(async () => new Response("<html>", { status: 500 })));
  const err = await fetchJson("/x").catch((e: unknown) => e);
  expect(err).toBeInstanceOf(ApiError);
  expect(err).toMatchObject({ status: 500, message: "request failed" });
});

test("401 sends the browser to /login", async () => {
  const assign = vi.fn();
  vi.stubGlobal("window", { location: { assign } });
  vi.stubGlobal("fetch", vi.fn(async () => Response.json({ error: "unauthorized" }, { status: 401 })));
  await expect(fetchJson("/x")).rejects.toMatchObject({ status: 401 });
  expect(assign).toHaveBeenCalledWith("/login");
});
