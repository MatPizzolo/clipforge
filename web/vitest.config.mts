import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

const here = fileURLToPath(new URL(".", import.meta.url));

export default defineConfig({
  resolve: {
    alias: {
      "@": here,
      // `server-only` throws outside React Server Components; unit tests import server modules directly.
      "server-only": `${here}tests/unit/empty.ts`,
    },
  },
  test: { include: ["tests/unit/**/*.test.ts"], environment: "node" },
});
