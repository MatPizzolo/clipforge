import { isJobId } from "@/lib/jobId";

const KEY = "clipforge.recentJobs";
const MAX = 10;

/** One recently opened job; `openedAt` is epoch ms, or null for entries saved before it existed. */
export type RecentJob = { id: string; openedAt: number | null };

function browserStorage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null; // blocked storage throws on access
  }
}

function parseEntry(x: unknown): RecentJob | null {
  if (typeof x === "string") return isJobId(x) ? { id: x, openedAt: null } : null; // old format: plain ids
  if (x && typeof x === "object" && "id" in x && typeof x.id === "string" && isJobId(x.id)) {
    const openedAt = "openedAt" in x && typeof x.openedAt === "number" ? x.openedAt : null;
    return { id: x.id, openedAt };
  }
  return null;
}

export function readRecent(storage: Storage | null = browserStorage()): RecentJob[] {
  try {
    const raw = storage?.getItem(KEY);
    const parsed: unknown = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(parsed)) return [];
    return parsed.map(parseEntry).filter((x): x is RecentJob => x !== null).slice(0, MAX);
  } catch {
    return [];
  }
}

export function addRecent(id: string, storage: Storage | null = browserStorage(), now: number = Date.now()): RecentJob[] {
  if (!isJobId(id)) return readRecent(storage);
  const next = [{ id, openedAt: now }, ...readRecent(storage).filter((x) => x.id !== id)].slice(0, MAX);
  try {
    storage?.setItem(KEY, JSON.stringify(next));
  } catch {
    // a per-viewer convenience: losing it is fine
  }
  return next;
}
