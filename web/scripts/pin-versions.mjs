// Rewrites every dependency range in package.json to the exact installed version.
// Run after any `npm i` or `shadcn add` that may have written ^ranges, then `npm install`.
import { readFileSync, writeFileSync } from "node:fs";

const pkg = JSON.parse(readFileSync("package.json", "utf8"));
for (const field of ["dependencies", "devDependencies"]) {
  for (const name of Object.keys(pkg[field] ?? {})) {
    const installed = JSON.parse(readFileSync(`node_modules/${name}/package.json`, "utf8"));
    pkg[field][name] = installed.version;
  }
}
writeFileSync("package.json", JSON.stringify(pkg, null, 2) + "\n");
console.log("pinned", Object.keys(pkg.dependencies).length + Object.keys(pkg.devDependencies).length, "packages");
