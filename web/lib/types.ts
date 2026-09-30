import type { z } from "zod";
import type { zChannelProgress, zClipState, zJobView, zPostingOverview } from "@/lib/api/zod.gen";

export type Posting = z.output<typeof zPostingOverview>;
export type ChannelProgress = z.output<typeof zChannelProgress>;
export type Job = z.output<typeof zJobView>;
export type Clip = z.output<typeof zClipState>;
