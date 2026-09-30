import { encode } from "next-auth/jwt";

// Test-only signing secret: the app accepts this cookie only because Playwright starts it with the same AUTH_SECRET.
export const E2E_SECRET = "e2e-only-auth-secret-0123456789abcdef";
export const COOKIE = "authjs.session-token"; // http (no __Secure- prefix)

export async function sessionCookie(host = "127.0.0.1") {
  const value = await encode({
    token: { name: "Owner", email: "owner@example.com", sub: "1" },
    secret: E2E_SECRET,
    salt: COOKIE,
  });
  return { name: COOKIE, value, domain: host, path: "/", httpOnly: true, sameSite: "Lax" as const };
}
