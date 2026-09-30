import { expect, test } from "vitest";
import { STATUS_ORDER, statusSegments } from "@/lib/statusBar";

test("fixed order, zero counts dropped, percentages sum to 100", () => {
  const segments = statusSegments({ queued: 29, posted: 20, rejected: 3, sent: 0 });
  expect(segments.map((s) => s.status)).toEqual(["posted", "queued", "rejected"]);
  expect(segments.reduce((sum, s) => sum + s.pct, 0)).toBeCloseTo(100);
  expect(segments[0]).toMatchObject({ status: "posted", count: 20 });
});

test("empty, missing and unknown statuses give no segments", () => {
  expect(statusSegments(undefined)).toEqual([]);
  expect(statusSegments({})).toEqual([]);
  expect(statusSegments({ mystery: 4 })).toEqual([]);
  expect(statusSegments({ posted: -2 })).toEqual([]);
});

test("the order covers every PostStatus", () => {
  expect([...STATUS_ORDER].sort()).toEqual(
    ["partly_posted", "posted", "queued", "rejected", "sent", "skipped", "unavailable"],
  );
});
