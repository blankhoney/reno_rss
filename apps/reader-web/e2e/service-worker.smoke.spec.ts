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
