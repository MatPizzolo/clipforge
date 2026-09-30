import { defineConfig, devices } from "@playwright/test";
import { E2E_SECRET } from "./e2e/session";

const PORT = 3100;

export default defineConfig({
  testDir: "e2e",
  forbidOnly: !!process.env.CI,
  reporter: process.env.CI ? "list" : "line",
  use: { baseURL: `http://127.0.0.1:${PORT}` },
  // Every page works on phone and laptop (08 §2): the same specs run at both sizes.
  projects: [
    { name: "phone", use: { ...devices["Pixel 7"] } },
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
  ],
  webServer: {
    command: `npm run build && npx next start -p ${PORT} -H 127.0.0.1`,
    url: `http://127.0.0.1:${PORT}/login`,
    reuseExistingServer: !process.env.CI,
    timeout: 240_000,
    // Set explicitly: Next never overrides defined variables with .env.local, so a local
    // AUTH_DISABLED=1 or real API settings can't leak into the smoke run.
    env: {
      AUTH_DISABLED: "",
      CLIPFORGE_API_URL: "",
      API_TOKEN: "",
      MOCK_API: "1",
      AUTH_SECRET: E2E_SECRET,
      AUTH_TRUST_HOST: "true",
      AUTH_GITHUB_ID: "e2e",
      AUTH_GITHUB_SECRET: "e2e",
      OWNER_EMAIL: "owner@example.com",
    },
  },
});
