// Mock mode serves fixtures instead of the API (local dev and CI). It must never reach production:
// next.config.ts calls assertMockAllowed at build time, and upstream.ts calls isMock at runtime.
type Env = Record<string, string | undefined>;

export function assertMockAllowed(env: Env): void {
  if (env.VERCEL_ENV === "production" && env.MOCK_API) {
    throw new Error("MOCK_API must not be set in Vercel production");
  }
}

export function isMock(env: Env): boolean {
  assertMockAllowed(env);
  return env.MOCK_API === "1";
}
