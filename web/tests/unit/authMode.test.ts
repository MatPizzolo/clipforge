import { expect, test } from "vitest";
import { assertAuthBypassAllowed, isAuthBypassed } from "@/lib/authMode";

const REFUSED = "AUTH_DISABLED is for local testing only and must not be set on Vercel";

test("auth is bypassed only for AUTH_DISABLED=1", () => {
  expect(isAuthBypassed({ AUTH_DISABLED: "1" })).toBe(true);
  expect(isAuthBypassed({})).toBe(false);
  expect(isAuthBypassed({ AUTH_DISABLED: "" })).toBe(false);
  expect(isAuthBypassed({ AUTH_DISABLED: "true" })).toBe(false);
});

test("any Vercel environment (production, preview, development) refuses it", () => {
  for (const vercelEnv of ["production", "preview", "development"]) {
    for (const value of ["1", "0", "true"]) {
      expect(() => assertAuthBypassAllowed({ VERCEL_ENV: vercelEnv, AUTH_DISABLED: value })).toThrow(REFUSED);
      expect(() => isAuthBypassed({ VERCEL_ENV: vercelEnv, AUTH_DISABLED: value })).toThrow(REFUSED);
    }
  }
  // Vercel sets VERCEL=1 at build time too.
  expect(() => assertAuthBypassAllowed({ VERCEL: "1", AUTH_DISABLED: "1" })).toThrow(REFUSED);
});

test("on Vercel without the flag, and locally with it, all is fine", () => {
  expect(() => assertAuthBypassAllowed({ VERCEL: "1", VERCEL_ENV: "production" })).not.toThrow();
  expect(isAuthBypassed({ AUTH_DISABLED: "1" })).toBe(true);
});
