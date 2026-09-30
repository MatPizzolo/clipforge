// AUTH_DISABLED=1 turns the GitHub login off for local testing: every request is treated as the
// owner. Local only (owner decision): never on Vercel, where previews use MOCK_API=1 and production
// uses GitHub login. next.config.ts calls assertAuthBypassAllowed at build time, and every session
// check calls isAuthBypassed at runtime. Vercel sets VERCEL=1 and VERCEL_ENV on builds and functions.
type Env = Record<string, string | undefined>;

export function assertAuthBypassAllowed(env: Env): void {
  if ((env.VERCEL || env.VERCEL_ENV) && env.AUTH_DISABLED) {
    throw new Error("AUTH_DISABLED is for local testing only and must not be set on Vercel");
  }
}

export function isAuthBypassed(env: Env): boolean {
  assertAuthBypassAllowed(env);
  return env.AUTH_DISABLED === "1";
}
