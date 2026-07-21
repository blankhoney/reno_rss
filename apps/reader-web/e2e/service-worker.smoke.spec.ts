import { expect, test } from "@playwright/test";

async function resetFixtures(page: import("@playwright/test").Page) {
  await page.request.post("/__e2e/reset");
}

test("registers and controls the second local page load", async ({ page }) => {
  await resetFixtures(page);
  await page.goto("/");
  await expect(page).toHaveTitle("AI Reader");

  const registration = await page.evaluate(async () => {
    const registration = await navigator.serviceWorker.ready;
    return registration.active?.scriptURL ?? null;
  });
  expect(registration).toContain("/sw.js");

  await page.reload();
  await expect.poll(() => page.evaluate(() => navigator.serviceWorker.controller != null)).toBe(true);
});

test("keeps job polling on the network after service worker control", async ({ page }) => {
  await resetFixtures(page);
  await page.goto("/");
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.reload();
  await expect.poll(() => page.evaluate(() => navigator.serviceWorker.controller != null)).toBe(true);

  const statuses = await page.evaluate(async () => {
    const first = await fetch("/api/jobs/7").then((response) => response.json());
    const second = await fetch("/api/jobs/7").then((response) => response.json());
    return [first.status, second.status];
  });

  expect(statuses).toEqual(["queued", "succeeded"]);
});

test("clears cached article details when the authenticated user changes", async ({ context, page }) => {
  await resetFixtures(page);
  await page.goto("/");
  await expect(page.getByText("Ada", { exact: true })).toBeVisible();
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.reload();
  await expect.poll(() => page.evaluate(() => navigator.serviceWorker.controller != null)).toBe(true);

  const articleForA = await page.evaluate(async () => {
    const response = await fetch("/api/articles/7");
    return { status: response.status, body: await response.json() };
  });
  expect(articleForA).toMatchObject({ status: 200, body: { owner: "user-a" } });

  await page.getByRole("button", { name: "退出登录" }).click();
  await page.getByRole("textbox", { name: "显示名称" }).fill("Babbage");
  await page.getByRole("button", { name: "进入阅读" }).click();
  await expect(page.getByText("Babbage", { exact: true })).toBeVisible();

  await context.setOffline(true);
  const articleForBOffline = await page.evaluate(async () => {
    const response = await fetch("/api/articles/7");
    return { status: response.status, body: await response.json() };
  });
  await context.setOffline(false);

  expect(articleForBOffline).toMatchObject({ status: 503, body: { error: { code: "offline" } } });
});

test("mobile module drawer overlays the bottom navigation", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await resetFixtures(page);
  await page.goto("/?module=all");
  await page.getByRole("button", { name: "打开阅读模块" }).click();
  await expect(page.getByRole("dialog", { name: "阅读模块" })).toBeVisible();

  const layers = await page.evaluate(() => ({
    drawer: Number.parseInt(getComputedStyle(document.querySelector(".mobileNavOverlay")!).zIndex, 10),
    bottomNav: Number.parseInt(getComputedStyle(document.querySelector(".mobileBottomNav")!).zIndex, 10),
  }));
  expect(layers.drawer).toBeGreaterThan(layers.bottomNav);
});

test("article shortcuts only apply when the article list owns focus", async ({ page }) => {
  await resetFixtures(page);
  await page.goto("/?module=all");
  await expect(page.getByText("Keyboard article one", { exact: true })).toBeVisible();

  const sortButton = page.getByRole("button", { name: /排序/ });
  await sortButton.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("listbox", { name: "排序方式" })).toBeVisible();
  await expect(page).toHaveURL(/\?module=all/);

  const list = page.locator(".articleList");
  await list.focus();
  await page.keyboard.press("j");
  await expect(page.getByRole("link", { name: /Keyboard article two/ })).toHaveAttribute("aria-current", "true");
});

test("mobile module drawer traps focus, inerts the background, and restores its trigger", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 });
  await resetFixtures(page);
  await page.goto("/?module=all");
  const trigger = page.getByRole("button", { name: "打开阅读模块" });
  await trigger.click();
  const drawer = page.getByRole("dialog", { name: "阅读模块" });
  await expect(drawer).toBeVisible();
  await expect(page.locator(".workbenchMain")).toHaveJSProperty("inert", true);
  await expect(page.locator(".mobileBottomNav")).toHaveJSProperty("inert", true);

  const focusables = drawer.locator("a[href], button:not([disabled])");
  await focusables.last().focus();
  await page.keyboard.press("Tab");
  await expect.poll(() => drawer.evaluate((element) => element.contains(document.activeElement))).toBe(true);

  await page.keyboard.press("Escape");
  await expect(drawer).toBeHidden();
  await expect(trigger).toBeFocused();
});

test("command palette inerts the app and restores prior focus after Escape", async ({ page }) => {
  await resetFixtures(page);
  await page.goto("/?module=all");
  const sortButton = page.getByRole("button", { name: /排序/ });
  await sortButton.focus();
  await page.keyboard.press("Meta+k");
  const dialog = page.getByRole("dialog", { name: "命令面板" });
  await expect(dialog).toBeVisible();
  await expect(page.locator(".workbench")).toHaveJSProperty("inert", true);
  await expect(dialog.getByRole("textbox")).toBeFocused();

  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(sortButton).toBeFocused();
});

test("Focus mode preserves a visible workbench column at the 899px breakpoint", async ({ page }) => {
  await page.setViewportSize({ width: 899, height: 900 });
  await resetFixtures(page);
  await page.goto("/?module=all");
  await page.evaluate(() => {
    document.documentElement.dataset.readerMode = "focus";
  });

  const gridColumns = await page.locator(".workbench").evaluate((element) => getComputedStyle(element).gridTemplateColumns);
  expect(gridColumns.startsWith("0px")).toBe(false);
});
