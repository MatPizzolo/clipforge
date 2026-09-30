import { expect, test } from "@playwright/test";
import { sessionCookie } from "./session";

const S3_PAGES = ["Review", "Calendar", "Accounts", "Sources", "Produce", "Costs"];

test.beforeEach(async ({ context }) => {
  await context.addCookies([await sessionCookie()]);
});

test("navigation: sidebar on a laptop, bottom tabs and More on a phone", async ({ page }, testInfo) => {
  await page.goto("/");
  const sidebar = page.getByRole("navigation", { name: "Sidebar" });
  const tabs = page.getByRole("navigation", { name: "Tabs" });
  if (testInfo.project.name === "desktop") {
    await expect(sidebar).toBeVisible();
    await expect(tabs).toBeHidden();
    await expect(sidebar.getByRole("link", { name: "Jobs" })).toBeVisible();
    for (const label of S3_PAGES) {
      const item = sidebar.locator('[aria-disabled="true"]', { hasText: label });
      await expect(item).toContainText("coming in S3");
      await expect(sidebar.getByRole("link", { name: label })).toHaveCount(0);
    }
  } else {
    await expect(tabs).toBeVisible();
    await expect(sidebar).toBeHidden();
    await tabs.getByRole("link", { name: "More" }).click();
    for (const label of S3_PAGES) {
      await expect(page.getByText(label, { exact: true })).toBeVisible();
    }
  }
});

test("laptop pages use the width: home grid, job table and side column", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "laptop layout only");
  await page.goto("/");
  const posting = page.getByText("Posting", { exact: true });
  const channel = page.getByText("Billy Garton Jr.");
  await expect(channel).toBeVisible();
  const [a, b] = [await posting.boundingBox(), await channel.boundingBox()];
  expect(Math.abs(a!.y - b!.y)).toBeLessThan(40); // same grid row
  expect(b!.x).toBeGreaterThan(a!.x + 200); // next column

  await page.goto("/jobs/20260929-3fa9c1d2-4b7e");
  await expect(page.getByRole("columnheader", { name: "Error stage" })).toBeVisible();
  const failedRow = page.getByRole("row").filter({ hasText: "clip_06" });
  await expect(failedRow.getByRole("cell").nth(3)).toHaveText("render");
  const clips = await page.getByText("Clips", { exact: true }).boundingBox();
  const cost = await page.getByText("Cost", { exact: true }).boundingBox();
  expect(cost!.x).toBeGreaterThan(clips!.x + 400); // side column

  await page.goto("/jobs");
  await expect(page.getByRole("columnheader", { name: "Last opened" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "29 Sept 2026" })).toBeVisible();
});
