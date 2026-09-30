import { Card, CardContent } from "@/components/ui/card";
import { formatUsd } from "@/lib/format";
import type { JobSummary } from "@/lib/summaries";

export function CostCard({ s }: { s: JobSummary }) {
  return (
    <Card>
      <CardContent className="space-y-1">
        <div className="flex justify-between">
          <b>Cost</b>
          <b className="tabular-nums">{formatUsd(s.totalUsd)}</b>
        </div>
        {s.costByStage.length > 0 && (
          <p className="text-xs text-muted-foreground">
            {s.costByStage.map((c) => `${c.stage} ${formatUsd(c.usd)}`).join(" · ")}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
