import { defineConfig } from "@hey-api/openapi-ts";

export default defineConfig({
  input: "./openapi.json",
  output: "lib/api",
  plugins: [
    "@hey-api/typescript",
    // Posting times carry the posting timezone's offset (e.g. -03:00): accept offsets and local times.
    { name: "zod", dates: { offset: true, local: true } },
  ],
});
