import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import { expect, test } from "@playwright/test";

async function resetFixtures(page: import("@playwright/test").Page) {
  const response = await page.request.post("/__e2e/reset");
  expect(response.ok()).toBe(true);
  await expect(response.json()).resolves.toEqual({ ok: true });
}

async function expectInViewport(
  page: import("@playwright/test").Page,
  target: import("@playwright/test").Locator,
) {
  const viewport = await page.evaluate(() => ({ width: window.innerWidth, height: window.innerHeight }));
  const bounds = await target.boundingBox();
  expect(bounds).not.toBeNull();
  expect(bounds!.x).toBeGreaterThanOrEqual(0);
  expect(bounds!.y).toBeGreaterThanOrEqual(0);
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(viewport.width);
  expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(viewport.height);
}

async function setFixtureAppearance(
  page: import("@playwright/test").Page,
  options: { theme: "light" | "dark"; mode: "scan" | "focus" | "keep" },
) {
  await page.addInitScript(({ theme, mode }) => {
    window.localStorage.setItem("ai-reader.theme", theme);
    window.localStorage.setItem(
      "ai-reader.craft.preferences",
      JSON.stringify({
        mode,
        density: "comfortable",
        dualPane: false,
        dualPaneKind: "notes",
        dualArticleId: null,
        pinnedThemes: [],
      }),
    );
    document.documentElement.dataset.theme = theme;
    document.documentElement.dataset.readerMode = mode;
  }, options);
}

async function attachViewportScreenshot(
  page: import("@playwright/test").Page,
  testInfo: import("@playwright/test").TestInfo,
  name: string,
) {
  const evidenceDir = resolve("test-results/evidence");
  await mkdir(evidenceDir, { recursive: true });
  const path = resolve(evidenceDir, `${name}.png`);
  await page.screenshot({ animations: "disabled", fullPage: false, path });
  await testInfo.attach(name, { path, contentType: "image/png" });
}

test("@evidence @desktop Scan workbench desktop light baseline", async ({ page }, testInfo) => {
  await resetFixtures(page);
  await setFixtureAppearance(page, { theme: "light", mode: "scan" });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.goto("/?module=all&sort=default&lang=zh");

  await expect(page.getByText("Keyboard article one", { exact: true })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.readerMode)).toBe("scan");
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth))
    .toBe(false);

  await attachViewportScreenshot(page, testInfo, "scan-workbench-desktop-light");
});

test("@evidence @touch focused reader mobile dark keyboard baseline", async ({ page }, testInfo) => {
  await resetFixtures(page);
  await setFixtureAppearance(page, { theme: "dark", mode: "focus" });
  await page.goto("/read/7?module=all&sort=default&lang=zh");

  await expect(page.getByRole("heading", { name: "Durable research workflows" })).toBeVisible();
  await expect.poll(() => page.evaluate(() => document.documentElement.dataset.theme)).toBe("dark");
  await page.keyboard.press("Tab");
  const focusState = await page.evaluate(() => {
    const target = document.activeElement as HTMLElement | null;
    if (target == null || target === document.body) return null;
    const bounds = target.getBoundingClientRect();
    const style = getComputedStyle(target);
    return {
      inViewport: bounds.top >= 0 && bounds.bottom <= window.innerHeight,
      visibleFocus: (style.outlineStyle !== "none" && style.outlineWidth !== "0px") || style.boxShadow !== "none",
    };
  });
  expect(focusState?.inViewport).toBe(true);
  expect(focusState?.visibleFocus).toBe(true);
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth))
    .toBe(false);

  await attachViewportScreenshot(page, testInfo, "focused-reader-mobile-dark-focus");
});

test("@evidence @desktop article-list error and recovered success", async ({ page }, testInfo) => {
  await resetFixtures(page);
  await setFixtureAppearance(page, { theme: "light", mode: "scan" });
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.request.post("/__e2e/article-list/fail-once");
  await page.goto("/?module=all&sort=default&lang=zh");

  const errorStatus = page.getByText(/文章加载失败/);
  const retryButton = page.getByRole("button", { name: "重试" });
  await expect(errorStatus).toBeVisible();
  await expect(retryButton).toBeVisible();
  await expect(page.getByText("暂无文章", { exact: true })).toHaveCount(0);
  await expectInViewport(page, errorStatus);
  await expectInViewport(page, retryButton);
  await attachViewportScreenshot(page, testInfo, "article-list-error");

  await page.getByRole("button", { name: "重试" }).click();
  await expect(page.getByText("Keyboard article one", { exact: true })).toBeVisible();
  await expect(page.getByText(/文章加载失败/)).toHaveCount(0);
  await attachViewportScreenshot(page, testInfo, "article-list-recovered");
});
