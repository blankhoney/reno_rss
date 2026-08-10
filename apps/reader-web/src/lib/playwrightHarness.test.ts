import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, rmSync, symlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import test from "node:test";
import { resolveEvidenceDirectory } from "../../e2e/support/evidence";
import { resolveSafePngPath } from "../../e2e/support/paths";
import { createPlaywrightConfig } from "../../playwright.config";

const outputDirectoryError =
  "PLAYWRIGHT_OUTPUT_DIR must be a non-empty relative subdirectory of test-results without traversal or symlinks";
const evidenceDirectoryError =
  "PLAYWRIGHT_EVIDENCE_DIR must be a non-empty relative subdirectory of test-results without traversal or symlinks";
const screenshotNameError =
  "Screenshot name must be a safe PNG basename using only letters, numbers, hyphens, or underscores";

test("Playwright runner output defaults to test-results", () => {
  const config = createPlaywrightConfig({}, "/reader-web");

  assert.equal(config.outputDir, "test-results");
});

test("Playwright runner output accepts an isolated environment override", () => {
  const config = createPlaywrightConfig(
    { PLAYWRIGHT_OUTPUT_DIR: "test-results/playwright-commit-h" },
    "/reader-web",
  );

  assert.equal(config.outputDir, "test-results/playwright-commit-h");
});

for (const value of [
  "",
  "   ",
  ".",
  "..",
  "test-results",
  "/tmp/playwright-output",
  "C:\\playwright-output",
  "test-results/../outside",
  "test-results/commit/../../outside",
  "test-results/./commit",
]) {
  test(`Playwright runner output rejects unsafe override ${JSON.stringify(value)}`, () => {
    assert.throws(
      () => createPlaywrightConfig({ PLAYWRIGHT_OUTPUT_DIR: value }, "/reader-web"),
      { message: outputDirectoryError },
    );
  });
}

test("evidence screenshots default to the existing evidence directory", () => {
  assert.equal(
    resolveEvidenceDirectory({}, "/reader-web"),
    resolve("/reader-web", "test-results/evidence"),
  );
});

test("evidence screenshots accept an isolated environment override", () => {
  assert.equal(
    resolveEvidenceDirectory(
      { PLAYWRIGHT_EVIDENCE_DIR: "test-results/evidence-commit-h" },
      "/reader-web",
    ),
    resolve("/reader-web", "test-results/evidence-commit-h"),
  );
});

for (const value of [
  "",
  "   ",
  ".",
  "..",
  "test-results",
  "/tmp/playwright-evidence",
  "C:\\playwright-evidence",
  "test-results/../outside",
  "test-results/commit/../../outside",
  "test-results/./commit",
]) {
  test(`evidence screenshots reject unsafe override ${JSON.stringify(value)}`, () => {
    assert.throws(
      () =>
        resolveEvidenceDirectory(
          { PLAYWRIGHT_EVIDENCE_DIR: value },
          "/reader-web",
        ),
      { message: evidenceDirectoryError },
    );
  });
}

test("harness directories reject an existing symlink component", () => {
  const readerWebRoot = mkdtempSync(join(tmpdir(), "reader-web-harness-"));
  const outside = mkdtempSync(join(tmpdir(), "reader-web-outside-"));
  mkdirSync(join(readerWebRoot, "test-results"));
  symlinkSync(outside, join(readerWebRoot, "test-results", "escaped"), "dir");

  try {
    assert.throws(
      () =>
        resolveEvidenceDirectory(
          { PLAYWRIGHT_EVIDENCE_DIR: "test-results/escaped/evidence" },
          readerWebRoot,
        ),
      { message: evidenceDirectoryError },
    );
  } finally {
    rmSync(readerWebRoot, { recursive: true, force: true });
    rmSync(outside, { recursive: true, force: true });
  }
});

test("screenshot path accepts a safe basename and adds the PNG extension", () => {
  assert.equal(
    resolveSafePngPath(
      "/reader-web/test-results/evidence-commit-h",
      "focused-reader_mobile-dark",
    ),
    "/reader-web/test-results/evidence-commit-h/focused-reader_mobile-dark.png",
  );
});

for (const name of [
  "",
  ".",
  "..",
  "../outside",
  "nested/outside",
  "nested\\outside",
  "/tmp/outside",
  "evidence.png",
]) {
  test(`screenshot path rejects unsafe name ${JSON.stringify(name)}`, () => {
    assert.throws(
      () => resolveSafePngPath("/reader-web/test-results/evidence", name),
      { message: screenshotNameError },
    );
  });
}

test("evidence mode exposes separate desktop and mobile Chromium projects", () => {
  const config = createPlaywrightConfig({ PLAYWRIGHT_EVIDENCE: "1" }, "/reader-web");
  const projects = config.projects ?? [];
  const desktop = projects.find((project) => project.name === "chromium-evidence");
  const mobile = projects.find((project) => project.name === "chromium-mobile-evidence");

  assert.ok(desktop);
  assert.ok(mobile);
  assert.equal(mobile.use?.browserName, "chromium");
  assert.deepEqual(mobile.use?.viewport, { width: 390, height: 844 });
  assert.equal(mobile.use?.hasTouch, true);
  assert.equal(mobile.use?.isMobile, true);
  assert.equal(mobile.use?.deviceScaleFactor, 1);
});
