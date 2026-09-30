"use client";

import { useQuery } from "@tanstack/react-query";
import { ApiError, fetchJson } from "@/lib/fetchJson";
import { HOME_POLL_MS, jobRefetchInterval } from "@/lib/polling";
import type { Job, Posting } from "@/lib/types";

function retry(failures: number, error: Error): boolean {
  if (error instanceof ApiError && (error.status === 401 || error.status === 404)) return false;
  return failures < 2;
}

export function usePosting() {
  return useQuery({
    queryKey: ["posting"],
    queryFn: () => fetchJson<Posting>("/api/cf/posting"),
    refetchInterval: HOME_POLL_MS,
    refetchIntervalInBackground: false,
    retry,
  });
}

export function useJob(id: string) {
  return useQuery({
    queryKey: ["job", id],
    queryFn: () => fetchJson<Job>(`/api/cf/jobs/${encodeURIComponent(id)}`),
    refetchInterval: (query) =>
      jobRefetchInterval({
        status: query.state.data?.status,
        errorStatus: query.state.error instanceof ApiError ? query.state.error.status : undefined,
      }),
    refetchIntervalInBackground: false,
    retry,
  });
}
