import { expect, test, vi } from "vitest";
import { fetchGitHubEmails, isOwner } from "@/lib/owner";

const e = (email: string, primary: boolean, verified: boolean) => ({ email, primary, verified });

test("only the primary, verified email counts (Review Focus 5)", () => {
  expect(isOwner([e("owner@x.com", true, true)], "owner@x.com")).toBe(true);
  expect(isOwner([e("owner@x.com", true, false)], "owner@x.com")).toBe(false);
  expect(isOwner([e("owner@x.com", false, true), e("other@x.com", true, true)], "owner@x.com")).toBe(false);
});

test("case and whitespace don't matter", () => {
  expect(isOwner([e("Owner@X.com", true, true)], "  owner@x.COM ")).toBe(true);
});

test("unset or empty OWNER_EMAIL refuses everyone", () => {
  expect(isOwner([e("owner@x.com", true, true)], undefined)).toBe(false);
  expect(isOwner([e("owner@x.com", true, true)], "  ")).toBe(false);
  expect(isOwner([], "owner@x.com")).toBe(false);
});

test("fetchGitHubEmails: token header, bad responses give []", async () => {
  const ok = vi.fn(async () => Response.json([{ email: "a@b.c", primary: true, verified: true, visibility: null }]));
  expect(await fetchGitHubEmails("gho_x", ok)).toEqual([{ email: "a@b.c", primary: true, verified: true }]);
  const [, init] = ok.mock.calls[0] as unknown as [string, RequestInit];
  expect((init.headers as Record<string, string>).Authorization).toBe("Bearer gho_x");
  expect(await fetchGitHubEmails("t", vi.fn(async () => new Response("no", { status: 401 })))).toEqual([]);
  expect(await fetchGitHubEmails("t", vi.fn(async () => Response.json({ message: "x" })))).toEqual([]);
  expect(await fetchGitHubEmails("t", vi.fn(async () => { throw new TypeError("fetch failed"); }))).toEqual([]);
});
