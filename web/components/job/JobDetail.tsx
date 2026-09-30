"use client";

import Link from "next/link";
import { useEffect } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { ClipList } from "@/components/job/ClipList";
import { CostCard } from "@/components/job/CostCard";
import { StaleNote } from "@/components/StaleNote";
import { ApiError } from "@/lib/fetchJson";
import { formatTime } from "@/lib/format";
import { JOB_POLL_MS } from "@/lib/polling";
import { useJob } from "@/lib/queries";
import { addRecent } from "@/lib/recentJobs";
import { clipProgress, summarizeJob } from "@/lib/summaries";

const STATUS_TONE = {
  queued: "bg-amber-500/15 text-amber-700 dark:text-amber-300",
  running: "bg-sky-500/15 text-sky-600 dark:text-sky-300",
  done: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-300",
  failed: "bg-rose-500/15 text-rose-600 dark:text-rose-300",
} as const;

export function JobDetail({ id }: { id: string }) {
  const q = useJob(id);
  const found = Boolean(q.data);
  useEffect(() => {
    if (found) addRecent(id);
  }, [found, id]);

  if (q.isPending) {
    return (
      <div className="space-y-3">
        <Skeleton className="h-28" />
        <Skeleton className="h-48" />
      </div>
    );
  }
  if (!q.data) {
    const unknown = q.error instanceof ApiError && q.error.status === 404;
    return (
      <Card>
        <CardContent className="space-y-3">
          <p className="font-medium">{unknown ? "Unknown job" : (q.error?.message ?? "API unavailable")}</p>
          <p className="break-all text-xs text-muted-foreground">{id}</p>
          {unknown ? (
            <Link href="/jobs" className="text-sm underline">Back to jobs</Link>
          ) : (
            <Button variant="secondary" onClick={() => q.refetch()}>Retry</Button>
          )}
        </CardContent>
      </Card>
    );
  }

  const job = q.data;
  const s = summarizeJob(job);
  // Laptop: the job and its clips on the left, cost, times and the download link in a side column.
  return (
    <div className="space-y-3 lg:grid lg:grid-cols-[1fr_20rem] lg:items-start lg:gap-4 lg:space-y-0">
      <div className="space-y-3">
        <Card>
          <CardContent className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <span className="break-all text-xs text-muted-foreground">{job.job_id}</span>
              <Badge className={STATUS_TONE[job.status]}>{job.status}</Badge>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span>Stage: <b>{job.stage ?? "—"}</b></span>
              <span className="text-muted-foreground">{clipProgress(s)}</span>
            </div>
            {job.progress && s.active && (
              <>
                <Progress value={job.progress.pct} aria-label="Stage progress" />
                {job.progress.message && <p className="text-xs text-muted-foreground">{job.progress.message}</p>}
              </>
            )}
          </CardContent>
        </Card>
        {job.error && (
          <div role="alert" className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm">
            Failed at {job.error.stage}: {job.error.message}
          </div>
        )}
        <ClipList clips={job.clips} />
      </div>
      <div className="space-y-3">
        <CostCard s={s} />
        <Card>
          <CardContent className="space-y-1 text-sm text-muted-foreground">
            {job.download_url && (
              <a href={job.download_url} className="block font-medium text-foreground underline" rel="noopener noreferrer">
                Download zip
              </a>
            )}
            <p>Created {formatTime(job.created_at)} · updated {formatTime(job.updated_at)}</p>
          </CardContent>
        </Card>
        <StaleNote dataUpdatedAt={q.dataUpdatedAt} error={q.isError ? q.error?.message : undefined} everyS={s.active ? JOB_POLL_MS / 1000 : undefined} />
      </div>
    </div>
  );
}
