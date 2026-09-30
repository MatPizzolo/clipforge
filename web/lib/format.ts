// All times show in the viewer's zone; `timeZone` is only passed by tests.
function dayKey(date: Date, timeZone?: string): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).format(date);
}

export function formatSlot(iso: string, now: Date = new Date(), timeZone?: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  const time = new Intl.DateTimeFormat("en-GB", { timeZone, hour: "2-digit", minute: "2-digit" }).format(date);
  const day = dayKey(date, timeZone);
  if (day === dayKey(now, timeZone)) return `today ${time}`;
  if (day === dayKey(new Date(now.getTime() + 86_400_000), timeZone)) return `tomorrow ${time}`;
  const weekday = new Intl.DateTimeFormat("en-GB", { timeZone, weekday: "short" }).format(date);
  return `${weekday} ${time}`;
}

export function ago(ms: number): string {
  if (ms < 1_000) return "just now";
  if (ms < 60_000) return `${Math.floor(ms / 1_000)} s ago`;
  if (ms < 3_600_000) return `${Math.floor(ms / 60_000)} min ago`;
  return `${Math.floor(ms / 3_600_000)} h ago`;
}

export function formatUsd(usd: number): string {
  return `$${usd.toFixed(3)}`;
}

export function formatTime(iso: string, timeZone?: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en-GB", {
    timeZone, day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
  }).format(date);
}

/** The "updated N ago" line; a failed refresh names its reason (e.g. a rejected API token). */
export function staleText({ when, everyS, error }: { when: string; everyS?: number; error?: string }): string {
  if (error !== undefined) return `Couldn't refresh${error ? ` (${error})` : ""} · last updated ${when}`;
  return `Updated ${when}${everyS ? ` · refreshes every ${everyS} s` : ""}`;
}
