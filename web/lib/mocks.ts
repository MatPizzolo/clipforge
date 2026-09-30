// Fixtures for MOCK_API=1 (local dev, CI and Playwright). Shapes match the API contract (tested).
import type { Job, Posting } from "@/lib/types";

export const MOCK_RUNNING_JOB_ID = "20260929-3fa9c1d2-4b7e";
export const MOCK_DONE_JOB_ID = "20260928-9b2e44a0-1c3d";

export const MOCK_POSTING: Posting = {
  enabled: true,
  paused: false,
  next_slot: "2026-09-29T18:00:00-03:00", // posting timezone offset, as the API sends it
  waiting: 41,
  days_left: 7,
  per_day: 6,
  problem: null,
  channels: [
    {
      slug: "billy-garton",
      name: "Billy Garton Jr.",
      episodes_clipped: 9,
      episodes_clipping: 1,
      episodes_failed: 1,
      counts: { posted: 20, partly_posted: 5, sent: 4, queued: 29, skipped: 5, rejected: 3 },
    },
    {
      slug: "founder-tapes",
      name: "Founder Tapes",
      episodes_clipped: 2,
      episodes_clipping: 0,
      episodes_failed: 0,
      counts: { posted: 3, queued: 12 },
    },
  ],
};

const at = "2026-09-29T12:09:00Z";

type StageCost = NonNullable<Job["cost"]["stages"]>[number];

const cost = (stage: StageCost["stage"], usd: number, clip_id?: string): StageCost => ({
  stage,
  clip_id: clip_id ?? null,
  usd_estimate: usd,
  wall_s: 0,
  gpu_s: 0,
  gpu_type: null,
  llm_model: null,
  llm_input_tokens: 0,
  llm_output_tokens: 0,
  llm_calls: 0,
  cached: false,
});

function clip(n: number, status: "pending" | "running" | "done" | "failed", pct?: number): Job["clips"][number] {
  const clip_id = `clip_0${n}`;
  return {
    clip_id,
    spec_ref: `mock/${clip_id}.json`,
    status,
    telegram_sent: status === "done",
    updated_at: at,
    result_ref: status === "done" ? `mock/${clip_id}/result.json` : null,
    progress: status === "running" ? { stage: "render", pct: pct ?? 0, message: "encoding…", at } : null,
    error: status === "failed" ? { stage: "render", error_type: "RenderError", message: "ffmpeg exited with status 1" } : null,
    cost: [],
  };
}

const JOBS: Record<string, Job> = {
  [MOCK_RUNNING_JOB_ID]: {
    job_id: MOCK_RUNNING_JOB_ID,
    status: "running",
    stage: "render",
    created_at: "2026-09-29T12:04:00Z",
    updated_at: at,
    progress: { stage: "render", pct: 55, message: "clip_04: encoding…", at },
    error: null,
    output_zip: null,
    download_url: null,
    clips: [clip(1, "done"), clip(2, "done"), clip(3, "done"), clip(4, "running", 55), clip(5, "pending"), clip(6, "failed")],
    cost: {
      total_usd: 0.084,
      stages: [cost("transcribe", 0.041), cost("highlights", 0.032), cost("render", 0.006, "clip_01"), cost("render", 0.005, "clip_02")],
    },
  },
  [MOCK_DONE_JOB_ID]: {
    job_id: MOCK_DONE_JOB_ID,
    status: "done",
    stage: "package",
    created_at: "2026-09-28T09:00:00Z",
    updated_at: "2026-09-28T09:07:00Z",
    progress: { stage: "package", pct: 100, message: "done", at: "2026-09-28T09:07:00Z" },
    error: null,
    output_zip: `${MOCK_DONE_JOB_ID}/job.zip`,
    download_url: "https://example.invalid/mock-download.zip",
    clips: [clip(1, "done"), clip(2, "done")],
    cost: { total_usd: 0.061, stages: [cost("transcribe", 0.03), cost("highlights", 0.025), cost("render", 0.006)] },
  },
};

export function mockJob(id: string): Job | undefined {
  return JOBS[id];
}
