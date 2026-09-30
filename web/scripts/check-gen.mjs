// Fails when lib/api/ is out of date with openapi.json (CI): regenerates in place and compares
// against the committed copy. A stale enum in the zod schemas would turn every refresh into a 502.
import { execSync } from "node:child_process";
import { cpSync, mkdtempSync, readdirSync, readFileSync, rmSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

function files(dir, prefix = "") {
  return readdirSync(dir).flatMap((name) => {
    const rel = join(prefix, name);
    return statSync(join(dir, name)).isDirectory() ? files(join(dir, name), rel) : [rel];
  }).sort();
}

const before = mkdtempSync(join(tmpdir(), "clipforge-api-"));
cpSync("lib/api", before, { recursive: true });
try {
  execSync("npx openapi-ts", { stdio: "ignore" });
  const old = files(before);
  const now = files("lib/api");
  const changed = [...new Set([...old, ...now])].filter(
    (f) => !old.includes(f) || !now.includes(f) || !readFileSync(join(before, f)).equals(readFileSync(join("lib/api", f))),
  );
  if (changed.length) {
    console.error(`lib/api is stale (${changed.join(", ")}): run \`npm run gen\` and commit the result`);
    process.exit(1);
  }
  console.log("lib/api is up to date");
} finally {
  rmSync(before, { recursive: true, force: true });
}
