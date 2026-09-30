// Same pattern as clipforge.jobs.is_job_id: "<yyyymmdd>-<source_hash8>-<rand4>".
const JOB_ID = /^\d{8}-[0-9a-f]{8}-[0-9a-f]{4}$/;

export function isJobId(value: string): boolean {
  return JOB_ID.test(value);
}

/** What the lookup box checks: pasted ids may carry spaces or uppercase hex. */
export function normalizeJobInput(value: string): string {
  return value.trim().toLowerCase();
}

/** For ids in the URL: the lowercase form when that fixes it, or null (already canonical or not an id). */
export function canonicalJobId(value: string): string | null {
  const id = normalizeJobInput(value);
  return id !== value && isJobId(id) ? id : null;
}

/** "29 Sept 2026" from the id's leading yyyymmdd (UTC), or "—" when it isn't a real date. */
export function jobCreatedDay(id: string): string {
  const m = /^(\d{4})(\d{2})(\d{2})-/.exec(id);
  if (!m) return "—";
  const [year, month, day] = [Number(m[1]), Number(m[2]), Number(m[3])];
  const date = new Date(Date.UTC(year, month - 1, day));
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) return "—";
  return new Intl.DateTimeFormat("en-GB", { timeZone: "UTC", day: "numeric", month: "short", year: "numeric" }).format(date);
}
