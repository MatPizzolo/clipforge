import { expect, test } from "vitest";
import { staleText } from "@/lib/format";

test("fresh data says when and how often", () => {
  expect(staleText({ when: "4 s ago", everyS: 15 })).toBe("Updated 4 s ago · refreshes every 15 s");
  expect(staleText({ when: "4 s ago" })).toBe("Updated 4 s ago");
});

test("a failed refresh names the reason (wrong token stays visible on an open tab)", () => {
  expect(staleText({ when: "1 min ago", error: "API rejected the token" })).toBe(
    "Couldn't refresh (API rejected the token) · last updated 1 min ago",
  );
  expect(staleText({ when: "1 min ago", error: "" })).toBe("Couldn't refresh · last updated 1 min ago");
});
