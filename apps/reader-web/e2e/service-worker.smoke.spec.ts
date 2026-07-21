import { expect, test } from "@playwright/test";

test("registers and controls the second local page load", async ({ page }) => {
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
