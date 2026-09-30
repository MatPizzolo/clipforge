import { expect, test } from "vitest";
import { canonicalJobId, isJobId, jobCreatedDay, normalizeJobInput } from "@/lib/jobId";

test("accepts ids made by new_job_id", () => {
  expect(isJobId("20260929-3fa9c1d2-4b7e")).toBe(true);
});

test("rejects anything else", () => {
  for (const bad of [
    "", "../posting", "%2e%2e", "20260929-3FA9C1D2-4B7E", "20260929-3fa9c1d2-4b7e ",
    "20260929-3fa9c1d2-4b7e/..", "2026092-3fa9c1d2-4b7e", "20260929-3fa9c1d2-4b7",
  ]) {
    expect(isJobId(bad), bad).toBe(false);
  }
});

test("lookup input is trimmed and lowercased before the check", () => {
  expect(normalizeJobInput("  20260929-3FA9C1D2-4B7E \n")).toBe("20260929-3fa9c1d2-4b7e");
  expect(isJobId(normalizeJobInput(" 20260929-3FA9C1D2-4B7E "))).toBe(true);
});

test("URL ids: a fixable id maps to its lowercase form, anything else is left alone", () => {
  expect(canonicalJobId("20260929-3FA9C1D2-4B7E")).toBe("20260929-3fa9c1d2-4b7e");
  expect(canonicalJobId(" 20260929-3fa9c1d2-4b7e ")).toBe("20260929-3fa9c1d2-4b7e");
  expect(canonicalJobId("20260929-3fa9c1d2-4b7e")).toBeNull(); // already canonical
  expect(canonicalJobId("../POSTING")).toBeNull(); // not a job id even when normalized
});

test("the created day comes from the id's yyyymmdd (no API call)", () => {
  expect(jobCreatedDay("20260929-3fa9c1d2-4b7e")).toBe("29 Sept 2026");
  expect(jobCreatedDay("20261399-3fa9c1d2-4b7e")).toBe("—"); // not a real date
  expect(jobCreatedDay("nope")).toBe("—");
});
