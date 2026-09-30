import { Card, CardContent } from "@/components/ui/card";
import { STATUS_COLOR } from "@/components/statusColors";
import { STATUS_LABEL, statusSegments } from "@/lib/statusBar";
import type { ChannelProgress } from "@/lib/types";

export function ChannelCard({ c }: { c: ChannelProgress }) {
  const segments = statusSegments(c.counts);
  const episodes = [
    `${c.episodes_clipped} episodes clipped`,
    c.episodes_clipping ? `${c.episodes_clipping} clipping` : null,
    c.episodes_failed ? `${c.episodes_failed} failed` : null,
  ].filter(Boolean).join(" · ");
  return (
    <Card>
      <CardContent className="space-y-2">
        <div className="flex items-baseline justify-between gap-2">
          <b className="truncate">{c.name}</b>
          <span className="shrink-0 text-xs text-muted-foreground">{c.slug}</span>
        </div>
        <p className="text-xs text-muted-foreground">{episodes}</p>
        {segments.length > 0 ? (
          <>
            <div
              className="flex h-2.5 overflow-hidden rounded-full bg-muted"
              role="img"
              aria-label={segments.map((s) => `${STATUS_LABEL[s.status]} ${s.count}`).join(", ")}
            >
              {segments.map((s) => (
                <span key={s.status} className={STATUS_COLOR[s.status]} style={{ width: `${s.pct}%` }} />
              ))}
            </div>
            <ul className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted-foreground">
              {segments.map((s) => (
                <li key={s.status} className="flex items-center gap-1">
                  <span className={`inline-block size-2 rounded-sm ${STATUS_COLOR[s.status]}`} />
                  {STATUS_LABEL[s.status]} {s.count}
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="text-xs text-muted-foreground">No clips queued yet.</p>
        )}
      </CardContent>
    </Card>
  );
}
