import { defineConfig, devices } from "@playwright/test";

const port = 3010;
const baseURL = `http://127.0.0.1:${port}`;
const crossEngineCoreFlows =
  /muted reading text|principal success fixtures|previous user's cached article|mobile module drawer|article shortcuts|article links and command input|scan mode|focus mode|keep mode remains|starred module|article list failure|review queue failure|core pages expose semantic|state language never contradicts|refreshed repeated|inline-markup annotation|workbench failure|focused reader exposes retry|Daily Intelligence labels|search URL state|continue-reading route|export panel downloads|mobile Agent and Toast|axe scan finds no critical/;
const touchCoreFlows =
  /muted reading text|principal success fixtures|previous user's cached article|mobile module drawer|article links and command input|scan mode|focus mode|keep mode remains|axe scan finds no critical/;
const evidenceRun = process.env.PLAYWRIGHT_EVIDENCE === "1";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: process.env.CI ? [["line"], ["html", { open: "never" }]] : "list",
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
            grep: /@evidence @desktop/,
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
    reuseExistingServer: !process.env.CI && process.env.PLAYWRIGHT_REUSE_SERVER !== "false",
  },
});
