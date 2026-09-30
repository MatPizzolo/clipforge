import { expect, test } from "vitest";
import { HOME_POLL_MS, JOB_POLL_MS, jobRefetchInterval } from "@/lib/polling";

test("intervals", () => {
  expect(HOME_POLL_MS).toBe(15_000);
  expect(JOB_POLL_MS).toBe(5_000);
});

test("jobs poll only while they can still change", () => {
  expect(jobRefetchInterval({ status: "queued" })).toBe(5_000);
  expect(jobRefetchInterval({ status: "running" })).toBe(5_000);
  expect(jobRefetchInterval({})).toBe(5_000);
  expect(jobRefetchInterval({ status: "done" })).toBe(false);
  expect(jobRefetchInterval({ status: "failed" })).toBe(false);
  expect(jobRefetchInterval({ errorStatus: 404 })).toBe(false);
  expect(jobRefetchInterval({ errorStatus: 401 })).toBe(false);
  expect(jobRefetchInterval({ status: "running", errorStatus: 502 })).toBe(5_000);
});
