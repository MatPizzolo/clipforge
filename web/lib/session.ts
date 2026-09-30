import "server-only";

import { auth } from "@/auth";
import { isAuthBypassed } from "@/lib/authMode";

// The session check every /api/cf handler runs. With AUTH_DISABLED=1 (local only; refused on
// every Vercel environment) it admits every request without asking Auth.js.
export async function hasSession(): Promise<boolean> {
  if (isAuthBypassed(process.env)) return true;
  return Boolean(await auth());
}
