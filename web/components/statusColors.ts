import type { PostStatusKey } from "@/lib/statusBar";

export const STATUS_COLOR: Record<PostStatusKey, string> = {
  posted: "bg-emerald-500",
  partly_posted: "bg-lime-400",
  sent: "bg-sky-500",
  queued: "bg-zinc-500",
  skipped: "bg-amber-400",
  rejected: "bg-rose-500",
  unavailable: "bg-fuchsia-500",
};
