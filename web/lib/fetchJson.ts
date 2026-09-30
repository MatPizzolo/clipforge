export class ApiError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
  }
}

// Browser → our /api/cf handlers only. A 401 means the session ended: go to the login page.
export async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { cache: "no-store" });
  if (res.status === 401 && typeof window !== "undefined") {
    // A full load on purpose: the session ended, so start over at the server-rendered login page.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.assign("/login");
  }
  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    const message =
      body && typeof body === "object" && "error" in body && typeof body.error === "string" ? body.error : "request failed";
    throw new ApiError(res.status, message);
  }
  return body as T;
}
