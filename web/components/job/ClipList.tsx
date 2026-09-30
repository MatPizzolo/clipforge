import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import type { Clip } from "@/lib/types";

const TONE: Record<Clip["status"], string> = {
  done: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-300",
  running: "bg-sky-500/15 text-sky-600 dark:text-sky-300",
  pending: "bg-amber-500/15 text-amber-700 dark:text-amber-300",
  failed: "bg-rose-500/15 text-rose-600 dark:text-rose-300",
};

/** Phone badge: status plus progress or error stage in one label. */
function label(c: Clip): string {
  if (c.status === "running" && c.progress) return `running ${Math.round(c.progress.pct)}%`;
  if (c.status === "failed" && c.error) return `failed · ${c.error.stage}`;
  return c.status;
}

// One table for both layouts, so each clip's text exists once: on a phone the rows render as the
// familiar list (combined badge); at ≥ 1024 px the header and the progress and error columns appear.
export function ClipList({ clips }: { clips: Clip[] }) {
  return (
    <Card>
      <CardContent>
        <b>Clips</b>
        {clips.length === 0 ? (
          <p className="pt-2 text-sm text-muted-foreground">No clips yet.</p>
        ) : (
          <table className="block w-full border-collapse text-sm lg:mt-2 lg:table">
            <thead className="hidden text-left text-xs text-muted-foreground lg:table-header-group">
              <tr>
                <th className="py-2 font-medium">Clip</th>
                <th className="py-2 font-medium">Status</th>
                <th className="py-2 font-medium">Progress</th>
                <th className="py-2 font-medium">Error stage</th>
              </tr>
            </thead>
            <tbody className="block divide-y lg:table-row-group">
              {clips.map((c) => (
                <tr key={c.clip_id} className="flex items-center justify-between py-2 lg:table-row">
                  <td className="lg:py-2">{c.clip_id}</td>
                  <td className="lg:py-2">
                    <Badge className={TONE[c.status]}>
                      <span className="lg:hidden">{label(c)}</span>
                      <span className="hidden lg:inline">{c.status}</span>
                    </Badge>
                  </td>
                  <td className="hidden tabular-nums lg:table-cell lg:py-2">
                    {c.status === "running" && c.progress ? `${Math.round(c.progress.pct)}%` : "—"}
                  </td>
                  <td className="hidden lg:table-cell lg:py-2">{c.error?.stage ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  );
}
