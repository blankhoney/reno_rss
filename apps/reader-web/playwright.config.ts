import { defineConfig, devices } from "@playwright/test";

const port = 3010;
const baseURL = `http://127.0.0.1:${port}`;
const crossEngineCoreFlows =
  /muted reading text|principal success fixtures|previous user's cached article|mobile module drawer|article shortcuts|article links and command input|scan mode remains|focus mode remains|keep mode remains|starred module|article list failure|review queue failure|core pages expose semantic|state language never contradicts|refreshed repeated|inline-markup annotation/;
const touchCoreFlows =
  /muted reading text|principal success fixtures|previous user's cached article|mobile module drawer|article links and command input|scan mode remains|focus mode remains|keep mode remains/;

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
  },
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
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
    },
  ],
  webServer: {
    command: "npm run start:e2e",
    cwd: ".",
    url: baseURL,
    timeout: 120_000,
    reuseExistingServer: !process.env.CI,
  },
});
