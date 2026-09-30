import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import type { PostingSummary } from "@/lib/summaries";

const PILL = {
  on: { text: "on", className: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-300" },
  paused: { text: "paused", className: "bg-amber-500/15 text-amber-700 dark:text-amber-300" },
  off: { text: "off", className: "bg-muted text-muted-foreground" },
} as const;

export function PostingCard({ s }: { s: PostingSummary }) {
  const pill = PILL[s.state];
  const stats: [string, number][] = [["waiting", s.waiting], ["days left", s.daysLeft], ["posted", s.posted]];
  return (
    <>
      {s.problem && (
        <div role="alert" className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-sm lg:col-span-full">
          Posting is off: {s.problem}
        </div>
      )}
      <Card>
        <CardContent className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="font-medium">Posting</span>
            <Badge className={pill.className}>● {pill.text}</Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            {s.nextSlot ? <>Next slot <b className="text-foreground">{s.nextSlot}</b> · </> : null}
            {s.perDay}/day
          </p>
          <dl className="grid grid-cols-3 gap-2 text-center">
            {stats.map(([label, value]) => (
              <div key={label} className="flex flex-col-reverse rounded-md bg-muted/50 py-2">
                <dt className="text-xs text-muted-foreground">{label}</dt>
                <dd className="text-xl font-bold tabular-nums">{value}</dd>
              </div>
            ))}
          </dl>
        </CardContent>
      </Card>
    </>
  );
}
