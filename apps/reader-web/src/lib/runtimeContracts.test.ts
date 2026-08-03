import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

const projectRoot = resolve(import.meta.dirname, "../..");


test("npm start prepares standalone public and static assets", () => {
  const packageJson = JSON.parse(
    readFileSync(resolve(projectRoot, "package.json"), "utf8"),
  ) as { scripts: Record<string, string> };

  assert.equal(packageJson.scripts.prestart, "npm run prepare:standalone");
  assert.match(packageJson.scripts["prepare:standalone"], /standalone\/public/);
  assert.match(packageJson.scripts["prepare:standalone"], /standalone\/\.next\/static/);
});


test("service worker registration is production-only", () => {
  const source = readFileSync(
    resolve(projectRoot, "src/components/ServiceWorkerRegister.tsx"),
    "utf8",
  );

  assert.match(source, /process\.env\.NODE_ENV !== "production"/);
});


test("service worker does not cache navigation documents as shell assets", () => {
  const source = readFileSync(resolve(projectRoot, "public/sw.js"), "utf8");

  assert.doesNotMatch(source, /SHELL_URLS = \["\/"/);
  assert.match(source, /url\.pathname\.startsWith\("\/_next\/static\/"\)/);
});
