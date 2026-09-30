import { formatSlot } from "@/lib/format";
import type { Job, Posting } from "@/lib/types";

export type PostingSummary = {
  state: "on" | "paused" | "off";
  problem: string | null;
  nextSlot: string | null;
  perDay: number;
  waiting: number;
  daysLeft: number;
  posted: number;
};

export function summarizePosting(p: Posting, fmt: (iso: string) => string = (iso) => formatSlot(iso)): PostingSummary {
  return {
    state: !p.enabled ? "off" : p.paused ? "paused" : "on",
    problem: p.problem ?? null,
    nextSlot: p.next_slot ? fmt(p.next_slot) : null,
    perDay: p.per_day,
    waiting: p.waiting,
    daysLeft: p.days_left,
    posted: p.channels.reduce((sum, c) => sum + (c.counts?.posted ?? 0), 0),
  };
}

export type JobSummary = {
  clipsDone: number;
  clipsFailed: number;
  clipsTotal: number;
  active: boolean;
  costByStage: { stage: string; usd: number }[];
  totalUsd: number;
};

export function summarizeJob(job: Job): JobSummary {
  const byStage = new Map<string, number>();
  for (const s of job.cost.stages ?? []) byStage.set(s.stage, (byStage.get(s.stage) ?? 0) + (s.usd_estimate ?? 0));
  // Round away float noise (0.004 + 0.007 → 0.011000000000000001).
  const round = (usd: number) => Math.round(usd * 1e6) / 1e6;
  return {
    clipsDone: job.clips.filter((c) => c.status === "done").length,
    clipsFailed: job.clips.filter((c) => c.status === "failed").length,
    clipsTotal: job.clips.length,
    active: job.status === "queued" || job.status === "running",
    costByStage: [...byStage].map(([stage, usd]) => ({ stage, usd: round(usd) })),
    totalUsd: job.cost.total_usd,
  };
}

/** "3 of 6 done · 1 failed": failed clips are never counted as done. */
export function clipProgress(s: Pick<JobSummary, "clipsDone" | "clipsFailed" | "clipsTotal">): string {
  if (s.clipsTotal === 0) return "no clips yet";
  const failed = s.clipsFailed ? ` · ${s.clipsFailed} failed` : "";
  return `${s.clipsDone} of ${s.clipsTotal} done${failed}`;
}
