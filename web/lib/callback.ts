// Deep links through login: the proxy sends a signed-out visit to /login?callbackUrl=<path+query>,
// and the login page passes it to signIn's redirectTo. Only same-site relative paths come back, so
// the parameter can't be used to redirect anywhere else (open redirect).

const LOGIN = /^\/login(?:[/?#]|$)/;

/** Where the proxy sends a signed-out request for `pathname` + `search`. */
export function loginPathFor(pathname: string, search: string): string {
  const target = pathname + search;
  return target === "/" ? "/login" : `/login?callbackUrl=${encodeURIComponent(target)}`;
}

/** The callbackUrl to honor after login, or "/" when it isn't a plain relative path. */
export function safeCallback(value: string | string[] | undefined | null): string {
  if (typeof value !== "string" || !value.startsWith("/")) return "/";
  if (value.startsWith("//") || value.includes("\\") || /[\u0000-\u001f\u007f]/.test(value)) return "/";
  if (LOGIN.test(value)) return "/";
  return value;
}
