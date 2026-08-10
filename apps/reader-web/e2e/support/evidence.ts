import { mkdir } from "node:fs/promises";
import type { Page, TestInfo } from "@playwright/test";
import { resolveSafePngPath, resolveTestResultsDirectory } from "./paths";

export function resolveEvidenceDirectory(
  env: NodeJS.ProcessEnv = process.env,
  readerWebRoot = process.cwd(),
): string {
  return resolveTestResultsDirectory({
    variableName: "PLAYWRIGHT_EVIDENCE_DIR",
    value: env.PLAYWRIGHT_EVIDENCE_DIR ?? "test-results/evidence",
    readerWebRoot,
  });
}

export async function attachViewportScreenshot(
  page: Page,
  testInfo: TestInfo,
  name: string,
): Promise<void> {
  const evidenceDir = resolveEvidenceDirectory();
  const path = resolveSafePngPath(evidenceDir, name);
  await mkdir(evidenceDir, { recursive: true });
  await page.screenshot({ animations: "disabled", fullPage: false, path });
  await testInfo.attach(name, { path, contentType: "image/png" });
}
