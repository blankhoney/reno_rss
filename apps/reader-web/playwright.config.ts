import { relative } from "node:path";
import { defineConfig, devices } from "@playwright/test";
import { resolveTestResultsDirectory } from "./e2e/support/paths";

function resolvePort(value: string | undefined, fallback: number): number {
  const port = Number(value ?? fallback);
  if (!Number.isInteger(port) || port < 1 || port > 65534) {
    throw new Error("READER_E2E_PORT must be an integer between 1 and 65534");
  }
  return port;
}

const crossEngineCoreFlows =
  /muted reading text|normal accent|settled ArticleList text|auth and command palette|principal success fixtures|previous user's cached article|mobile module drawer|article shortcuts|article links and command input|scan mode|focus mode|keep mode remains|starred module|article list failure|review queue failure|core pages expose semantic|state language never contradicts|refreshed repeated|inline-markup annotation|workbench failure|focused reader exposes retry|Daily Intelligence labels|search URL state|continue-reading route|export panel downloads|mobile Agent and Toast|axe scan finds no critical/;
const touchCoreFlows =
  /muted reading text|normal accent|settled ArticleList text|principal success fixtures|previous user's cached article|mobile module drawer|article links and command input|scan mode|focus mode|keep mode remains|axe scan finds no critical/;

export function createPlaywrightConfig(
  env: NodeJS.ProcessEnv = process.env,
  readerWebRoot = process.cwd(),
) {
  const evidenceRun = env.PLAYWRIGHT_EVIDENCE === "1";
  const port = resolvePort(env.READER_E2E_PORT, evidenceRun ? 3012 : 3010);
  const baseURL = `http://127.0.0.1:${port}`;
  const outputOverride = env.PLAYWRIGHT_OUTPUT_DIR;
  const outputDirectory = resolveTestResultsDirectory({
    variableName: "PLAYWRIGHT_OUTPUT_DIR",
    value: outputOverride ?? "test-results",
    readerWebRoot,
    allowTestResultsRoot: outputOverride === undefined,
  });

  return defineConfig({
    testDir: "./e2e",
    outputDir: relative(readerWebRoot, outputDirectory),
    fullyParallel: false,
    forbidOnly: Boolean(env.CI),
    retries: env.CI ? 2 : 0,
    workers: 1,
    reporter: env.CI ? [["line"], ["html", { open: "never" }]] : "list",
    use: {
      baseURL,
      trace: "on-first-retry",
      screenshot: "only-on-failure",
      video: "retain-on-failure",
    },
    projects: [
      {
        name: "chromium",
        use: { ...devices["Desktop Chrome"] },
        grepInvert: /@evidence/,
      },
      {
        name: "firefox",
        use: { ...devices["Desktop Firefox"] },
        grep: crossEngineCoreFlows,
      },
      {
        name: "webkit",
        use: { ...devices["Desktop Safari"] },
        grep: crossEngineCoreFlows,
      },
      {
        name: "webkit-touch",
        use: { ...devices["iPhone 13"] },
        grep: touchCoreFlows,
        grepInvert: /@evidence/,
      },
      ...(evidenceRun
        ? [
            {
              name: "chromium-evidence",
              use: { ...devices["Desktop Chrome"] },
              grep: /(?=.*@reader-a11y)(?=.*@desktop-chromium)/,
            },
            {
              name: "chromium-mobile-evidence",
              use: {
                browserName: "chromium" as const,
                viewport: { width: 390, height: 844 },
                hasTouch: true,
                isMobile: true,
                deviceScaleFactor: 1,
              },
              grep: /(?=.*@reader-a11y)(?=.*@mobile-chromium)/,
            },
            {
              name: "webkit-touch-evidence",
              use: { ...devices["iPhone 13"] },
              grep: /@evidence @touch/,
            },
          ]
        : []),
    ],
    webServer: {
      command: "npm run start:e2e",
      cwd: ".",
      url: baseURL,
      timeout: 120_000,
      reuseExistingServer: !env.CI && env.PLAYWRIGHT_REUSE_SERVER !== "false",
    },
  });
}

export default createPlaywrightConfig();
