import { expect, test } from "vitest";
import { zJobView, zPostingOverview } from "@/lib/api/zod.gen";
import { MOCK_DONE_JOB_ID, MOCK_POSTING, MOCK_RUNNING_JOB_ID, mockJob } from "@/lib/mocks";

test("fixtures match the API contract", () => {
  expect(zPostingOverview.safeParse(MOCK_POSTING).success).toBe(true);
  expect(zJobView.safeParse(mockJob(MOCK_RUNNING_JOB_ID)).success).toBe(true);
  expect(zJobView.safeParse(mockJob(MOCK_DONE_JOB_ID)).success).toBe(true);
});

test("the posting fixture uses a non-UTC offset (Review Focus 1)", () => {
  expect(MOCK_POSTING.next_slot).toMatch(/-03:00$/);
});

test("unknown ids have no fixture", () => {
  expect(mockJob("20260929-00000000-0000")).toBeUndefined();
});
