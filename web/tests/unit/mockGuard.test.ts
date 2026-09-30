import { describe, expect, test } from "vitest";
import { assertMockAllowed, isMock } from "@/lib/mockGuard";

describe("mock guard", () => {
  test("mock mode only for MOCK_API=1", () => {
    expect(isMock({ MOCK_API: "1" })).toBe(true);
    expect(isMock({})).toBe(false);
    expect(isMock({ MOCK_API: "" })).toBe(false);
    expect(isMock({ MOCK_API: "true" })).toBe(false);
  });

  test("production with any MOCK_API value is refused", () => {
    for (const value of ["1", "0", "true"]) {
      expect(() => assertMockAllowed({ VERCEL_ENV: "production", MOCK_API: value })).toThrow(
        "MOCK_API must not be set in Vercel production",
      );
      expect(() => isMock({ VERCEL_ENV: "production", MOCK_API: value })).toThrow();
    }
  });

  test("production without MOCK_API, and previews with it, are allowed", () => {
    expect(() => assertMockAllowed({ VERCEL_ENV: "production" })).not.toThrow();
    expect(() => assertMockAllowed({ VERCEL_ENV: "production", MOCK_API: "" })).not.toThrow();
    expect(isMock({ VERCEL_ENV: "preview", MOCK_API: "1" })).toBe(true);
  });
});
