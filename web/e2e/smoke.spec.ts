import { expect, test } from "@playwright/test";
import { sessionCookie } from "./session";

const RUNNING = "20260929-3fa9c1d2-4b7e";

test.describe("signed out", () => {
  test("home redirects to login", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByRole("button", { name: "Sign in with GitHub" })).toBeVisible();
  });

  test("look-alike paths don't skip the gate", async ({ page, request }) => {
    await page.goto("/loginx");
    await expect(page).toHaveURL(`/login?callbackUrl=${encodeURIComponent("/loginx")}`);
    const res = await request.get("/api/authx");
    expect(res.status()).toBe(401);
  });

  test("a deep link returns to the page after login", async ({ page, context }) => {
    const deep = `/jobs/${RUNNING}`;
    await page.goto(deep);
    await expect(page).toHaveURL(`/login?callbackUrl=${encodeURIComponent(deep)}`);
    // GitHub isn't reachable in tests: stop at the authorize request and check where Auth.js will return.
    let authorize: URL | undefined;
    await page.route("https://github.com/**", async (route) => {
      authorize = new URL(route.request().url());
      await route.fulfill({ status: 200, contentType: "text/html", body: "github (stubbed)" });
    });
    await page.getByRole("button", { name: "Sign in with GitHub" }).click();
    await expect.poll(() => authorize?.pathname).toBe("/login/oauth/authorize");
    const callback = (await context.cookies()).find((c) => c.name === "authjs.callback-url");
    expect(decodeURIComponent(callback?.value ?? "")).toBe(`http://127.0.0.1:3100${deep}`);
  });

  test("the API proxy answers 401", async ({ request }) => {
    const res = await request.get("/api/cf/posting");
    expect(res.status()).toBe(401);
    expect(await res.json()).toEqual({ error: "unauthorized" });
  });
});

test.describe("signed in", () => {
  test.beforeEach(async ({ context }) => {
    await context.addCookies([await sessionCookie()]);
  });

  test("home shows posting progress per channel", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByText("Billy Garton Jr.")).toBeVisible();
    await expect(page.getByText("Founder Tapes")).toBeVisible();
    await expect(page.getByText("posted 20")).toBeVisible();
    await expect(page.getByText(/Next slot/)).toBeVisible();
    await expect(page.getByText(/Updated .* refreshes every 15 s/)).toBeVisible();
  });

  test("lookup opens the job page, which lists clips", async ({ page }) => {
    await page.goto("/jobs");
    await page.getByLabel("Job id").fill(` ${RUNNING.toUpperCase()} `);
    await page.getByRole("button", { name: "Go" }).click();
    await expect(page).toHaveURL(new RegExp(`/jobs/${RUNNING}$`));
    await expect(page.getByText("clip_04", { exact: true })).toBeVisible();
    // Phone: one "running 55%" badge; laptop: a separate Progress cell. Only the visible one counts.
    await expect(page.getByText(/55%/).filter({ visible: true })).toBeVisible();
    await page.goto("/jobs");
    await expect(page.getByRole("link", { name: RUNNING })).toBeVisible();
  });

  test("an uppercase id in the URL is lowercased", async ({ page }) => {
    await page.goto(`/jobs/${RUNNING.toUpperCase()}`);
    await expect(page).toHaveURL(new RegExp(`/jobs/${RUNNING}$`));
    await expect(page.getByText("3 of 6 done · 1 failed")).toBeVisible();
  });

  test("an unknown job says so", async ({ page }) => {
    await page.goto("/jobs/20260929-00000000-0000");
    await expect(page.getByText("Unknown job")).toBeVisible();
  });

  test("a bad id never reaches the API", async ({ page }) => {
    // page.request shares the context's session cookie; the bare `request` fixture doesn't.
    const res = await page.request.get("/api/cf/jobs/..%2Fposting");
    expect(res.status()).toBe(404);
    expect(await res.json()).toEqual({ error: "unknown job" });
  });
});
