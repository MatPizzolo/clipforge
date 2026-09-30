// GET /posting scans the whole Dict and keeps the Modal container warm, so Home polls slowly.
export const HOME_POLL_MS = 15_000;
export const JOB_POLL_MS = 5_000;

export function jobRefetchInterval(state: { status?: string; errorStatus?: number }): number | false {
  if (state.errorStatus === 404 || state.errorStatus === 401) return false;
  if (state.status === "done" || state.status === "failed") return false;
  return JOB_POLL_MS;
}
