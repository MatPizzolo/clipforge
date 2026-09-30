"use client";

import { useEffect, useState } from "react";
import { ago, staleText } from "@/lib/format";

// `error` is the failed refresh's message, or undefined while the data is fresh.
export function StaleNote({ dataUpdatedAt, error, everyS }: { dataUpdatedAt: number; error?: string; everyS?: number }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1_000);
    return () => clearInterval(timer);
  }, []);
  if (!dataUpdatedAt) return null;
  const when = ago(Math.max(0, now - dataUpdatedAt));
  return (
    <p className="py-2 text-center text-xs text-muted-foreground" aria-live="polite">
      {staleText({ when, everyS, error })}
    </p>
  );
}
