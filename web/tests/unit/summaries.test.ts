import { expect, test } from "vitest";
import { summarizeJob, summarizePosting } from "@/lib/summaries";
import type { Job, Posting } from "@/lib/types";

const posting: Posting = {
  enabled: true, paused: false, next_slot: "2026-09-29T18:00:00-03:00",
  waiting: 41, days_left: 7, per_day: 6, problem: null,
  channels: [
    { slug: "a", name: "A", episodes_clipped: 1, episodes_clipping: 0, episodes_failed: 0, counts: { posted: 20, queued: 3 } },
    { slug: "b", name: "B", episodes_clipped: 1, episodes_clipping: 0, episodes_failed: 0 },
  ],
};

test("posting summary", () => {
  expect(summarizePosting(posting, () => "today 18:00")).toEqual({
    state: "on", problem: null, nextSlot: "today 18:00", perDay: 6, waiting: 41, daysLeft: 7, posted: 20,
  });
  expect(summarizePosting({ ...posting, paused: true }).state).toBe("paused");
  const off = summarizePosting({ ...posting, enabled: false, next_slot: null, problem: "bad POSTING_SLOTS" });
  expect(off).toMatchObject({ state: "off", nextSlot: null, problem: "bad POSTING_SLOTS" });
});

type StageCost = NonNullable<Job["cost"]["stages"]>[number];
const stage = (s: StageCost["stage"], usd: number): StageCost =>
  ({ stage: s, usd_estimate: usd, cached: false, gpu_s: 0, llm_calls: 0, llm_input_tokens: 0, llm_output_tokens: 0, wall_s: 0 });

test("job summary", () => {
  const job = {
    job_id: "20260929-3fa9c1d2-4b7e", status: "running", stage: "render",
    created_at: "2026-09-29T12:04:00Z", updated_at: "2026-09-29T12:09:00Z",
    clips: [
      { clip_id: "clip_01", spec_ref: "x", status: "done", telegram_sent: true, updated_at: "2026-09-29T12:08:00Z" },
      { clip_id: "clip_02", spec_ref: "x", status: "failed", telegram_sent: false, updated_at: "2026-09-29T12:08:00Z" },
      { clip_id: "clip_03", spec_ref: "x", status: "running", telegram_sent: false, updated_at: "2026-09-29T12:08:00Z" },
    ],
    cost: {
      total_usd: 0.084,
      stages: [stage("transcribe", 0.041), stage("render", 0.004), stage("highlights", 0.032), stage("render", 0.007)],
    },
  } as Job;
  expect(summarizeJob(job)).toEqual({
    clipsDone: 1, clipsFailed: 1, clipsTotal: 3, active: true, totalUsd: 0.084,
    costByStage: [
      { stage: "transcribe", usd: 0.041 },
      { stage: "render", usd: 0.011 },
      { stage: "highlights", usd: 0.032 },
    ],
  });
  expect(summarizeJob({ ...job, status: "done" }).active).toBe(false);
});

test("clip progress line counts done clips only and names failures", async () => {
  const { clipProgress } = await import("@/lib/summaries");
  expect(clipProgress({ clipsDone: 3, clipsFailed: 1, clipsTotal: 6 })).toBe("3 of 6 done · 1 failed");
  expect(clipProgress({ clipsDone: 2, clipsFailed: 0, clipsTotal: 2 })).toBe("2 of 2 done");
  expect(clipProgress({ clipsDone: 0, clipsFailed: 0, clipsTotal: 0 })).toBe("no clips yet");
});
