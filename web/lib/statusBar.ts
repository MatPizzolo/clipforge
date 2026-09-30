export const STATUS_ORDER = [
  "posted", "partly_posted", "sent", "queued", "skipped", "rejected", "unavailable",
] as const;

export type PostStatusKey = (typeof STATUS_ORDER)[number];

export const STATUS_LABEL: Record<PostStatusKey, string> = {
  posted: "posted",
  partly_posted: "partly",
  sent: "sent",
  queued: "queued",
  skipped: "skipped",
  rejected: "rejected",
  unavailable: "unavailable",
};

export type Segment = { status: PostStatusKey; count: number; pct: number };

export function statusSegments(counts?: Record<string, number>): Segment[] {
  const rows = STATUS_ORDER.map((status) => ({ status, count: Math.max(0, counts?.[status] ?? 0) }))
    .filter((row) => row.count > 0);
  const total = rows.reduce((sum, row) => sum + row.count, 0);
  return rows.map((row) => ({ ...row, pct: (row.count / total) * 100 }));
}
