import { expect, test } from "vitest";
import { ago, formatSlot, formatTime, formatUsd } from "@/lib/format";

const now = new Date("2026-09-29T15:00:00Z");

test("slot with a -03:00 offset shows in the viewer's zone", () => {
  expect(formatSlot("2026-09-29T18:00:00-03:00", now, "America/Sao_Paulo")).toBe("today 18:00");
  expect(formatSlot("2026-09-29T18:00:00-03:00", now, "UTC")).toBe("today 21:00");
  expect(formatSlot("2026-09-30T09:00:00-03:00", now, "America/Sao_Paulo")).toBe("tomorrow 09:00");
  expect(formatSlot("2026-10-02T09:00:00Z", now, "UTC")).toBe("Fri 09:00");
});

test("an unparseable slot shows a dash", () => {
  expect(formatSlot("not a date", now, "UTC")).toBe("—");
});

test("ago", () => {
  expect(ago(400)).toBe("just now");
  expect(ago(4_200)).toBe("4 s ago");
  expect(ago(125_000)).toBe("2 min ago");
  expect(ago(2 * 3_600_000)).toBe("2 h ago");
});

test("usd and time", () => {
  expect(formatUsd(0.08449)).toBe("$0.084");
  expect(formatUsd(0)).toBe("$0.000");
  expect(formatTime("2026-09-29T12:04:05Z", "UTC")).toBe("29 Sept, 12:04");
});
