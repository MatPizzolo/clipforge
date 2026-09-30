"use client";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ChannelCard } from "@/components/home/ChannelCard";
import { PostingCard } from "@/components/home/PostingCard";
import { JobLookup } from "@/components/JobLookup";
import { StaleNote } from "@/components/StaleNote";
import { HOME_POLL_MS } from "@/lib/polling";
import { usePosting } from "@/lib/queries";
import { summarizePosting } from "@/lib/summaries";

export function HomeView() {
  const q = usePosting();
  if (q.isPending) {
    return (
      <div className="space-y-3 lg:grid lg:grid-cols-2 lg:gap-4 lg:space-y-0 xl:grid-cols-3">
        <Skeleton className="h-36" />
        <Skeleton className="h-28" />
        <Skeleton className="h-28" />
      </div>
    );
  }
  if (!q.data) {
    return (
      <Card>
        <CardContent className="space-y-3">
          <p>{q.error?.message ?? "API unavailable"}</p>
          <Button variant="secondary" onClick={() => q.refetch()}>Retry</Button>
        </CardContent>
      </Card>
    );
  }
  // Laptop: the posting card and channel cards share a 2–3 column grid; lookup and status below.
  return (
    <div className="space-y-3 lg:space-y-6">
      <div className="space-y-3 lg:grid lg:grid-cols-2 lg:items-start lg:gap-4 lg:space-y-0 xl:grid-cols-3">
        <PostingCard s={summarizePosting(q.data)} />
        {q.data.channels.length === 0 && (
          <p className="px-1 text-sm text-muted-foreground">No channels yet. Run `clipforge clip` with a channel folder.</p>
        )}
        {q.data.channels.map((c) => <ChannelCard key={c.slug} c={c} />)}
      </div>
      <div className="space-y-3 lg:flex lg:items-center lg:justify-between lg:gap-4 lg:space-y-0">
        <div className="lg:w-full lg:max-w-lg"><JobLookup /></div>
        <StaleNote dataUpdatedAt={q.dataUpdatedAt} error={q.isError ? q.error?.message : undefined} everyS={HOME_POLL_MS / 1000} />
      </div>
    </div>
  );
}
