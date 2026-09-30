import { expect, test } from "vitest";
import { loginPathFor, safeCallback } from "@/lib/callback";

test("the proxy sends deep links to /login with the path and query", () => {
  expect(loginPathFor("/jobs/20260929-3fa9c1d2-4b7e", "")).toBe("/login?callbackUrl=%2Fjobs%2F20260929-3fa9c1d2-4b7e");
  expect(loginPathFor("/jobs", "?x=1&y=2")).toBe("/login?callbackUrl=%2Fjobs%3Fx%3D1%26y%3D2");
  expect(loginPathFor("/", "")).toBe("/login"); // Home is the default anyway
});

test("login accepts only relative paths", () => {
  expect(safeCallback("/jobs/20260929-3fa9c1d2-4b7e")).toBe("/jobs/20260929-3fa9c1d2-4b7e");
  expect(safeCallback("/jobs?x=1")).toBe("/jobs?x=1");
  for (const bad of [
    undefined, null, "", "jobs", "https://evil.example/x", "//evil.example/x", "/\\evil.example",
    "/login", "/login?callbackUrl=/x", "/login/x", "javascript:alert(1)", "/jobs\nx", " /jobs",
  ]) {
    expect(safeCallback(bad), String(bad)).toBe("/");
  }
  // a repeated query parameter arrives as an array
  expect(safeCallback(["/jobs", "/x"])).toBe("/");
});
