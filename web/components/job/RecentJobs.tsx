"use client";

import Link from "next/link";
import { useSyncExternalStore } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { formatTime } from "@/lib/format";
import { jobCreatedDay } from "@/lib/jobId";
import { readRecent, type RecentJob } from "@/lib/recentJobs";

const noSubscribe = () => () => {};

// One table for both layouts: a plain list of ids on a phone; at ≥ 1024 px the header and the
// Created (from the id) and Last opened columns appear.
export function RecentJobs() {
  // localStorage doesn't exist during server rendering: the server snapshot is an empty list.
  // Snapshots are JSON strings so React sees a stable value between renders.
  const jobs = JSON.parse(useSyncExternalStore(noSubscribe, () => JSON.stringify(readRecent()), () => "[]")) as RecentJob[];
  return (
    <Card>
      <CardContent>
        <b>Recent</b>
        {jobs.length === 0 ? (
          <p className="pt-2 text-sm text-muted-foreground">Jobs you open appear here (on this device only).</p>
        ) : (
          <table className="block w-full border-collapse text-sm lg:mt-2 lg:table">
            <thead className="hidden text-left text-xs text-muted-foreground lg:table-header-group">
              <tr>
                <th className="py-2 font-medium">Job id</th>
                <th className="py-2 font-medium">Created</th>
                <th className="py-2 font-medium">Last opened</th>
              </tr>
            </thead>
            <tbody className="block divide-y lg:table-row-group">
              {jobs.map((job) => (
                <tr key={job.id} className="block lg:table-row">
                  <td className="block lg:table-cell">
                    <Link href={`/jobs/${job.id}`} className="block py-2 underline-offset-2 hover:underline">{job.id}</Link>
                  </td>
                  <td className="hidden text-muted-foreground lg:table-cell">{jobCreatedDay(job.id)}</td>
                  <td className="hidden text-muted-foreground lg:table-cell">
                    {job.openedAt ? formatTime(new Date(job.openedAt).toISOString()) : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  );
}
