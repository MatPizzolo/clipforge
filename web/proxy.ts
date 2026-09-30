import { NextResponse } from "next/server";
import { auth } from "@/auth";
import { isAuthBypassed } from "@/lib/authMode";
import { loginPathFor } from "@/lib/callback";

// First gate: no session → /login?callbackUrl=<path> (pages) or 401 (API). The /api/cf handlers
// check again.
// AUTH_DISABLED=1 lets everything through: local only, refused on every Vercel environment.
const gate = auth((req) => {
  if (req.auth) return;
  if (req.nextUrl.pathname.startsWith("/api/")) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  return NextResponse.redirect(new URL(loginPathFor(req.nextUrl.pathname, req.nextUrl.search), req.nextUrl));
});

export const proxy: typeof gate = (...args) => (isAuthBypassed(process.env) ? NextResponse.next() : gate(...args));

// Exclusions end at a path boundary, so look-alikes (/loginx, /api/authx) still pass the gate.
export const config = {
  matcher: ["/((?!api/auth(?:/|$)|login$|_next/static/|_next/image$|favicon\\.ico$).*)"],
};
