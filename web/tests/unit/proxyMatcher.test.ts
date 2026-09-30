import { expect, test, vi } from "vitest";

// proxy.ts wraps Auth.js; only its static `config` is under test here.
vi.mock("@/auth", () => ({ auth: (fn: unknown) => fn }));
const { config } = await import("@/proxy");

// Next compiles the matcher with path-to-regexp; the pattern is a plain regex group, so an
// anchored RegExp matches the same paths. "gated" = the proxy runs on that path.
const gated = (path: string) => config.matcher.some((m: string) => new RegExp(`^${m}$`).test(path));

test("pages, API routes and look-alike paths are gated", () => {
  for (const path of ["/", "/jobs", "/jobs/20260929-3fa9c1d2-4b7e", "/api/cf/posting", "/loginx", "/login/x", "/api/authx", "/api/auth-x", "/favicon.icox", "/icon.svg"]) {
    expect(gated(path), path).toBe(true);
  }
});

test("login, Auth.js routes and static assets are not", () => {
  for (const path of ["/login", "/api/auth", "/api/auth/callback/github", "/api/auth/session", "/_next/static/chunks/a.js", "/_next/image", "/favicon.ico"]) {
    expect(gated(path), path).toBe(false);
  }
});
